"""列表翻页归档测试。"""

from pathlib import Path

import yaml

from engine.engine import InfoCollectorEngine


LIST_PAGE_1 = """
<html><body>
  <ul class="news-list">
    <li><a href="/detail/1.shtml">高质量数据集名单 一</a></li>
    <li><a href="/detail/2.shtml">高质量数据集名单 二</a></li>
  </ul>
  <a class="next-page" href="/list.shtml?page=2">下一页</a>
</body></html>
"""

LIST_PAGE_2 = """
<html><body>
  <ul class="news-list">
    <li><a href="/detail/3.shtml">高质量数据集名单 三</a></li>
    <li><a href="/detail/4.shtml">高质量数据集名单 四</a></li>
  </ul>
</body></html>
"""

LIST_PAGE_2_WITH_NEXT = """
<html><body>
  <ul class="news-list">
    <li><a href="/detail/3.shtml">高质量数据集名单 三</a></li>
    <li><a href="/detail/4.shtml">高质量数据集名单 四</a></li>
  </ul>
  <a class="next-page" href="/list.shtml?page=3">下一页</a>
</body></html>
"""

LIST_PAGE_3_ONLY = """
<html><body>
  <ul class="news-list">
    <li><a href="/detail/5.shtml">高质量数据集名单 五</a></li>
  </ul>
</body></html>
"""

DETAIL_TEMPLATE = """
<html><body>
  <h1 class="title">详情 {slug}</h1>
  <div class="content"><p>正文 {slug}</p></div>
</body></html>
"""


def _write_rule(tmp_path: Path, *, max_pages: int | None, max_details: int = 10) -> str:
    rule = {
        "name": "pagination-test",
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
        "discovery": {
            "enabled": True,
            "max_details": max_details,
            "list": {
                "items_path": "css:.news-list li",
                "title": {"selector": "a", "type": "text"},
                "detail_url": {"selector": "a", "type": "attribute", "attribute": "href"},
            },
            "filters": {"title_keywords": ["高质量数据集"]},
        },
        "archive": {"enabled": True, "mode": "page_markdown"},
        "dedup": {"incremental": False},
    }
    if max_pages is not None:
        rule["discovery"]["pagination"] = {
            "enabled": True,
            "next_page": {"selector": "a.next-page", "attribute": "href"},
            "max_pages": max_pages,
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
            "page_id": f"page-uuid-{len(self.saved)}",
            "block_ids": {},
            "asset_ids": {},
            "ocr_result_ids": [],
            "structured_record_ids": [],
            "counts": {"pages": 1, "blocks": 0, "assets": 0, "ocr_results": 0, "structured_records": 0},
        }


def _bind_store(monkeypatch, store):
    monkeypatch.setattr(
        "engine.engine.ArchiveStore.from_rule",
        classmethod(lambda cls, rule: store),
    )


def _bind_collection_store(monkeypatch):
    class _CollectionStore:
        def save_run_items(self, **kwargs):
            return {
                "run_id": "run-uuid-1",
                "item_ids": [f"item-{idx}" for idx, _ in enumerate(kwargs.get("items", []), start=1)],
                "governance_record_id": "gov-uuid-1",
            }

    monkeypatch.setattr(
        "engine.engine.CollectionStore.from_project_config",
        classmethod(lambda cls: _CollectionStore()),
    )


def _bind_save_pkg(monkeypatch, engine, tmp_path):
    monkeypatch.setattr(
        engine.output_mgr, "save_archive_package", lambda page, rule: str(tmp_path / "pkg")
    )


def _stub_html(monkeypatch, engine, pages: dict):
    def fake_fetch(url, **kwargs):
        for fragment, html in pages.items():
            if fragment in url:
                return html
        slug = url.rstrip("/").rsplit("/", 1)[-1].replace(".shtml", "")
        return DETAIL_TEMPLATE.format(slug=slug)

    monkeypatch.setattr(engine.html_crawler, "fetch", fake_fetch)


def test_no_pagination_config_fetches_one_page(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, max_pages=None, max_details=10)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine, {"/list.shtml": LIST_PAGE_1})
    _bind_collection_store(monkeypatch)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    result = engine.run(rule_path)

    assert len(store.saved) == 2
    urls = [p["meta"]["source_url"] for p in store.saved]
    assert "https://www.hubei.gov.cn/detail/1.shtml" in urls
    assert "https://www.hubei.gov.cn/detail/2.shtml" in urls
    assert not any("/detail/3" in u for u in urls)


def test_pagination_fetches_second_page(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, max_pages=2, max_details=10)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine, {
        "page=2": LIST_PAGE_2,
        "/list.shtml": LIST_PAGE_1,
    })
    _bind_collection_store(monkeypatch)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    result = engine.run(rule_path)

    assert len(store.saved) == 4
    urls = {p["meta"]["source_url"] for p in store.saved}
    assert "https://www.hubei.gov.cn/detail/3.shtml" in urls
    assert "https://www.hubei.gov.cn/detail/4.shtml" in urls


def test_pagination_respects_max_pages(tmp_path, monkeypatch):
    """max_pages=2 不应跟第 2 页的 next-page 链接去抓第 3 页。"""
    rule_path = _write_rule(tmp_path, max_pages=2, max_details=10)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    # 第 1 页→第 2 页（有 next-page → 第 3 页）；第 3 页含 detail/5
    _stub_html(monkeypatch, engine, {
        "page=2": LIST_PAGE_2_WITH_NEXT,
        "page=3": LIST_PAGE_3_ONLY,
        "/list.shtml": LIST_PAGE_1,
    })
    _bind_collection_store(monkeypatch)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    engine.run(rule_path)

    urls = {p["meta"]["source_url"] for p in store.saved}
    # 第 1 页 detail/1, detail/2 + 第 2 页 detail/3, detail/4 = 4 条
    assert len(store.saved) == 4
    assert not any("/detail/5" in u for u in urls)


def test_pagination_stops_when_no_next_link(tmp_path, monkeypatch):
    """第二页没有 next-page 链接 → 只抓两页，共 4 条归档。"""
    rule_path = _write_rule(tmp_path, max_pages=5, max_details=10)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine, {
        "page=2": LIST_PAGE_2,
        "/list.shtml": LIST_PAGE_1,
    })
    _bind_collection_store(monkeypatch)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    engine.run(rule_path)

    assert len(store.saved) == 4
