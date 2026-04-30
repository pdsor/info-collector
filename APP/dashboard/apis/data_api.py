"""
Data API — 数据预览
"""
import sqlite3
import json
import os
from flask import Blueprint, jsonify, request

data_bp = Blueprint("data", __name__)

DB_PATH = "APP/dashboard/dashboard.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@data_bp.route("/subjects", methods=["GET"])
def list_subjects():
    """GET /api/data/subjects — 列出所有数据主题"""
    engine_data = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "engine", "data",
    )
    if not os.path.exists(engine_data):
        return jsonify({"subjects": []})

    subjects = []
    for s in os.listdir(engine_data):
        s_path = os.path.join(engine_data, s)
        if os.path.isdir(s_path):
            subjects.append(s)
    return jsonify({"subjects": sorted(subjects)})


@data_bp.route("/platforms", methods=["GET"])
def list_platforms():
    """GET /api/data/platforms?subject=xxx — 列出某主题下的平台"""
    subject = request.args.get("subject", "")
    engine_data = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "engine", "data", subject,
    )
    if not os.path.exists(engine_data):
        return jsonify({"platforms": []})

    platforms = []
    for f in os.listdir(engine_data):
        if f.endswith(".jsonl") or f.endswith(".json"):
            p = f.replace(".jsonl", "").replace(".json", "")
            platforms.append(p)
    return jsonify({"platforms": sorted(platforms)})


@data_bp.route("/preview", methods=["GET"])
def preview_data():
    """GET /api/data/preview?subject=xxx&platform=xxx&limit=10 — 预览数据"""
    subject = request.args.get("subject", "")
    platform = request.args.get("platform", "")
    limit = min(int(request.args.get("limit", 20)), 100)

    if not subject or not platform:
        return jsonify({"error": "subject and platform required"}), 400

    data_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "engine", "data", subject, f"{platform}.jsonl",
    )

    if not os.path.exists(data_path):
        return jsonify({"error": "Data file not found"}), 404

    items = []
    total = 0
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            total += 1
            if len(items) < limit:
                try:
                    items.append(json.loads(line.strip()))
                except Exception:
                    pass

    return jsonify({
        "items": items,
        "total": total,
        "preview_count": len(items),
    })


@data_bp.route("/stats", methods=["GET"])
def data_stats():
    """GET /api/data/stats — 全局统计"""
    engine_data = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "engine", "data",
    )

    stats = {}
    if os.path.exists(engine_data):
        for subject in os.listdir(engine_data):
            s_path = os.path.join(engine_data, subject)
            if not os.path.isdir(s_path):
                continue
            stats[subject] = {}
            for f in os.listdir(s_path):
                if f.endswith(".jsonl") or f.endswith(".json"):
                    p = f.replace(".jsonl", "").replace(".json", "")
                    fp = os.path.join(s_path, f)
                    count = sum(1 for _ in open(fp, "r", encoding="utf-8", errors="replace"))
                    stats[subject][p] = count

    return jsonify(stats)
