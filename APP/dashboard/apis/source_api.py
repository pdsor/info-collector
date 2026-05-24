"""Source Center API。"""
import json
import os
import sqlite3
from urllib.parse import urlparse

import yaml
from flask import Blueprint, jsonify

sources_bp = Blueprint("sources", __name__)

DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.dirname(DASHBOARD_DIR)
ENGINE_DIR = os.path.join(APP_DIR, "engine")
RULES_DIR = os.path.join(ENGINE_DIR, "rules")
DB_PATH = os.path.join(DASHBOARD_DIR, "dashboard.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _iter_rule_files():
    for root, dirs, files in os.walk(RULES_DIR):
        dirs.sort()
        for fname in sorted(files):
            if fname.endswith((".yaml", ".yml")):
                yield os.path.join(root, fname)


def _source_id(rule: dict, path: str) -> str:
    return str(rule.get("source_id") or rule.get("source", {}).get("id") or os.path.relpath(path, ENGINE_DIR))


def _domain_from_rule(rule: dict) -> str:
    source = rule.get("source") or {}
    url = source.get("url") or source.get("base_url") or ""
    return urlparse(url).netloc


def _source_from_rule(path: str, rule: dict) -> dict:
    source = rule.get("source") or {}
    rel_path = os.path.relpath(path, ENGINE_DIR)
    platform = source.get("platform") or rule.get("source_id") or os.path.splitext(os.path.basename(path))[0]
    source_type = source.get("type", "html")
    enabled = bool(rule.get("enabled", True) and source.get("enabled", True))
    return {
        "id": _source_id(rule, path),
        "name": source.get("name") or rule.get("name") or platform,
        "domain": _domain_from_rule(rule),
        "type": "api" if source_type == "api" else "website",
        "category": rule.get("subject") or source.get("subject") or "",
        "trust_score": 0.85 if enabled else 0.3,
        "update_frequency": int(source.get("update_frequency", 3600)),
        "anti_crawl_level": source.get("anti_crawl_level", "low"),
        "parser_strategy": source_type,
        "auth_required": 1 if (source.get("auth") or {}).get("type", "none") != "none" else 0,
        "language": source.get("language", "zh-CN"),
        "tags": json.dumps(rule.get("tags", []), ensure_ascii=False),
        "enabled": 1 if enabled else 0,
        "lifecycle_status": "ACTIVE" if enabled else "PAUSED",
        "rule_path": rel_path,
    }


def sync_sources_from_rules() -> list[dict]:
    """从 YAML 规则派生 Source Registry。"""
    records = []
    for path in _iter_rule_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                rule = yaml.safe_load(f) or {}
            if not isinstance(rule, dict):
                continue
            records.append(_source_from_rule(path, rule))
        except Exception:
            continue

    conn = get_db()
    cur = conn.cursor()
    for record in records:
        cur.execute(
            """
            INSERT INTO sources (
                id, name, domain, type, category, trust_score, update_frequency,
                anti_crawl_level, parser_strategy, auth_required, language, tags,
                enabled, lifecycle_status, rule_path, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                domain=excluded.domain,
                type=excluded.type,
                category=excluded.category,
                trust_score=excluded.trust_score,
                update_frequency=excluded.update_frequency,
                anti_crawl_level=excluded.anti_crawl_level,
                parser_strategy=excluded.parser_strategy,
                auth_required=excluded.auth_required,
                language=excluded.language,
                tags=excluded.tags,
                enabled=excluded.enabled,
                lifecycle_status=excluded.lifecycle_status,
                rule_path=excluded.rule_path,
                updated_at=datetime('now', 'localtime')
            """,
            (
                record["id"], record["name"], record["domain"], record["type"],
                record["category"], record["trust_score"], record["update_frequency"],
                record["anti_crawl_level"], record["parser_strategy"], record["auth_required"],
                record["language"], record["tags"], record["enabled"],
                record["lifecycle_status"], record["rule_path"],
            ),
        )
    conn.commit()
    conn.close()
    return records


@sources_bp.route("", methods=["GET"])
def list_sources():
    """GET /api/sources — 来源列表。"""
    sync_sources_from_rules()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sources ORDER BY enabled DESC, category, name")
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    for row in rows:
        try:
            row["tags"] = json.loads(row.get("tags") or "[]")
        except json.JSONDecodeError:
            row["tags"] = []
        row["enabled"] = bool(row["enabled"])
        row["auth_required"] = bool(row["auth_required"])
    return jsonify({"sources": rows})


@sources_bp.route("/summary", methods=["GET"])
def source_summary():
    """GET /api/sources/summary — Source Center 摘要。"""
    sources = list_sources().json["sources"]
    return jsonify({
        "total": len(sources),
        "active": sum(1 for source in sources if source["enabled"]),
        "paused": sum(1 for source in sources if not source["enabled"]),
        "avg_trust_score": round(
            sum(source["trust_score"] for source in sources) / len(sources), 4
        ) if sources else 0,
    })
