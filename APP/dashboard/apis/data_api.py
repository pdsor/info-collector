"""
Data API — 数据预览
"""
import sqlite3
import json
import os
import glob
from flask import Blueprint, jsonify, request

data_bp = Blueprint("data", __name__)

DB_PATH = "APP/dashboard/dashboard.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _find_latest_data_file(data_dir: str, subject: str, platform: str):
    """在 engine/data/{subject}/{platform}/ 目录中找到最新的 data_*.json 文件"""
    target_dir = os.path.join(data_dir, subject, platform)
    if not os.path.exists(target_dir):
        return None
    json_files = glob.glob(os.path.join(target_dir, "data_*.json"))
    if not json_files:
        return None
    return max(json_files)  # 按文件名排序，含日期


def _load_items_from_file(file_path: str, limit: int = None):
    """从文件加载数据项，支持 JSON 对象格式和 JSONL 逐行格式"""
    if not os.path.exists(file_path):
        return [], 0

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        return [], 0

    if content.startswith("{"):
        # JSON 对象格式（output.py 输出）：{"meta":..., "data": [...]}
        try:
            obj = json.loads(content)
            all_items = obj.get("data", [])
            total = len(all_items)
            items = all_items[:limit] if limit is not None else all_items
            return items, total
        except Exception:
            return [], 0
    else:
        # JSONL 逐行格式或其他格式
        items = []
        total = 0
        for line in content.split("\n"):
            if not line.strip():
                continue
            total += 1
            if limit is None or len(items) < limit:
                try:
                    items.append(json.loads(line.strip()))
                except Exception:
                    pass
        return items, total


def _count_items_in_file(file_path: str) -> int:
    """计算文件中数据项数量"""
    if not os.path.exists(file_path):
        return 0

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read().strip()

    if not content:
        return 0

    if content.startswith("{"):
        # JSON 对象格式
        try:
            obj = json.loads(content)
            return len(obj.get("data", []))
        except Exception:
            return 0
    else:
        # JSONL 逐行格式
        count = 0
        for line in content.split("\n"):
            if line.strip():
                count += 1
        return count


def _get_data_dir():
    """获取 engine/data 目录路径"""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "engine", "data",
    )


@data_bp.route("/subjects", methods=["GET"])
def list_subjects():
    """GET /api/data/subjects — 列出所有数据主题"""
    engine_data = _get_data_dir()
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
    engine_data = _get_data_dir()
    subject_dir = os.path.join(engine_data, subject)

    if not os.path.exists(subject_dir):
        return jsonify({"platforms": []})

    platforms = []
    for f in os.listdir(subject_dir):
        f_path = os.path.join(subject_dir, f)
        if os.path.isdir(f_path):
            # 子目录形式：{subject}/{platform}/data_*.json
            platforms.append(f)
        elif f.endswith(".json") or f.endswith(".jsonl"):
            # 文件形式：{subject}/{platform}.jsonl
            p = f.replace(".jsonl", "").replace(".json", "")
            platforms.append(p)
    return jsonify({"platforms": sorted(set(platforms))})


@data_bp.route("/preview", methods=["GET"])
def preview_data():
    """GET /api/data/preview?subject=xxx&platform=xxx&limit=10 — 预览数据"""
    subject = request.args.get("subject", "")
    platform = request.args.get("platform", "")
    limit = min(int(request.args.get("limit", 20)), 100)

    if not subject or not platform:
        return jsonify({"error": "subject and platform required"}), 400

    engine_data = _get_data_dir()
    latest_file = _find_latest_data_file(engine_data, subject, platform)

    if latest_file is None:
        return jsonify({"error": "No data file found"}), 404

    items, total = _load_items_from_file(latest_file, limit=limit)

    return jsonify({
        "items": items,
        "total": total,
        "preview_count": len(items),
        "file": os.path.basename(latest_file),
    })


@data_bp.route("/stats", methods=["GET"])
def data_stats():
    """GET /api/data/stats — 全局统计"""
    engine_data = _get_data_dir()

    stats = {}
    if os.path.exists(engine_data):
        for subject in os.listdir(engine_data):
            s_path = os.path.join(engine_data, subject)
            if not os.path.isdir(s_path):
                continue
            stats[subject] = {}
            for platform in os.listdir(s_path):
                p_path = os.path.join(s_path, platform)
                if not os.path.isdir(p_path):
                    continue
                # 查找该平台目录下的数据文件
                json_files = glob.glob(os.path.join(p_path, "data_*.json"))
                total_count = 0
                latest_file = None
                if json_files:
                    latest_file = max(json_files)
                    total_count = _count_items_in_file(latest_file)
                stats[subject][platform] = {
                    "count": total_count,
                    "latest_file": os.path.basename(latest_file) if latest_file else None,
                }

    return jsonify(stats)
