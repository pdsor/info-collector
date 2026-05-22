# 列表页 discovery 到详情页归档最小闭环开发计划

> **面向代理工作者：** 执行本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 在 `archive.enabled=true` 的规则上启用 `discovery.enabled=true` 时，让 `InfoCollectorEngine.run()` 从列表/搜索页发现第一条候选详情页 URL，单独抓取该详情页 HTML，并把详情页（而非列表页）作为归档对象走 `OutputManager.save_archive_package()` + `ArchiveStore.save_archive_page()`。

**架构：** 本切片只覆盖「列表 → 单条详情 → 归档」一条最小闭环，不引入翻页、不做批量并发、不连真实 PostgreSQL。在 `engine.py` 新增 `_discover_first_detail()` 与 `_archive_detail_page()`，把它们插在 `crawl()` 之后、`_maybe_archive_page()` 之前的路径中。`_maybe_archive_page()` 在被升级为支持详情归档时，由调用方传入预先解析好的详情 HTML、blocks、assets，原列表归档分支保留为兜底。

**技术栈：** Python、pytest、现有 `InfoCollectorEngine`、`HTMLCrawler.fetch/parse_items`、`build_archive_page`、`OutputManager.save_archive_package`、`ArchiveStore`、Rule v2 YAML。

---

## 文件结构

- 修改：`APP/engine/engine/engine.py`
  - 新增 `_discover_first_detail(rule, list_html)`：基于 `discovery.list.items_path/detail_url` 从已抓到的列表 HTML 中取第一条候选 `{title, detail_url}`，应用 `discovery.filters.title_keywords` 简单过滤。
  - 新增 `_extract_detail_blocks(rule, detail_html)`：按 `archive.detail.selector` 解析详情页正文，产出一个 `heading` + 一个 `paragraph` block；首版不解析图片/附件。
  - 新增 `_fetch_detail_html(rule, detail_url)`：复用现有 html/browser 客户端取详情页。
  - 调整 `_maybe_archive_page(rule, items, html, *, detail_url=None, detail_html=None, blocks=None, assets=None, title=None)`：当调用方传入详情上下文时，按详情口径组装归档对象；否则保持旧行为。
  - `run()` 在 `crawl()` 之后判断：若 `archive.enabled` 且 `discovery.enabled=true`，先取列表 HTML（沿用既有 crawler）、调用 `_discover_first_detail`，再 `_fetch_detail_html` + `_extract_detail_blocks`，最后把详情信息透传给 `_maybe_archive_page`。
- 修改：`APP/engine/engine/rule_parser.py`
  - 给 `_validate_archive_blocks()` 补一条最小校验：当 `discovery.enabled=true` 时必须有 `discovery.list.items_path` 和 `discovery.list.detail_url`。
- 新增：`APP/engine/tests/test_archive_discovery.py`
  - 三个用例：
    1. `discovery` 未启用 → 走旧的列表归档路径，保持现状。
    2. `discovery.enabled=true` → 调用 `_fetch_detail_html` 抓详情，归档对象的 `meta.source_url`、`meta.title` 来自详情，`blocks` 非空。
    3. discovery 未匹配到任何候选 → `run()` 返回 `status=="success"`，但不写归档包、不写主库（避免把空详情当成有效归档）。
- 不修改：`engine/archive.py`、`engine/archive_store.py`、`engine/output.py`。
- 不引入：discovery 翻页、批量详情、真实 PostgreSQL、Dashboard 改动。

---

## 任务 1：discovery 校验与失败测试

**文件：**
- 修改：`APP/engine/engine/rule_parser.py`
- 新增：`APP/engine/tests/test_archive_discovery.py`

- [ ] **步骤 1：补一条 rule_parser 测试**

在 `tests/test_rule_v2.py` 末尾追加：

```python
def test_rule_parser_requires_discovery_list_when_enabled():
    """discovery.enabled=true 必须提供 list.items_path 与 list.detail_url。"""
    from engine.rule_parser import RuleParser
    import pytest

    rule = {
        "rule_id": "discovery-bad",
        "source_id": "discovery-bad-source",
        "version": 1,
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "source": {"type": "html", "platform": "x", "url": "https://x/list"},
        "discovery": {"enabled": True, "list": {}},
        "archive": {"enabled": True},
    }
    with pytest.raises(ValueError, match="discovery.list"):
        RuleParser().validate(rule)
```

- [ ] **步骤 2：实现校验**

在 `_validate_archive_blocks()` 中处理：

```python
if discovery is not None and discovery.get("enabled"):
    list_cfg = discovery.get("list") or {}
    if not list_cfg.get("items_path"):
        raise ValueError("discovery.list.items_path is required when discovery is enabled")
    if not list_cfg.get("detail_url"):
        raise ValueError("discovery.list.detail_url is required when discovery is enabled")
```

- [ ] **步骤 3：新增 discovery 闭环失败测试**

新建 `APP/engine/tests/test_archive_discovery.py`：

```python
"""列表→详情→归档最小闭环测试。"""

from pathlib import Path

import yaml

from engine.engine import InfoCollectorEngine


LIST_HTML = """
<html><body>
  <ul class="news-list">
    <li><a href="/detail/1.shtml">高质量数据集名单公示</a></li>
    <li><a href="/detail/2.shtml">无关公告</a></li>
  </ul>
</body></html>
"""

DETAIL_HTML = """
<html><body>
  <h1 class="title">高质量数据集名单公示</h1>
  <div class="content"><p>正文段落一</p><p>正文段落二</p></div>
</body></html>
"""


def _write_rule(tmp_path: Path, *, discovery=True):
    rule = {
        "name": "discovery闭环",
        "subject": "数据要素",
        "source": {
            "type": "html",
            "platform": "hubei_gov",
            "url": "https://www.hubei.gov.cn/list.shtml",
            "client": "desktop",
        },
        "list": {
            "items_path": "css:.news-list li",
            "fields": [
                {"name": "title", "type": "element_text"},
                {"name": "url", "type": "element_href"},
            ],
        },
        "archive": {"enabled": True, "mode": "page_markdown"},
        "dedup": {"incremental": False},
    }
    if discovery:
        rule["discovery"] = {
            "enabled": True,
            "list": {
                "items_path": "css:.news-list li",
                "title": {"selector": "a", "type": "text"},
                "detail_url": {"selector": "a", "type": "attribute", "attribute": "href"},
            },
            "filters": {"title_keywords": ["高质量数据集"]},
        }
    path = tmp_path / "rule.yaml"
    path.write_text(yaml.safe_dump(rule, allow_unicode=True), encoding="utf-8")
    return str(path)


class _RecordingStore:
    def __init__(self):
        self.saved = []

    def save_archive_page(self, archive_page):
        self.saved.append(archive_page)
        return {
            "page_id": "page-uuid-1",
            "block_ids": {},
            "asset_ids": {},
            "ocr_result_ids": [],
            "counts": {"pages": 1, "blocks": len(archive_page.get("blocks", [])), "assets": 0, "ocr_results": 0},
        }


def _bind_store(monkeypatch, store):
    monkeypatch.setattr(
        "engine.engine.ArchiveStore.from_rule",
        classmethod(lambda cls, rule: store),
    )


def _stub_html(monkeypatch, engine, *, list_html=LIST_HTML, detail_html=DETAIL_HTML):
    fetches = []

    def fake_fetch(url, **kwargs):
        fetches.append(url)
        if url.endswith("/list.shtml"):
            return list_html
        return detail_html

    monkeypatch.setattr(engine.html_crawler, "fetch", fake_fetch)
    return fetches


def test_discovery_disabled_keeps_list_archive_behavior(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, discovery=False)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine)
    monkeypatch.setattr(
        engine.output_mgr, "save_archive_package", lambda page, rule: str(tmp_path / "pkg")
    )
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    result = engine.run(rule_path)

    assert result.get("archive_page_id") == "page-uuid-1"
    assert store.saved[0]["meta"]["source_url"].endswith("list.shtml")


def test_discovery_enabled_archives_first_detail(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, discovery=True)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    fetches = _stub_html(monkeypatch, engine)
    monkeypatch.setattr(
        engine.output_mgr, "save_archive_package", lambda page, rule: str(tmp_path / "pkg")
    )
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    result = engine.run(rule_path)

    assert result["archive_page_id"] == "page-uuid-1"
    archived = store.saved[0]
    assert archived["meta"]["source_url"].endswith("/detail/1.shtml")
    assert archived["meta"]["title"] == "高质量数据集名单公示"
    assert len(archived["blocks"]) >= 1
    assert any(u.endswith("/detail/1.shtml") for u in fetches)


def test_discovery_no_candidate_skips_archive(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, discovery=True)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    empty_list = "<html><body><ul class='news-list'></ul></body></html>"
    _stub_html(monkeypatch, engine, list_html=empty_list)

    def _fail(*args, **kwargs):
        raise AssertionError("不应触发归档")

    monkeypatch.setattr(engine.output_mgr, "save_archive_package", _fail)
    _bind_store(monkeypatch, _RecordingStore())

    result = engine.run(rule_path)

    assert result["status"] in {"success", "partial_success"}
    assert "archive_page_id" not in result
```

- [ ] **步骤 4：运行测试确认失败**

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_discovery.py tests/test_rule_v2.py::test_rule_parser_requires_discovery_list_when_enabled -q
```

预期：3 个 discovery 用例失败（实现尚未到位），rule_parser 用例通过。

---

## 任务 2：实现 discovery + detail 抓取

**文件：**
- 修改：`APP/engine/engine/engine.py`

- [ ] **步骤 1：新增 `_discover_first_detail()`**

复用 `parsel.Selector` 解析 `discovery.list.items_path`：

```python
def _discover_first_detail(self, rule: dict, list_html: str) -> dict | None:
    cfg = (rule.get("discovery") or {})
    list_cfg = cfg.get("list") or {}
    items_path = list_cfg.get("items_path", "")
    if not items_path or not list_html:
        return None
    title_def = list_cfg.get("title") or {}
    detail_def = list_cfg.get("detail_url") or {}
    keywords = (cfg.get("filters") or {}).get("title_keywords") or []

    selector = parsel.Selector(text=list_html)
    css = items_path.removeprefix("css:") if items_path.startswith("css:") else items_path
    for item in selector.css(css):
        title_sel = item.css(title_def.get("selector", ""))
        title = "".join(title_sel.xpath("string()").getall()).strip()
        url_sel = item.css(detail_def.get("selector", ""))
        attribute = detail_def.get("attribute", "href")
        detail_url = url_sel.attrib.get(attribute, "") if url_sel else ""
        if not detail_url:
            continue
        if keywords and not any(k in title for k in keywords):
            continue
        return {"title": title, "detail_url": self._absolutize(rule, detail_url)}
    return None
```

`_absolutize()` 用 `urllib.parse.urljoin(source.url, detail_url)` 把相对 URL 补全。

- [ ] **步骤 2：新增 `_fetch_detail_html()` 与 `_extract_detail_blocks()`**

```python
def _fetch_detail_html(self, rule: dict, detail_url: str) -> str:
    client = (rule.get("source") or {}).get("client", "desktop")
    if client == "browser":
        return self.browser_crawler.fetch(detail_url, rule.get("render", {}) or {})
    return self.html_crawler.fetch(detail_url)


def _extract_detail_blocks(self, rule: dict, detail_html: str) -> tuple[str, list[dict]]:
    archive_cfg = rule.get("archive") or {}
    metadata = (archive_cfg.get("detail") or {}).get("metadata") or {}
    title_selector = (metadata.get("title") or {}).get("selector") or "h1"
    content_selector = (metadata.get("content") or {}).get("selector") or "body"

    selector = parsel.Selector(text=detail_html or "")
    title = "".join(selector.css(title_selector).xpath("string()").getall()).strip()

    blocks = []
    if title:
        blocks.append({"block_id": "b1", "type": "heading", "order": 1, "text": title, "level": 1})
    for index, para in enumerate(selector.css(f"{content_selector} p"), start=2):
        text = "".join(para.xpath("string()").getall()).strip()
        if text:
            blocks.append({"block_id": f"b{index}", "type": "paragraph", "order": index, "text": text})
    return title, blocks
```

- [ ] **步骤 3：升级 `_maybe_archive_page()` 支持详情口径**

把签名扩展为：

```python
def _maybe_archive_page(
    self,
    rule: dict,
    items: list,
    html: str | None,
    *,
    detail_url: str | None = None,
    detail_html: str | None = None,
    detail_title: str | None = None,
    detail_blocks: list[dict] | None = None,
    detail_assets: list[dict] | None = None,
) -> dict:
```

当 `detail_url` 非空时：
- `source_url` / `final_url` 用 `detail_url`，`entry_url` 用 `rule.source.url`。
- `title` 优先取 `detail_title`，否则保留旧逻辑。
- `html` 取 `detail_html`，`blocks`/`assets` 取详情口径，缺失则空列表。

旧调用（列表归档）保持原状。

- [ ] **步骤 4：在 `run()` 中接入闭环**

在现有 `archive_info = self._maybe_archive_page(...)` 之前增加分支：

```python
discovery_cfg = (rule.get("discovery") or {})
if (rule.get("archive") or {}).get("enabled") and discovery_cfg.get("enabled"):
    list_html = self._last_list_html  # 由 _crawl_* 在抓取后写回
    candidate = self._discover_first_detail(rule, list_html or "")
    if candidate:
        detail_html = self._fetch_detail_html(rule, candidate["detail_url"])
        title, blocks = self._extract_detail_blocks(rule, detail_html)
        archive_info = self._maybe_archive_page(
            rule,
            items,
            html=None,
            detail_url=candidate["detail_url"],
            detail_html=detail_html,
            detail_title=title or candidate["title"],
            detail_blocks=blocks,
        )
    else:
        archive_info = {}
else:
    archive_info = self._maybe_archive_page(rule, items, html=None)
```

为了拿到列表 HTML，`_crawl_html`/`_crawl_browser` 在 fetch 之后赋值 `self._last_list_html = html_content`，构造函数中初始化为 `""`。

- [ ] **步骤 5：运行测试确认通过**

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_discovery.py tests/test_archive_engine.py tests/test_rule_v2.py -q
```

预期：全部通过。

---

## 任务 3：回归与提交

- [ ] **步骤 1：本切片回归**

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive.py tests/test_archive_store.py tests/test_archive_engine.py tests/test_archive_discovery.py tests/test_rule_v2.py tests/test_integration.py -q
```

预期：全部通过。

- [ ] **步骤 2：只暂存本切片文件**

```bash
git add APP/engine/engine/engine.py APP/engine/engine/rule_parser.py \
        APP/engine/tests/test_archive_discovery.py APP/engine/tests/test_rule_v2.py \
        docs/superpowers/plans/2026-05-23-page-archive-discovery-loop.md
git status --short
```

预期：仅这五个路径处于 staged。

- [ ] **步骤 3：提交**

```bash
git commit -m "discovery到详情归档最小闭环"
```

---

## 验收标准

- `discovery.enabled` 未配置或为 false 时，归档行为与上一切片完全一致（列表口径）。
- `discovery.enabled=true` 且列表能匹配到候选时：
  - 真实发起一次详情页 HTTP 抓取。
  - 归档对象 `meta.source_url`、`meta.entry_url`、`meta.title` 来自详情页。
  - `blocks` 至少包含 1 个 `heading` + ≥1 个 `paragraph`。
  - 主库写入失败仍会让任务失败。
- discovery 启用但未匹配候选 → `run()` 返回 success，不调用 `save_archive_package`、不调用 `save_archive_page`。
- 测试全部通过且不依赖真实 PostgreSQL 或外部 HTTP。

## 后续切片边界

- 下一切片：列表多条候选的批量详情归档（含 `max_details` 与去重）。
- 再下一切片：详情页图片/附件抓取 + OCR 块入库。
- 最后切片：真实 `ARCHIVE_PG_DSN` 集成验证。

## 自检

- 范围只包含「列表 → 单条详情 → 归档」闭环，未引入翻页、批量、真实 PostgreSQL。
- 复用 `build_archive_page`、`OutputManager.save_archive_package`、`ArchiveStore` 既有接口，未修改其签名。
- 命名一致：`_discover_first_detail`、`_fetch_detail_html`、`_extract_detail_blocks`、`detail_url`、`detail_html`、`detail_blocks`、`archive_page_id`。
