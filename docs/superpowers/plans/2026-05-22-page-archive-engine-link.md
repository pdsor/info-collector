# 页面归档接入采集执行链路实现计划

> **面向代理工作者：** 执行本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 在不大改 `APP/engine/engine/engine.py` 的前提下，让 `archive.enabled=true` 的规则在执行结束时基于规则执行结果组装 `archive_page`，并依次调用 `OutputManager.save_archive_package()`（输出归档调试包）和 `ArchiveStore.save_archive_page()`（写入主库），最终在 `run()` 返回结果中暴露 `archive_page_id` 与 `archive_package_path`。

**架构：** 本切片只覆盖“规则执行结束后的归档接入”。`archive.enabled` 未配置或为 false 时行为完全不变；为 true 时在 `run()` 末尾追加归档分支，包含三步：
1. 用规则字段 + 当前执行采集到的 `items`、`html`、`url` 组装一个最小化 `archive_page`（依赖现有 `build_archive_page`）。
2. 调用 `output_mgr.save_archive_package()` 落盘调试包，记录 `archive_package_path`。
3. 调用 `ArchiveStore.from_rule(rule).save_archive_page()` 写主库，记录 `archive_page_id`。

主库写入失败需要把整条任务结果标记为失败，不能静默吞掉异常；测试通过伪连接和伪 store 保证不依赖真实 PostgreSQL。

**技术栈：** Python、pytest、现有 `InfoCollectorEngine`、`OutputManager`、`ArchiveStore`、`build_archive_page`、Rule v2 YAML。

---

## 文件结构

- 修改：`APP/engine/engine/engine.py`
  - 在 `run()` 主流程末尾新增 `_maybe_archive_page()` 调用。
  - 新增 `_maybe_archive_page()` 私有方法：判断 `archive.enabled`、组装 `archive_page`、调用输出包、调用主库写入、返回 `(archive_page_id, archive_package_path)`。
  - 主库写入异常时抛出，让 `run()` 既有的 `except Exception` 把任务标记为失败。
- 修改：`APP/engine/engine/archive.py`（如需要少量调整）
  - 仅在 `build_archive_page` 缺少“从 items + html 构造默认 blocks”这种轻量便利能力时再补充。本切片不改变其签名。
- 新增：`APP/engine/tests/test_archive_engine.py`
  - 三个用例：未配置不归档、`enabled=true` 成功归档、主库失败让任务失败。
  - 通过 monkeypatch 替换 `OutputManager.save_archive_package`、`InfoCollectorEngine._maybe_archive_page` 的依赖，使用伪 store/伪 connection 而非真实 PostgreSQL。
- 不修改：`APP/engine/engine/archive_store.py`
  - 本切片复用已落地的 `ArchiveStore.save_archive_page()`、`ArchiveStore.from_rule()`。
- 不修改：`APP/engine/engine/output.py`
  - 本切片复用已落地的 `save_archive_package()`。
- 不引入：列表页 discovery、详情页批量循环、真实 PostgreSQL 连接。

---

## 任务 1：为归档接入定义失败测试

**文件：**
- 新增：`APP/engine/tests/test_archive_engine.py`

- [ ] **步骤 1：编写测试骨架**

新建 `APP/engine/tests/test_archive_engine.py`：

```python
"""归档接入采集执行链路测试。

只验证 InfoCollectorEngine.run() 在 archive.enabled 的三种状态下的行为，
不依赖真实 PostgreSQL，也不触发 discovery / 列表页闭环。
"""

import os
from pathlib import Path

import pytest

from engine.engine import InfoCollectorEngine


def _write_rule(tmp_path: Path, archive_block: dict | None) -> str:
    """生成最小 NG v2 规则文件：直接走 HTML 抓取，不依赖网络。"""
    import yaml

    rule = {
        "rule_id": "archive-link-test",
        "source_id": "archive-link-source",
        "name": "归档接入回归",
        "version": 1,
        "subject": "数据要素",
        "source": {
            "type": "html",
            "platform": "hubei_gov",
            "url": "https://www.hubei.gov.cn/a.shtml",
            "client": "desktop",
        },
        "list": {
            "items_path": "css:.news-list li",
            "fields": [
                {"name": "title", "type": "element_text"},
                {"name": "url", "type": "element_href"},
            ],
        },
        "dedup": {"incremental": False},
    }
    if archive_block is not None:
        rule["archive"] = archive_block

    path = tmp_path / "rule.yaml"
    path.write_text(yaml.safe_dump(rule, allow_unicode=True), encoding="utf-8")
    return str(path)


def _stub_engine_pipeline(monkeypatch, engine: InfoCollectorEngine, items: list[dict]) -> None:
    """把 crawl 和 save 桩成可控行为，专注验证归档分支。"""
    monkeypatch.setattr(engine, "crawl", lambda rule: list(items))
    monkeypatch.setattr(engine, "save_output", lambda *args, **kwargs: "")


def test_archive_not_enabled_does_not_trigger_archive(tmp_path, monkeypatch):
    """archive.enabled 未配置或为 false 时，run() 不应触发归档分支。"""
    rule_path = _write_rule(tmp_path, archive_block=None)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_engine_pipeline(monkeypatch, engine, items=[{"title": "x", "url": "https://x"}])

    save_called = {"count": 0}

    def _fail_save_archive_package(*args, **kwargs):
        save_called["count"] += 1
        raise AssertionError("不应调用 save_archive_package")

    monkeypatch.setattr(engine.output_mgr, "save_archive_package", _fail_save_archive_package)

    result = engine.run(rule_path)

    assert result["status"] in {"success", "partial_success"}
    assert "archive_page_id" not in result
    assert "archive_package_path" not in result
    assert save_called["count"] == 0


def test_archive_enabled_writes_package_and_main_store(tmp_path, monkeypatch):
    """archive.enabled=true 时，run() 应落盘归档包并写入主库。"""
    rule_path = _write_rule(
        tmp_path,
        archive_block={
            "enabled": True,
            "mode": "page_markdown",
            "markdown": {"enabled": True},
        },
    )
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_engine_pipeline(
        monkeypatch,
        engine,
        items=[{"title": "归档样例", "url": "https://www.hubei.gov.cn/a.shtml"}],
    )

    monkeypatch.setattr(
        engine.output_mgr,
        "save_archive_package",
        lambda archive_page, rule: str(tmp_path / "fake-package"),
    )

    class FakeStore:
        def __init__(self):
            self.saved = []

        def save_archive_page(self, archive_page):
            self.saved.append(archive_page)
            return {
                "page_id": "page-uuid-1",
                "block_ids": {},
                "asset_ids": {},
                "ocr_result_ids": [],
                "counts": {"pages": 1, "blocks": 0, "assets": 0, "ocr_results": 0},
            }

    fake_store = FakeStore()
    monkeypatch.setattr(
        "engine.engine.ArchiveStore.from_rule",
        classmethod(lambda cls, rule: fake_store),
    )

    result = engine.run(rule_path)

    assert result["status"] in {"success", "partial_success"}
    assert result["archive_page_id"] == "page-uuid-1"
    assert result["archive_package_path"] == str(tmp_path / "fake-package")
    assert len(fake_store.saved) == 1
    assert "meta" in fake_store.saved[0]


def test_archive_store_failure_marks_task_failed(tmp_path, monkeypatch):
    """主库写入失败时，run() 应返回 failed，不静默吞掉异常。"""
    rule_path = _write_rule(
        tmp_path,
        archive_block={"enabled": True, "mode": "page_markdown"},
    )
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_engine_pipeline(
        monkeypatch,
        engine,
        items=[{"title": "归档样例", "url": "https://www.hubei.gov.cn/a.shtml"}],
    )
    monkeypatch.setattr(
        engine.output_mgr,
        "save_archive_package",
        lambda archive_page, rule: str(tmp_path / "fake-package"),
    )

    class BrokenStore:
        def save_archive_page(self, archive_page):
            raise RuntimeError("模拟主库写入失败")

    monkeypatch.setattr(
        "engine.engine.ArchiveStore.from_rule",
        classmethod(lambda cls, rule: BrokenStore()),
    )

    result = engine.run(rule_path)

    assert result["status"] == "failed"
    assert "模拟主库写入失败" in result.get("error", "")
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_engine.py -q
```

预期：失败，提示 `engine.engine.ArchiveStore` 未导入，或 `run()` 结果中没有 `archive_page_id`、`archive_package_path` 字段。

---

## 任务 2：在 engine.py 接入归档分支

**文件：**
- 修改：`APP/engine/engine/engine.py`

- [ ] **步骤 1：在模块顶部导入归档依赖**

在 `from .image_extraction import ImageExtractionRunner` 附近补充：

```python
from datetime import datetime, timezone
from urllib.parse import urlparse

from .archive import build_archive_page
from .archive_store import ArchiveStore
```

注意：保持现有 import 顺序，新增 import 紧邻已有同类引用，不重排其它行。

- [ ] **步骤 2：新增 `_maybe_archive_page()` 私有方法**

在 `InfoCollectorEngine` 内（建议放在 `save_output()` 之后、`preview_rule()` 之前）新增：

```python
def _maybe_archive_page(self, rule: dict, items: list, html: str | None) -> dict:
    """如果规则配置了 archive.enabled=true，组装并写出归档包与主库记录。

    Returns:
        包含 ``archive_page_id`` 和 ``archive_package_path`` 的字典；
        若未启用归档，返回空字典。
    """
    archive_cfg = rule.get("archive") or {}
    if not archive_cfg.get("enabled"):
        return {}

    source = rule.get("source", {}) or {}
    source_url = source.get("url", "")
    domain = urlparse(source_url).netloc or source.get("platform", "")
    title = ""
    if items:
        first = items[0]
        if isinstance(first, dict):
            title = first.get("title") or ""

    archive_page = build_archive_page(
        source_url=source_url,
        entry_url=source_url,
        final_url=source_url,
        domain=domain,
        platform=source.get("platform"),
        subject=rule.get("subject") or source.get("subject"),
        title=title,
        source_name=source.get("source_name"),
        publish_time=None,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        html=html or "",
        markdown="",
        blocks=[],
        assets=[],
    )

    package_path = self.output_mgr.save_archive_package(archive_page, rule)
    store = ArchiveStore.from_rule(rule)
    write_result = store.save_archive_page(archive_page)

    return {
        "archive_page_id": write_result.get("page_id"),
        "archive_package_path": package_path,
    }
```

说明：本切片只组装“最小可写”归档对象——blocks/assets 暂时留空，等下一切片接入 discovery/详情页时再补。`html` 暂未在 `run()` 中透传，本切片先按 `""` 传入即可，保证字段完整、`content_hash` 仍可计算。

- [ ] **步骤 3：在 `run()` 成功分支调用 `_maybe_archive_page()`**

在 `run()` 中 `save_output(...)` 之后、`state_mgr.record_finish(...)` 之前插入：

```python
archive_info = self._maybe_archive_page(rule, items, html=None)
```

并在 `result = {...}` 字典构建后追加：

```python
if archive_info:
    result.update(archive_info)
```

不要把归档写入放在 `except` 之外吞掉异常：`_maybe_archive_page` 抛出的任何 `Exception` 都应由 `run()` 现有的 `except Exception` 分支接住，被记录为任务失败。

- [ ] **步骤 4：运行新切片测试**

运行：

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_engine.py -q
```

预期：三条测试全部通过。

---

## 任务 3：本切片回归与提交

**文件：**
- 修改：`APP/engine/engine/engine.py`
- 新增：`APP/engine/tests/test_archive_engine.py`

- [ ] **步骤 1：运行归档与存储回归**

运行：

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive.py tests/test_archive_store.py -q
```

预期：全部通过，旧契约不受影响。

- [ ] **步骤 2：运行集成回归**

运行：

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_integration.py -q
```

预期：全部通过；未配置 `archive` 的规则不应触发归档分支。

- [ ] **步骤 3：运行本切片测试**

运行：

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_engine.py -q
```

预期：全部通过。

- [ ] **步骤 4：检查工作树只包含本切片变更**

运行：

```bash
git status --short
```

预期：变更集合为 `APP/engine/engine/engine.py`、`APP/engine/tests/test_archive_engine.py`、`docs/superpowers/plans/2026-05-22-page-archive-engine-link.md`。如有非本切片变更，分开暂存。

- [ ] **步骤 5：提交**

运行：

```bash
git add APP/engine/engine/engine.py APP/engine/tests/test_archive_engine.py docs/superpowers/plans/2026-05-22-page-archive-engine-link.md
git commit -m "接入页面归档到采集执行链路"
```

预期：生成一个中文 commit message 的提交。

---

## 验收标准

- 普通规则（未配置 `archive` 或 `archive.enabled=false`）行为完全不变。
- `archive.enabled=true` 时 `run()` 返回值新增 `archive_page_id` 和 `archive_package_path` 摘要字段。
- 主库写入失败时任务结果 `status=="failed"`，错误信息可见，不被静默吞掉。
- 测试仅依赖伪 store / monkeypatch 的伪 connection，不连真实 PostgreSQL。

## 后续切片边界

- 下一切片：列表页 discovery 到详情页 archive 的单页最小闭环（含详情页 HTML 抓取、blocks/assets 组装）。
- 再下一切片：批量翻页与多详情页归档。
- 最后切片：使用 `ARCHIVE_PG_DSN` 做真实 PostgreSQL 集成验证。

## 自检

- 需求覆盖：本切片只接入“执行链路末尾的归档输出与主库写入”，未引入 discovery、批量闭环或真实 PostgreSQL。
- 占位检查：无 TODO/TBD/留空步骤。
- 类型一致性：所有引用统一为 `build_archive_page`、`OutputManager.save_archive_package`、`ArchiveStore.from_rule`、`ArchiveStore.save_archive_page`、`archive_page_id`、`archive_package_path`。
