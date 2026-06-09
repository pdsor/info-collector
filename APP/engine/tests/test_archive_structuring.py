"""OCR 精抽 → structured_records 测试。"""

from pathlib import Path

import yaml

from engine.engine import InfoCollectorEngine


LIST_HTML = """
<html><body>
  <ul class="news-list">
    <li><a href="/detail/1.shtml">高质量数据集名单公示</a></li>
  </ul>
</body></html>
"""

# 包含表格式OCR文本的详情页
DETAIL_HTML = """
<html><body>
  <h1 class="title">第三批高质量数据集名单</h1>
  <div class="content">
    <p>现将名单公示如下。</p>
    <img src="/assets/table.png" alt="名单表格">
  </div>
</body></html>
"""

OCR_TABLE_TEXT = """第三批湖北省高质量数据集名单
序号 数据集名称 申报单位
1 城市地理数据集 武汉市自然资源局
2 医疗健康数据集 湖北省卫生健康委员会
3 工业传感器数据集 武汉钢铁有限公司"""

OCR_NONTABLE_TEXT = "这是一段普通正文，不包含表格结构。"


def _write_rule(tmp_path: Path, *, structuring: bool, keywords=None) -> str:
    rule = {
        "name": "structuring-test",
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
        },
        "archive": {
            "enabled": True,
            "mode": "page_markdown",
            "image_ocr": {
                "enabled": True,
                "images": {"selector": ".content img"},
                "ocr": {"plugin": "tesseract", "languages": ["chi_sim"]},
            },
        },
        "dedup": {"incremental": False},
    }
    if structuring:
        kws = keywords or ["数据集名称", "申报单位"]
        rule["structuring"] = {
            "enabled": True,
            "strategies": [
                {
                    "record_type": "dataset_row",
                    "applies_to": {
                        "block_types": ["ocr"],
                        "keywords": kws,
                    },
                }
            ],
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
            "structured_record_ids": [],
            "counts": {
                "pages": 1,
                "blocks": len(archive_page.get("blocks", [])),
                "assets": 0,
                "ocr_results": 0,
                "structured_records": len(archive_page.get("structured_records", [])),
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
    monkeypatch.setattr(
        engine.output_mgr, "save_archive_package", lambda page, rule: str(tmp_path / "pkg")
    )


def _bind_ocr(monkeypatch, ocr_text):
    from dataclasses import dataclass

    @dataclass
    class _FakeResult:
        plugin: str = "tesseract"
        status: str = "success"
        text: str = ocr_text
        error: str = ""
        elapsed_seconds: float = 0.0
        structured_data: dict | None = None

        @property
        def empty(self):
            return self.text.strip() == ""

        @property
        def manual_review_required(self):
            return self.status != "success" or self.empty

    class _FakePlugin:
        def recognize(self, path, cfg):
            return _FakeResult()

    monkeypatch.setattr("engine.engine.get_ocr_plugin", lambda name: _FakePlugin())

    def fake_download(url, cfg):
        from pathlib import Path
        p = Path("/tmp/fake_img.png")
        p.write_bytes(b"\x89PNG")
        return str(p)

    monkeypatch.setattr("engine.engine._download_image_for_archive", fake_download)


def _stub_html(monkeypatch, engine):
    def fake_fetch(url, **kwargs):
        if url.endswith("/list.shtml"):
            return LIST_HTML
        return DETAIL_HTML

    monkeypatch.setattr(engine.html_crawler, "fetch", fake_fetch)


def test_structuring_disabled_no_structured_records(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, structuring=False)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine)
    _bind_collection_store(monkeypatch)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    _bind_ocr(monkeypatch, OCR_TABLE_TEXT)
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    engine.run(rule_path)

    archived = store.saved[0]
    assert archived.get("structured_records") in (None, [])


def test_structuring_enabled_parses_ocr_table(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, structuring=True)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine)
    _bind_collection_store(monkeypatch)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    _bind_ocr(monkeypatch, OCR_TABLE_TEXT)
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    result = engine.run(rule_path)

    assert result["archive_page_id"] == "page-uuid-1"
    archived = store.saved[0]
    records = archived.get("structured_records") or []
    assert len(records) == 3
    assert records[0]["record_type"] == "dataset_row"
    assert records[0]["data"]["序号"] == "1"
    assert records[0]["data"]["数据集名称"] == "城市地理数据集"
    assert records[0]["data"]["申报单位"] == "武汉市自然资源局"
    assert records[0]["source_block_id"] is not None
    assert len(records[0]["raw_columns"]) >= 3


def test_structuring_skips_no_keyword_match(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, structuring=True)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine)
    _bind_collection_store(monkeypatch)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    _bind_ocr(monkeypatch, OCR_NONTABLE_TEXT)
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    engine.run(rule_path)

    archived = store.saved[0]
    records = archived.get("structured_records") or []
    assert records == []


def test_structuring_run_count_in_result(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, structuring=True)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine)
    _bind_collection_store(monkeypatch)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    _bind_ocr(monkeypatch, OCR_TABLE_TEXT)
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    result = engine.run(rule_path)

    pages = result.get("archive_pages") or []
    assert len(pages) == 1
    # structured_records count exposed via store mock
    archived = store.saved[0]
    assert len(archived.get("structured_records") or []) == 3
