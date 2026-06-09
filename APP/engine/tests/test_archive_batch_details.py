"""列表多候选批量详情归档测试。"""

from pathlib import Path

import yaml

from engine.engine import InfoCollectorEngine


LIST_HTML_FIVE = """
<html><body>
  <ul class="news-list">
    <li><a href="/detail/1.shtml">高质量数据集名单 一</a></li>
    <li><a href="/detail/2.shtml">高质量数据集名单 二</a></li>
    <li><a href="/detail/3.shtml">高质量数据集名单 三</a></li>
    <li><a href="/detail/4.shtml">高质量数据集名单 四</a></li>
    <li><a href="/detail/5.shtml">高质量数据集名单 五</a></li>
  </ul>
</body></html>
"""

LIST_HTML_DUPLICATES = """
<html><body>
  <ul class="news-list">
    <li><a href="/detail/1.shtml">高质量数据集名单 一</a></li>
    <li><a href="/detail/1.shtml">高质量数据集名单 一</a></li>
    <li><a href="/detail/2.shtml">高质量数据集名单 二</a></li>
  </ul>
</body></html>
"""

DETAIL_HTML_TEMPLATE = """
<html><body>
  <h1 class="title">{title}</h1>
  <div class="content"><p>{body}</p></div>
</body></html>
"""


def _write_rule(tmp_path: Path, *, max_details: int | None) -> str:
    rule = {
        "name": "batch-detail",
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
    if max_details is not None:
        rule["discovery"]["max_details"] = max_details
    path = tmp_path / "rule.yaml"
    path.write_text(yaml.safe_dump(rule, allow_unicode=True), encoding="utf-8")
    return str(path)


class _RecordingStore:
    def __init__(self):
        self.saved = []

    def save_archive_page(self, archive_page):
        self.saved.append(archive_page)
        idx = len(self.saved)
        return {
            "page_id": f"page-uuid-{idx}",
            "block_ids": {},
            "asset_ids": {},
            "ocr_result_ids": [],
            "counts": {
                "pages": 1,
                "blocks": len(archive_page.get("blocks", [])),
                "assets": 0,
                "ocr_results": 0,
            },
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
    counter = {"n": 0}

    def fake_save(page, rule):
        counter["n"] += 1
        return str(tmp_path / f"pkg-{counter['n']}")

    monkeypatch.setattr(engine.output_mgr, "save_archive_package", fake_save)


def _stub_html(monkeypatch, engine, list_html, detail_factory):
    def fake_fetch(url, **kwargs):
        if url.endswith("/list.shtml"):
            return list_html
        return detail_factory(url)

    monkeypatch.setattr(engine.html_crawler, "fetch", fake_fetch)


def _distinct_detail(url):
    return DETAIL_HTML_TEMPLATE.format(title=f"标题 {url}", body=f"正文 {url}")


def test_default_max_details_is_unlimited(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, max_details=None)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine, LIST_HTML_FIVE, _distinct_detail)
    _bind_collection_store(monkeypatch)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    result = engine.run(rule_path)

    assert len(store.saved) == 5
    assert result["archive_page_id"] == "page-uuid-1"


def test_max_details_limits_archives(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, max_details=3)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine, LIST_HTML_FIVE, _distinct_detail)
    _bind_collection_store(monkeypatch)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    result = engine.run(rule_path)

    assert len(store.saved) == 3
    assert len(result["archive_pages"]) == 3
    urls = [p["source_url"] for p in result["archive_pages"]]
    assert urls == [
        "https://www.hubei.gov.cn/detail/1.shtml",
        "https://www.hubei.gov.cn/detail/2.shtml",
        "https://www.hubei.gov.cn/detail/3.shtml",
    ]


def test_url_dedup_skips_duplicate_link(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, max_details=5)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine, LIST_HTML_DUPLICATES, _distinct_detail)
    _bind_collection_store(monkeypatch)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    result = engine.run(rule_path)

    assert len(store.saved) == 2
    urls = [p["source_url"] for p in result["archive_pages"]]
    assert urls == [
        "https://www.hubei.gov.cn/detail/1.shtml",
        "https://www.hubei.gov.cn/detail/2.shtml",
    ]


def test_content_hash_dedup_skips_same_payload(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, max_details=5)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    identical = DETAIL_HTML_TEMPLATE.format(title="一致标题", body="一致正文")
    _stub_html(monkeypatch, engine, LIST_HTML_FIVE, lambda url: identical)
    _bind_collection_store(monkeypatch)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    result = engine.run(rule_path)

    assert len(store.saved) == 1
    assert len(result["archive_pages"]) == 1
    assert result["archive_pages"][0]["source_url"] == "https://www.hubei.gov.cn/detail/1.shtml"
