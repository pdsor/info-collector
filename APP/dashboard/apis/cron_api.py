"""
Cron API — 定时任务管理
"""
import os
import sqlite3
import json
from flask import Blueprint, request, jsonify, current_app
from datetime import datetime

cron_bp = Blueprint("cron", __name__)

_DASHBOARD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "dashboard"
)
DB_PATH = os.path.join(_DASHBOARD_DIR, "dashboard.db")
_scheduler = None


def set_scheduler(scheduler):
    """由 server.py 在注册蓝图前调用，注入 scheduler 实例"""
    global _scheduler
    _scheduler = scheduler


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_crons_from_db():
    """启动时从 DB 加载 cron 配置到 APScheduler"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cron_jobs WHERE enabled = 1")
    jobs = cur.fetchall()
    conn.close()
    for job in jobs:
        _add_scheduler_job(job)


def _add_scheduler_job(job_row):
    """将单个 cron job 添加到调度器"""
    global _scheduler
    scheduler = _scheduler
    if not scheduler:
        return
    job_id = f"cron_{job_row['id']}"
    rule_path = job_row.get("rule_path", "") or ""
    job_name = job_row.get("name", f"cron_{job_id}")

    def _run_cron(job_row=job_row):
        """Cron 触发时调用：创建任务记录并异步执行"""
        from APP.dashboard.apis.tasks_api import trigger_task
        import os
        ENGINE_DIR = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "engine"
        )
        VENV_PY = os.path.join(ENGINE_DIR, ".venv", "bin", "python")
        CLI = os.path.join(ENGINE_DIR, "engine_cli.py")

        name = job_row.get("name", f"cron_{job_row['id']}")
        rule_path = job_row.get("rule_path", "") or ""

        task_name = f"cron: {name}"
        if rule_path:
            cmd = [VENV_PY, CLI, "run-rule", rule_path, "--format=jsonl"]
        else:
            cmd = [VENV_PY, CLI, "run-all", "--format=jsonl"]

        trigger_task(
            task_name=task_name,
            cmd=cmd,
            trigger_type="cron",
            rule_path=rule_path,
        )
        # 不等待，任务在后台线程执行，结果写入 task_history

    # 移除旧的（如果存在）
    try:
        scheduler.remove_job(job_id)
    except Exception:
        pass

    # 添加新的 — APScheduler cron trigger 直接接受字符串 "*" 或整数
    scheduler.add_job(
        _run_cron,
        "cron",
        id=job_id,
        second=str(job_row.get("second", "0")),
        minute=str(job_row.get("minute", "*")),
        hour=str(job_row.get("hour", "*")),
        day=str(job_row.get("day", "*")),
        month=str(job_row.get("month", "*")),
        day_of_week=str(job_row.get("day_of_week", "*")),
        replace_existing=True,
    )


@cron_bp.route("", methods=["GET"])
def list_crons():
    """GET /api/cron — 列出所有 cron 任务"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cron_jobs ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return jsonify({"crons": [dict(r) for r in rows]})


@cron_bp.route("", methods=["POST"])
def create_cron():
    """POST /api/cron — 创建 cron 任务"""
    body = request.get_json()
    name = body.get("name", "").strip()
    schedule = body.get("schedule", "")
    rule_path = body.get("rule_path", "")
    enabled = bool(body.get("enabled", True))

    if not name or not schedule:
        return jsonify({"error": "name and schedule required"}), 400

    # 解析 cron 表达式
    parts = schedule.split()
    if len(parts) < 5:
        return jsonify({"error": "Invalid cron format, need at least 5 fields"}), 400

    second = parts[0] if len(parts) > 5 else "0"
    minute, hour, day, month, dow = parts[-5], parts[-4], parts[-3], parts[-2], parts[-1]

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO cron_jobs (name, second, minute, hour, day, month, day_of_week, rule_path, enabled)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, second, minute, hour, day, month, dow, rule_path, 1 if enabled else 0),
    )
    conn.commit()
    job_id = cur.lastrowid
    conn.close()

    # 如果启用，立即添加到调度器
    if enabled:
        conn2 = get_db()
        cur2 = conn2.cursor()
        cur2.execute("SELECT * FROM cron_jobs WHERE id = ?", (job_id,))
        job_row = dict(cur2.fetchone())
        conn2.close()
        _add_scheduler_job(job_row)

    return jsonify({"id": job_id, "success": True}), 201


@cron_bp.route("/<int:cron_id>", methods=["GET"])
def get_cron(cron_id):
    """GET /api/cron/<id>"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM cron_jobs WHERE id = ?", (cron_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify(dict(row))


@cron_bp.route("/<int:cron_id>", methods=["PUT"])
def update_cron(cron_id):
    """PUT /api/cron/<id> — 更新 cron 任务"""
    body = request.get_json()
    conn = get_db()
    cur = conn.cursor()

    # 获取现有
    cur.execute("SELECT * FROM cron_jobs WHERE id = ?", (cron_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    name = body.get("name", existing["name"])
    schedule = body.get("schedule", None)
    rule_path = body.get("rule_path", existing["rule_path"])
    enabled = body.get("enabled", bool(existing["enabled"]))

    if schedule:
        parts = schedule.split()
        second = parts[0] if len(parts) > 5 else "0"
        minute, hour, day, month, dow = parts[-5], parts[-4], parts[-3], parts[-2], parts[-1]
    else:
        second = existing["second"]
        minute = existing["minute"]
        hour = existing["hour"]
        day = existing["day"]
        month = existing["month"]
        dow = existing["day_of_week"]

    cur.execute(
        """UPDATE cron_jobs SET name=?, second=?, minute=?, hour=?, day=?, month=?,
           day_of_week=?, rule_path=?, enabled=? WHERE id=?""",
        (name, second, minute, hour, day, month, dow, rule_path, 1 if enabled else 0, cron_id),
    )
    conn.commit()
    conn.close()

    # 重新注册调度器
    global _scheduler
    scheduler = _scheduler
    if scheduler:
        try:
            scheduler.remove_job(f"cron_{cron_id}")
        except Exception:
            pass
        if enabled:
            conn2 = get_db()
            cur2 = conn2.cursor()
            cur2.execute("SELECT * FROM cron_jobs WHERE id = ?", (cron_id,))
            job_row = dict(cur2.fetchone())
            conn2.close()
            _add_scheduler_job(job_row)

    return jsonify({"success": True})


@cron_bp.route("/<int:cron_id>", methods=["DELETE"])
def delete_cron(cron_id):
    """DELETE /api/cron/<id>"""
    global _scheduler
    scheduler = _scheduler
    if scheduler:
        try:
            scheduler.remove_job(f"cron_{cron_id}")
        except Exception:
            pass

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM cron_jobs WHERE id = ?", (cron_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


@cron_bp.route("/<int:cron_id>/toggle", methods=["POST"])
def toggle_cron(cron_id):
    """POST /api/cron/<id>/toggle — 启用/停用"""
    body = request.get_json()
    enabled = bool(body.get("enabled", True))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE cron_jobs SET enabled=? WHERE id=?", (1 if enabled else 0, cron_id))
    conn.commit()
    conn.close()

    global _scheduler
    scheduler = _scheduler
    if scheduler:
        job_id = f"cron_{cron_id}"
        try:
            scheduler.remove_job(job_id)
        except Exception:
            pass
        if enabled:
            conn2 = get_db()
            cur2 = conn2.cursor()
            cur2.execute("SELECT * FROM cron_jobs WHERE id = ?", (cron_id,))
            job_row = dict(cur2.fetchone())
            conn2.close()
            _add_scheduler_job(job_row)

    return jsonify({"success": True, "enabled": enabled})
