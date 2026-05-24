"""规则试采 API 测试。"""

import os
import sys


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../engine")))

from APP.dashboard.server import app


def test_preview_rule_rejects_empty_yaml():
    """空 YAML 不能试采。"""
    client = app.test_client()

    response = client.post("/api/rules/preview", json={"yaml": ""})

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_preview_rule_accepts_unsaved_yaml(monkeypatch):
    """未保存的编辑器 YAML 可以直接试采。"""
    from engine import crawl_html

    class FakeResponse:
        text = "<article><h1>沙箱</h1></article>"
        apparent_encoding = "utf-8"
        encoding = "utf-8"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(crawl_html.requests, "get", lambda *args, **kwargs: FakeResponse())

    yaml_content = """
rule_id: "preview-api-rule"
source_id: "preview-api-source"
version: 1
status: DRAFT
source:
  platform: "preview-api"
  type: "html"
  url: "https://example.com"
list:
  items_path: "css:article"
extract:
  title: { selector: "h1", type: "text" }
output:
  fields: ["title"]
  save_raw: false
governance:
  sanitize: true
""".strip()
    client = app.test_client()

    response = client.post("/api/rules/preview", json={"yaml": yaml_content, "limit": 5})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["items"][0]["title"] == "沙箱"


def test_preview_rule_response_contains_ocr_summary(monkeypatch):
    """规则试采 API 返回 OCR 摘要字段。"""
    from engine import crawl_html

    class FakeResponse:
        text = "<article><h1>沙箱</h1></article>"
        apparent_encoding = "utf-8"
        encoding = "utf-8"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(crawl_html.requests, "get", lambda *args, **kwargs: FakeResponse())

    yaml_content = """
rule_id: "preview-api-rule"
source_id: "preview-api-source"
version: 1
status: DRAFT
source:
  platform: "preview-api"
  type: "html"
  url: "https://example.com"
list:
  items_path: "css:article"
extract:
  title: { selector: "h1", type: "text" }
output:
  fields: ["title"]
  save_raw: false
governance:
  sanitize: true
""".strip()
    client = app.test_client()

    response = client.post("/api/rules/preview", json={"yaml": yaml_content, "limit": 5})

    assert response.status_code == 200
    assert response.get_json()["ocr_summary"] == {}
