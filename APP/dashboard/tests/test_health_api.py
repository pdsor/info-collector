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
    """不同结构的页面应产生不同的 DOM 结构哈希。"""
    html_v2 = """
    <html><body>
      <div class="article-list">
        <article><h2>新闻标题</h2></article>
      </div>
    </body></html>
    """
    client = app.test_client()
    r1 = client.post("/api/health/check", json={"rule": RULE, "html": SAMPLE_HTML}).get_json()
    r2 = client.post("/api/health/check", json={"rule": RULE, "html": html_v2}).get_json()
    assert r1["dom_structure_hash"] != r2["dom_structure_hash"]


def test_health_check_requires_rule():
    client = app.test_client()
    resp = client.post("/api/health/check", json={"html": SAMPLE_HTML})
    assert resp.status_code == 400


def test_health_check_empty_rule_selectors_returns_full_score():
    """规则没有声明任何选择器时，健康分为 1.0（无可测项）。"""
    empty_rule = {"name": "empty", "source": {"url": "https://x.com"}}
    client = app.test_client()
    resp = client.post("/api/health/check", json={"rule": empty_rule, "html": SAMPLE_HTML})
    assert resp.status_code == 200
    assert resp.get_json()["health_score"] == 1.0
