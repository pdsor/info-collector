"""Rule Health Check API — 检测规则选择器有效性与 DOM 漂移。"""
import hashlib
import json
import os
import sys

import parsel
from flask import Blueprint, jsonify, request

health_bp = Blueprint("health", __name__)

DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.dirname(DASHBOARD_DIR)
ENGINE_DIR = os.path.join(APP_DIR, "engine")
if ENGINE_DIR not in sys.path:
    sys.path.insert(0, ENGINE_DIR)


def _dom_structure_hash(html: str) -> str:
    """提取页面标签序列哈希，用于 DOM 漂移检测。"""
    sel = parsel.Selector(text=html or "")
    tags = [node.root.tag for node in sel.xpath("//*") if isinstance(node.root.tag, str)]
    return hashlib.sha256(" ".join(tags).encode("utf-8")).hexdigest()


def _check_selector(html: str, selector: str) -> dict:
    """执行一个选择器，返回命中数和样本文本。"""
    if not selector or not html:
        return {"hits": 0, "sample": []}
    sel = parsel.Selector(text=html)
    css = selector.removeprefix("css:") if selector.startswith("css:") else selector
    try:
        nodes = sel.css(css)
        hits = len(nodes)
        sample = ["".join(n.xpath("string()").getall()).strip() for n in nodes[:3]]
        sample = [s for s in sample if s]
    except Exception as exc:
        return {"hits": 0, "sample": [], "error": str(exc)}
    return {"hits": hits, "sample": sample}


def _run_health_check(rule: dict, html: str) -> dict:
    """对 rule 的关键选择器集跑健康检测，返回结构化报告。"""
    selectors_to_check = {}

    # list.items_path
    items_path = (rule.get("list") or {}).get("items_path")
    if items_path:
        selectors_to_check["list.items_path"] = items_path

    # extract fields
    for field, defn in (rule.get("extract") or {}).items():
        if isinstance(defn, dict) and defn.get("selector"):
            selectors_to_check[f"extract.{field}"] = defn["selector"]

    # discovery.list selectors
    disc_list = (rule.get("discovery") or {}).get("list") or {}
    for key in ("title", "detail_url"):
        sel = (disc_list.get(key) or {}).get("selector")
        if sel:
            selectors_to_check[f"discovery.list.{key}"] = sel

    results = {}
    total_hits = 0
    total_selectors = len(selectors_to_check)
    working = 0
    for name, sel in selectors_to_check.items():
        r = _check_selector(html, sel)
        results[name] = r
        if r["hits"] > 0:
            working += 1
            total_hits += r["hits"]

    health_score = round(working / total_selectors, 4) if total_selectors else 1.0
    dom_hash = _dom_structure_hash(html)

    return {
        "health_score": health_score,
        "working_selectors": working,
        "total_selectors": total_selectors,
        "dom_structure_hash": dom_hash,
        "selectors": results,
    }


@health_bp.route("/check", methods=["POST"])
def health_check():
    """POST /api/health/check

    Body JSON:
      { "rule": <rule dict>, "html": "<page html>" }
    or
      { "rule": <rule dict> }  — 则系统自行抓取 rule.source.url

    返回每个关键选择器的命中数、健康分和 DOM 结构哈希。
    """
    body = request.get_json(silent=True) or {}
    rule = body.get("rule")
    if not rule:
        return jsonify({"error": "rule is required"}), 400

    html = body.get("html")
    if not html:
        # 尝试自行抓取
        source_url = (rule.get("source") or {}).get("url")
        if not source_url:
            return jsonify({"error": "rule.source.url or html is required"}), 400
        try:
            from engine.crawl_html import HTMLCrawler
            html = HTMLCrawler().fetch(source_url)
        except Exception as exc:
            return jsonify({"error": f"fetch failed: {exc}"}), 502

    report = _run_health_check(rule, html)
    return jsonify(report)
