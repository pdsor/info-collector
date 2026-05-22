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


def _write_rule(tmp_path: Path, *, discovery: bool = True) -> str:
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
