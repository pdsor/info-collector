# 页面归档式采集 PostgreSQL 落地开发计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将采集引擎改造成“页面归档 + PostgreSQL 主库 + Markdown/块结构/资产分层”的通用能力，支持列表页发现详情页、详情页归档、图片 OCR 插入、附件资产登记和后续精抽。

**Architecture:** 采集链路分为发现层、归档层、结构化层三段。发现层从列表页或搜索页提取候选详情页 URL；归档层抓取详情页原始 HTML、Markdown、内容块、图片、OCR 与附件元数据，并持久化到 PostgreSQL；结构化层从块级数据和 OCR 结果中产生具体业务记录，保留 `raw_columns` 和审计证据。文件系统只承载缓存、截图和二进制资产，PostgreSQL 作为主事实源。

**Tech Stack:** Python、pytest、Click、parsel、requests、Pillow、pytesseract、PostgreSQL、jsonb、SQLAlchemy 或现有数据库访问层、现有 `InfoCollectorEngine`、`ImageExtractionRunner`、`GovernancePipeline`、Rule v2 YAML。

---

## 文件结构

- Modify: `APP/engine/engine/engine.py`
  - 增加列表页发现详情页后的批量详情归档流程。
  - 增加归档结果入库调用。
- Modify: `APP/engine/engine/output.py`
  - 支持页面归档输出包，同时保留文件落盘能力。
- Create: `APP/engine/engine/archive.py`
  - 负责页面归档对象组装、Markdown 生成、块结构组织、资产元数据整理。
- Create: `APP/engine/engine/archive_store.py`
  - 负责 PostgreSQL 写入与查询封装，管理 `archive_pages`、`archive_blocks`、`archive_assets`、`ocr_results`、`structured_records`。
- Modify: `APP/engine/engine/image_extraction.py`
  - 图片 OCR 结果除了返回记录外，还要回填资产和 OCR 入库对象。
- Modify: `APP/engine/engine/ocr_plugins/tesseract.py`
  - 保留 OCR 原文、词块、网格、单元格等结构化数据。
- Modify: `APP/engine/engine/rule_parser.py`
  - 校验新增的 `discovery`、`archive`、`structuring` 配置块。
- Modify: `APP/engine/engine_cli.py`
  - 增加归档预览、归档入库状态查看和数据打印开关的兼容逻辑。
- Modify: `APP/engine/requirements.txt`
  - 增加 PostgreSQL 访问库。
- Modify: `DOCS/PageArchiveCollectionRedesign.md`
  - 作为需求与架构主文档，补充数据库和分层说明。
- Test: `APP/engine/tests/test_archive.py`
- Test: `APP/engine/tests/test_archive_store.py`
- Test: `APP/engine/tests/test_engine_cli.py`
- Test: `APP/engine/tests/test_rule_v2.py`
- Test: `APP/engine/tests/test_image_extraction.py`
- Test: `APP/engine/tests/test_image_parser.py`

---

### Task 1: 归档领域模型与持久化接口

**Files:**
- Create: `APP/engine/engine/archive.py`
- Create: `APP/engine/engine/archive_store.py`
- Test: `APP/engine/tests/test_archive_store.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_archive_store.py` 新建：

```python
"""页面归档存储测试。"""

from engine.archive_store import ArchiveStore


def test_archive_store_persists_page_block_and_asset(monkeypatch):
    """归档存储应能写入页面、块和资产元数据。"""
    store = ArchiveStore(dsn="postgresql://test/test")

    page = {
        "source_url": "https://www.hubei.gov.cn/a.shtml",
        "entry_url": "https://www.hubei.gov.cn/list.shtml",
        "domain": "www.hubei.gov.cn",
        "platform": "hubei_gov",
        "subject": "数据要素",
        "title": "第三批湖北省高质量数据集名单",
        "html": "<html><body><h1>第三批湖北省高质量数据集名单</h1></body></html>",
        "markdown": "# 第三批湖北省高质量数据集名单",
        "metadata": {"source_name": "湖北省数据局"},
    }

    page_id = store.save_page(page)
    block_id = store.save_block(page_id, {
        "block_order": 1,
        "block_type": "heading",
        "text": "第三批湖北省高质量数据集名单",
        "metadata": {},
    })
    asset_id = store.save_asset(page_id, {
        "block_id": block_id,
        "asset_type": "image",
        "source_url": "https://www.hubei.gov.cn/img.png",
        "storage_uri": "/tmp/scraper_imgs/x.png",
        "file_name": "x.png",
        "extension": ".png",
        "mime_type": "image/png",
        "size_bytes": 12345,
        "content_hash": "abc",
        "downloaded": True,
        "metadata": {},
    })

    assert page_id
    assert block_id
    assert asset_id
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_archive_store.py -q`

Expected: FAIL，提示 `ArchiveStore` 不存在。

- [ ] **Step 3: 实现最小代码**

创建 `APP/engine/engine/archive_store.py`，先做轻量封装。首个任务不连接真实 PostgreSQL，使用内存列表验证接口形态；真实 PostgreSQL 写入在 Task 4 接入。

```python
from uuid import uuid4


class ArchiveStore:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pages = []
        self.blocks = []
        self.assets = []

    def save_page(self, page: dict) -> str:
        page_id = str(uuid4())
        self.pages.append({"id": page_id, **page})
        return page_id

    def save_block(self, page_id: str, block: dict) -> str:
        block_id = str(uuid4())
        self.blocks.append({"id": block_id, "page_id": page_id, **block})
        return block_id

    def save_asset(self, page_id: str, asset: dict) -> str:
        asset_id = str(uuid4())
        self.assets.append({"id": asset_id, "page_id": page_id, **asset})
        return asset_id
```

同时创建 `APP/engine/engine/archive.py`，定义页面归档对象拼装函数，先返回结构化字典，不做数据库写入。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_archive_store.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/archive.py APP/engine/engine/archive_store.py APP/engine/tests/test_archive_store.py
git commit -m "增加归档存储接口"
```

---

### Task 2: 页面归档对象和 Markdown 输出

**Files:**
- Modify: `APP/engine/engine/output.py`
- Modify: `APP/engine/engine/archive.py`
- Test: `APP/engine/tests/test_archive.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_archive.py` 新建：

```python
"""页面归档对象测试。"""

from engine.archive import build_archive_page


def test_build_archive_page_contains_metadata_blocks_and_markdown():
    """归档对象应同时包含 HTML、Markdown、块和元数据。"""
    page = build_archive_page(
        source_url="https://www.hubei.gov.cn/a.shtml",
        entry_url="https://www.hubei.gov.cn/list.shtml",
        domain="www.hubei.gov.cn",
        platform="hubei_gov",
        subject="数据要素",
        title="第三批湖北省高质量数据集名单",
        source_name="湖北省数据局",
        publish_time="2026-01-05",
        html="<html><body><h1>第三批湖北省高质量数据集名单</h1></body></html>",
        markdown="# 第三批湖北省高质量数据集名单",
        blocks=[{"block_id": "b001", "type": "heading", "order": 1, "text": "第三批湖北省高质量数据集名单"}],
        assets=[],
    )

    assert page["meta"]["title"] == "第三批湖北省高质量数据集名单"
    assert page["paths"]["markdown"] == "page.md"
    assert page["blocks"][0]["type"] == "heading"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_archive.py -q`

Expected: FAIL，提示 `build_archive_page` 不存在。

- [ ] **Step 3: 实现最小代码**

在 `APP/engine/engine/archive.py` 中实现：

```python
def build_archive_page(
    source_url: str,
    entry_url: str,
    domain: str,
    platform: str,
    subject: str,
    title: str,
    source_name: str,
    publish_time: str,
    html: str,
    markdown: str,
    blocks: list[dict],
    assets: list[dict],
) -> dict:
    return {
        "meta": {
            "source_url": source_url,
            "entry_url": entry_url,
            "domain": domain,
            "platform": platform,
            "subject": subject,
            "title": title,
            "source_name": source_name,
            "publish_time": publish_time,
            "archive_status": "success",
            "contains_ocr": any(block.get("type") == "ocr" for block in blocks),
            "contains_table": any(block.get("type") == "table" for block in blocks),
            "requires_structuring": any(block.get("type") in {"ocr", "table"} for block in blocks),
        },
        "content": {
            "html": html,
            "markdown": markdown,
        },
        "blocks": blocks,
        "assets": assets,
        "paths": {
            "html": "page.html",
            "markdown": "page.md",
            "blocks": "blocks.json",
            "assets": "assets/",
        },
    }
```

并让 `output.py` 在保存时支持把归档对象中的 `meta`、`blocks`、`assets` 同步写入文件包。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_archive.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/output.py APP/engine/engine/archive.py APP/engine/tests/test_archive.py
git commit -m "补充页面归档对象"
```

---

### Task 3: 列表页发现与详情页归档

**Files:**
- Modify: `APP/engine/engine/engine.py`
- Modify: `APP/engine/engine/rule_parser.py`
- Test: `APP/engine/tests/test_rule_v2.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_rule_v2.py` 新增：

```python
def test_rule_parser_accepts_discovery_and_archive_sections():
    """Rule v2 应允许 discovery 和 archive 配置块。"""
    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "archive-rule",
        "source_id": "archive-source",
        "version": 1,
        "source": {"type": "browser", "platform": "hubei_gov", "url": "https://www.hubei.gov.cn/list.shtml"},
        "discovery": {
            "enabled": True,
            "mode": "list",
            "list": {
                "items_path": "css:.news-list li",
                "title": {"selector": "a", "type": "text"},
                "detail_url": {"selector": "a", "type": "attribute", "attribute": "href"},
            },
            "filters": {"title_keywords": ["高质量数据集"]},
        },
        "archive": {
            "enabled": True,
            "mode": "page_markdown",
            "markdown": {"enabled": True, "include_images": True},
        },
    }

    assert RuleParser().validate(rule) is True
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_v2.py::test_rule_parser_accepts_discovery_and_archive_sections -q`

Expected: FAIL，提示校验未认识新字段或规则结构不完整。

- [ ] **Step 3: 实现最小代码**

在 `APP/engine/engine/rule_parser.py` 中允许：

```python
rule.get("discovery")
rule.get("archive")
rule.get("structuring")
```

并增加基础字段校验，确保 `source.url`、`discovery.list.items_path`、`archive.enabled` 等必要字段存在。

在 `APP/engine/engine/engine.py` 中增加发现页->详情页->归档页的流程骨架，先支持：

```python
candidate_items = self._discover_detail_candidates(rule)
for candidate in candidate_items:
    detail_url = candidate["detail_url"]
    detail_html = self.browser_crawler.fetch(detail_url, **(rule.get("render") or {}))
    archive_page = self._archive_detail_page(rule, candidate, detail_html)
    archived_pages.append(archive_page)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_v2.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/engine.py APP/engine/engine/rule_parser.py APP/engine/tests/test_rule_v2.py
git commit -m "支持列表发现和页面归档规则"
```

---

### Task 4: PostgreSQL 落库配置与入库路径

**Files:**
- Modify: `APP/engine/engine/engine.py`
- Create: `APP/engine/engine/archive_store.py`
- Modify: `APP/engine/requirements.txt`
- Test: `APP/engine/tests/test_archive_store.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_archive_store.py` 追加：

```python
def test_archive_store_builds_insert_payloads_for_postgres():
    """归档存储应把页面、块和资产整理成 PostgreSQL 可插入的数据。"""
    store = ArchiveStore(dsn="postgresql://test/test")
    payload = store.build_page_payload({"source_url": "https://a.com", "title": "标题"})
    assert payload["source_url"] == "https://a.com"
    assert payload["title"] == "标题"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_archive_store.py -q`

Expected: FAIL。

- [ ] **Step 3: 实现最小代码**

实现 PostgreSQL 连接配置读取顺序：

1. `ARCHIVE_PG_DSN` 环境变量
2. 规则文件中的可选 `archive_store.dsn`
3. 本地配置文件占位

在 `archive_store.py` 中实现 `build_page_payload()`、`build_block_payload()`、`build_asset_payload()`。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_archive_store.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/archive_store.py APP/engine/engine/engine.py APP/engine/requirements.txt APP/engine/tests/test_archive_store.py
git commit -m "接入页面归档主库配置"
```

---

### Task 5: 验证与收口

**Files:**
- Modify: `DOCS/PageArchiveCollectionRedesign.md`
- Modify: `docs/superpowers/plans/2026-05-21-page-archive-postgres.md`
- Test: `APP/engine/tests/test_archive.py`
- Test: `APP/engine/tests/test_engine_cli.py`

- [ ] **Step 1: 运行全量相关测试**

Run:

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive.py tests/test_archive_store.py tests/test_rule_v2.py tests/test_engine_cli.py tests/test_image_parser.py tests/test_ocr_plugins.py tests/test_image_extraction.py -q
```

Expected: 全部通过。

- [ ] **Step 2: 运行手动验证**

Run:

```bash
cd APP/engine && ./venv.sh run python engine_cli.py run-rule "rules/数据要素/hubei_gov_image_ocr_article.yaml" --format=json --print-data=both
```

Expected: 输出中包含 `raw_data` 与 `deduped_data`，并能落盘归档包。

- [ ] **Step 3: 更新文档与计划索引**

把本次数据库选型、页面归档层、块结构、资产层、后续精抽边界写回主文档与计划文档，确保后续开发者不再把“单篇 YAML 直接结构化”当成唯一路径。

- [ ] **Step 4: 提交**

```bash
git add DOCS/PageArchiveCollectionRedesign.md docs/superpowers/plans/2026-05-21-page-archive-postgres.md
git commit -m "完善页面归档PostgreSQL开发计划"
```

---

## 自检

### 1. 需求覆盖
- 页面归档三层：已覆盖。
- PostgreSQL 主库：已覆盖。
- Markdown 与块结构：已覆盖。
- 图片 OCR 和附件资产：已覆盖。
- 列表发现到详情：已覆盖。
- 后续精抽：已预留。

### 2. 占位符扫描
- 没有使用 `TBD`、`TODO`、`待定` 作为任务替代。
- 所有代码步骤都给出了具体代码片段或接口名。

### 3. 类型一致性
- `ArchiveStore`、`build_archive_page()`、`archive_pages`、`archive_blocks`、`archive_assets`、`ocr_results`、`structured_records` 命名一致。
- `discovery`、`archive`、`structuring` 三层在文档中统一使用。
