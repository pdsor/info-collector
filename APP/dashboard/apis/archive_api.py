"""Archive Center API — 读文件系统归档包，不需要 PostgreSQL。"""
import glob
import json
import os

from flask import Blueprint, jsonify

from APP.dashboard.apis.rule_scope import is_current_scope

archive_bp = Blueprint("archives", __name__)

DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.dirname(DASHBOARD_DIR)
ENGINE_DIR = os.path.join(APP_DIR, "engine")
OUTPUT_DIR = os.path.join(ENGINE_DIR, "output")


def _iter_page_files():
    pattern = os.path.join(OUTPUT_DIR, "*", "*", "archives", "*", "page.json")
    yield from sorted(glob.glob(pattern), reverse=True)


def _load_page_summary(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None
    meta = payload.get("meta") or {}
    content_hash = meta.get("content_hash", "")
    if not content_hash:
        return None
    blocks = payload.get("blocks") or []
    block_types = [b.get("block_type") for b in blocks]
    subject = meta.get("subject") or ""
    platform = meta.get("platform") or ""
    if not is_current_scope(subject, platform):
        return None
    return {
        "content_hash": content_hash,
        "title": meta.get("title") or "",
        "source_url": meta.get("source_url") or "",
        "domain": meta.get("domain") or "",
        "platform": platform,
        "subject": subject,
        "fetched_at": meta.get("fetched_at") or "",
        "contains_ocr": bool(meta.get("contains_ocr")),
        "contains_table": bool(meta.get("contains_table")),
        "requires_structuring": bool(meta.get("requires_structuring")),
        "block_count": len(blocks),
        "ocr_block_count": block_types.count("ocr"),
        "image_block_count": block_types.count("image"),
    }


@archive_bp.route("", methods=["GET"])
def list_archives():
    """GET /api/archives — 归档页列表。"""
    pages = []
    for path in _iter_page_files():
        summary = _load_page_summary(path)
        if summary:
            pages.append(summary)
        if len(pages) >= 200:
            break
    return jsonify({"pages": pages, "total": len(pages)})


@archive_bp.route("/<content_hash>", methods=["GET"])
def get_archive(content_hash: str):
    """GET /api/archives/<hash> — 单页归档详情（blocks + structured_records）。"""
    pattern = os.path.join(OUTPUT_DIR, "*", "*", "archives", content_hash, "page.json")
    matches = glob.glob(pattern)
    if not matches:
        return jsonify({"error": "not found"}), 404
    try:
        with open(matches[0], "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    meta = payload.get("meta") or {}
    if not is_current_scope(meta.get("subject") or "", meta.get("platform") or ""):
        return jsonify({"error": "not found"}), 404

    # Try to load structured_records sidecar if present
    sr_path = os.path.join(os.path.dirname(matches[0]), "structured_records.json")
    structured_records = []
    if os.path.exists(sr_path):
        try:
            with open(sr_path, "r", encoding="utf-8") as f:
                structured_records = json.load(f)
        except Exception:
            pass

    return jsonify({
        "meta": meta,
        "blocks": payload.get("blocks") or [],
        "assets": payload.get("assets") or [],
        "structured_records": structured_records,
    })
