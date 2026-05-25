"""规则健康度检测 API 测试。"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../engine")))

from APP.dashboard.server import app

SAMPLE_HTML = """
<html><body>
  <ul class="news-list">
    <li><a href="/detail/1.html">第一批高质量数据集名单</a></li>
    <li><a href="/detail/2.html">第二批高质量数据集名单</a></li>
  </ul>
</body></html>
"""

HTML_V2 = """
<html><body>
  <div class="article-list">
    <article><h2>新闻标题</h2></article>
  </div>
</body></html>
"""

RULE = {
    "name": "test",
    "source": {"type": "html", "platform": "example", "url": "https://example.com/list"},
    "list": {"items_path": "css:.news-list li"},
    "extract": {"title": {"selector": "a", "type": "text"}},
}


def test_health_check_all_selectors_hit():
    client = app.test_client()
    resp = client.post("/api/health/check", json={"rule": RULE, "html": SAMPLE_HTML})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["health_score"] == 1.0
    assert data["working_selectors"] == data["total_selectors"]
    assert data["selectors"]["list.items_path"]["hits"] == 2
    assert data["selectors"]["extract.title"]["hits"] == 2
    assert data["dom_structure_hash"]


def test_health_check_broken_selector_lowers_score():
    broken_rule = {
        **RULE,
        "extract": {"title": {"selector": "div.nonexistent", "type": "text"}},
    }
    client = app.test_client()
    resp = client.post("/api/health/check", json={"rule": broken_rule, "html": SAMPLE_HTML})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["health_score"] < 1.0
    assert data["selectors"]["extract.title"]["hits"] == 0


def test_health_check_dom_hash_changes_on_restructure():
    client = app.test_client()
    r1 = client.post("/api/health/check", json={"rule": RULE, "html": SAMPLE_HTML}).get_json()
    r2 = client.post("/api/health/check", json={"rule": RULE, "html": HTML_V2}).get_json()
    assert r1["dom_structure_hash"] != r2["dom_structure_hash"]


def test_health_check_requires_rule():
    client = app.test_client()
    resp = client.post("/api/health/check", json={"html": SAMPLE_HTML})
    assert resp.status_code == 400


def test_health_check_empty_rule_selectors_returns_full_score():
    empty_rule = {"name": "empty", "source": {"url": "https://x.com"}}
    client = app.test_client()
    resp = client.post("/api/health/check", json={"rule": empty_rule, "html": SAMPLE_HTML})
    assert resp.status_code == 200
    assert resp.get_json()["health_score"] == 1.0


def test_set_baseline_stores_dom_hash(tmp_path, monkeypatch):
    import APP.dashboard.apis.health_api as ha
    monkeypatch.setattr(ha, "ENGINE_DIR", str(tmp_path))
    client = app.test_client()
    rule_path = "rules/test_rule.yaml"
    resp = client.post("/api/health/set-baseline", json={"rule_path": rule_path, "html": SAMPLE_HTML})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["dom_baseline_hash"]
    sidecar_path = os.path.join(str(tmp_path), rule_path + ".health.json")
    assert os.path.exists(sidecar_path)
    with open(sidecar_path) as f:
        saved = json.load(f)
    assert saved["dom_baseline_hash"] == data["dom_baseline_hash"]


def test_health_check_detects_dom_drift(tmp_path, monkeypatch):
    import APP.dashboard.apis.health_api as ha
    monkeypatch.setattr(ha, "ENGINE_DIR", str(tmp_path))
    client = app.test_client()
    rule_path = "rules/drift_rule.yaml"
    # Set baseline with SAMPLE_HTML
    client.post("/api/health/set-baseline", json={"rule_path": rule_path, "html": SAMPLE_HTML})
    # Check with different HTML → drift detected
    resp = client.post("/api/health/check", json={"rule": RULE, "html": HTML_V2, "rule_path": rule_path})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["dom_drifted"] is True
    assert data["baseline_set_at"] is not None


def test_health_check_no_drift_when_html_unchanged(tmp_path, monkeypatch):
    import APP.dashboard.apis.health_api as ha
    monkeypatch.setattr(ha, "ENGINE_DIR", str(tmp_path))
    client = app.test_client()
    rule_path = "rules/nodrift_rule.yaml"
    client.post("/api/health/set-baseline", json={"rule_path": rule_path, "html": SAMPLE_HTML})
    resp = client.post("/api/health/check", json={"rule": RULE, "html": SAMPLE_HTML, "rule_path": rule_path})
    data = resp.get_json()
    assert data["dom_drifted"] is False
