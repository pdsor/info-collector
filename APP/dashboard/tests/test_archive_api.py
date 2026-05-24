"""Archive Center API 测试。"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../engine")))

from APP.dashboard.server import app

SAMPLE_PAGE = {
    "meta": {
        "content_hash": "abc123",
        "title": "测试归档页",
        "source_url": "https://example.com/detail/1.html",
        "domain": "example.com",
        "platform": "example",
        "subject": "数据要素",
        "fetched_at": "2026-05-24T10:00:00",
        "contains_ocr": True,
        "contains_table": False,
        "requires_structuring": True,
    },
    "blocks": [
        {"id": "b1", "block_type": "heading", "block_order": 1, "text": "测试标题"},
        {"id": "b2", "block_type": "paragraph", "block_order": 2, "text": "正文段落"},
        {"id": "b3", "block_type": "ocr", "block_order": 3, "ocr_text": "序号 名称\n1 数据集A"},
    ],
    "assets": [],
    "paths": {},
}


def _write_package(tmp_path, content_hash="abc123", page=None):
    pkg_dir = tmp_path / "数据要素" / "example" / "archives" / content_hash
    pkg_dir.mkdir(parents=True, exist_ok=True)
    page_data = page if page is not None else SAMPLE_PAGE
    (pkg_dir / "page.json").write_text(json.dumps(page_data, ensure_ascii=False), encoding="utf-8")
    return pkg_dir


def test_list_archives_empty(monkeypatch, tmp_path):
    monkeypatch.setattr("APP.dashboard.apis.archive_api.OUTPUT_DIR", str(tmp_path))
    client = app.test_client()
    resp = client.get("/api/archives")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["pages"] == []
    assert data["total"] == 0


def test_list_archives_returns_summaries(monkeypatch, tmp_path):
    _write_package(tmp_path)
    monkeypatch.setattr("APP.dashboard.apis.archive_api.OUTPUT_DIR", str(tmp_path))
    client = app.test_client()
    resp = client.get("/api/archives")
    assert resp.status_code == 200
    pages = resp.get_json()["pages"]
    assert len(pages) == 1
    p = pages[0]
    assert p["content_hash"] == "abc123"
    assert p["title"] == "测试归档页"
    assert p["contains_ocr"] is True
    assert p["block_count"] == 3
    assert p["ocr_block_count"] == 1


def test_get_archive_not_found(monkeypatch, tmp_path):
    monkeypatch.setattr("APP.dashboard.apis.archive_api.OUTPUT_DIR", str(tmp_path))
    client = app.test_client()
    resp = client.get("/api/archives/nonexistent")
    assert resp.status_code == 404


def test_get_archive_returns_blocks(monkeypatch, tmp_path):
    _write_package(tmp_path)
    monkeypatch.setattr("APP.dashboard.apis.archive_api.OUTPUT_DIR", str(tmp_path))
    client = app.test_client()
    resp = client.get("/api/archives/abc123")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["meta"]["title"] == "测试归档页"
    assert len(data["blocks"]) == 3
    assert data["blocks"][2]["block_type"] == "ocr"
    assert data["structured_records"] == []


def test_get_archive_loads_structured_records_sidecar(monkeypatch, tmp_path):
    pkg_dir = _write_package(tmp_path)
    sr = [{"record_type": "dataset_row", "data": {"序号": "1", "名称": "数据集A"}, "raw_columns": ["1", "数据集A"]}]
    (pkg_dir / "structured_records.json").write_text(json.dumps(sr, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr("APP.dashboard.apis.archive_api.OUTPUT_DIR", str(tmp_path))
    client = app.test_client()
    resp = client.get("/api/archives/abc123")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["structured_records"]) == 1
    assert data["structured_records"][0]["data"]["名称"] == "数据集A"
