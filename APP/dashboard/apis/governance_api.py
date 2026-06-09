"""Governance Center API。"""
import glob
import json
import os

from flask import Blueprint, jsonify

from APP.dashboard.apis.rule_scope import is_current_scope

governance_bp = Blueprint("governance", __name__)

DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.dirname(DASHBOARD_DIR)
ENGINE_DIR = os.path.join(APP_DIR, "engine")
OUTPUT_DIR = os.path.join(ENGINE_DIR, "output")


def _iter_data_files():
    pattern = os.path.join(OUTPUT_DIR, "*", "*", "*.json")
    for path in sorted(glob.glob(pattern), reverse=True):
        if os.path.basename(path).startswith("combined"):
            continue
        yield path


def _load_record(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None

    meta = payload.get("meta") or {}
    governance = meta.get("governance") or {}
    data = payload.get("data") or []
    subject = meta.get("subject") or ""
    platform = meta.get("platform") or ""
    if not is_current_scope(subject, platform):
        return None
    item_count = int(governance.get("item_count", len(data)))
    field_completeness = float(governance.get("field_completeness", 1.0 if data else 0.0))
    quality_score = float(governance.get("quality_score", field_completeness))
    status = governance.get("status") or ("SUCCESS" if field_completeness >= 0.8 else "PARTIAL_SUCCESS")
    return {
        "subject": subject,
        "platform": platform,
        "source_file": os.path.basename(path),
        "item_count": item_count,
        "duplicate_count": int(governance.get("duplicate_count", meta.get("dedup_filtered", 0))),
        "injection_risk_count": int(governance.get("injection_risk_count", 0)),
        "field_completeness": field_completeness,
        "quality_score": quality_score,
        "status": status,
        "collected_at": meta.get("collected_at", ""),
    }


@governance_bp.route("/summary", methods=["GET"])
def governance_summary():
    """GET /api/governance/summary — 治理摘要和最近文件。"""
    records = []
    for path in _iter_data_files():
        record = _load_record(path)
        if record:
            records.append(record)
        if len(records) >= 100:
            break

    total_items = sum(record["item_count"] for record in records)
    total_risk = sum(record["injection_risk_count"] for record in records)
    avg_completeness = (
        round(sum(record["field_completeness"] for record in records) / len(records), 4)
        if records else 0
    )
    avg_quality = (
        round(sum(record["quality_score"] for record in records) / len(records), 4)
        if records else 0
    )
    return jsonify({
        "summary": {
            "file_count": len(records),
            "total_items": total_items,
            "injection_risk_count": total_risk,
            "avg_field_completeness": avg_completeness,
            "avg_quality_score": avg_quality,
        },
        "records": records[:30],
    })
