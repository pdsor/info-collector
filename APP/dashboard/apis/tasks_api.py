"""
Tasks API — 手动触发执行 + SSE 实时日志流
"""
import sqlite3
import subprocess
import json
import os
from flask import Blueprint, jsonify, Response, stream_with_context
from datetime import datetime

tasks_bp = Blueprint("tasks", __name__)

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine")
VENV_PYTHON = os.path.join(ENGINE_DIR, ".venv", "bin", "python")
ENGINE_CLI = os.path.join(ENGINE_DIR, "engine_cli.py")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def record_task(name, status, message="", new_count=0, duration=0.0):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO task_history (task_name, status, message, new_count, duration) VALUES (?, ?, ?, ?, ?)",
        (name, status, message, new_count, duration)
    )
    conn.commit()
    task_id = cur.lastrowid
    conn.close()
    return task_id


@tasks_bp.route("/run-all", methods=["POST"])
def run_all():
    """POST /api/tasks/run-all — 执行所有已启用规则"""
    import time
    start = time.time()
    task_id = record_task("run-all", "running", "开始执行...")

    cmd = [VENV_PYTHON, ENGINE_CLI, "run-all"]
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=ENGINE_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
        )
        output_lines = []
        for line in proc.stdout:
            output_lines.append(line)
        proc.wait()
        duration = time.time() - start
        success = proc.returncode == 0
        # 简单解析 new_count
        new_count = 0
        for line in output_lines:
            if "new" in line.lower() and "count" in line.lower():
                try:
                    new_count = int(line.strip().split()[-1])
                except Exception:
                    pass
        msg = "".join(output_lines[-5:]) if output_lines else ("成功" if success else "失败")
        record_task("run-all", "success" if success else "failed", msg[:500], new_count, duration)
        return jsonify({
            "task_id": task_id,
            "success": success,
            "new_count": new_count,
            "duration": round(duration, 1),
            "output": "".join(output_lines),
        })
    except Exception as e:
        duration = time.time() - start
        record_task("run-all", "failed", str(e), 0, duration)
        return jsonify({"task_id": task_id, "success": False, "error": str(e), "duration": round(duration, 1)}), 500


@tasks_bp.route("/stream", methods=["GET"])
def stream():
    """GET /api/tasks/stream — SSE 实时流，执行所有已启用规则"""
    import time

    def generate():
        # 发送开始信号
        yield f"data: {json.dumps({'type': 'start', 'msg': '开始执行所有已启用规则...'})}\n\n"
        time.sleep(0.1)

        cmd = [VENV_PYTHON, ENGINE_CLI, "run-all"]
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=ENGINE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
            )
            for line in proc.stdout:
                if line:
                    yield f"data: {json.dumps({'type': 'output', 'line': line.rstrip()})}\n\n"
            proc.wait()
            success = proc.returncode == 0
            yield f"data: {json.dumps({'type': 'done', 'success': success, 'returncode': proc.returncode})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@tasks_bp.route("/history", methods=["GET"])
def task_history():
    """GET /api/tasks/history — 查询任务历史"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, task_name, status, message, new_count, duration, created_at FROM task_history ORDER BY created_at DESC LIMIT 50"
    )
    rows = cur.fetchall()
    conn.close()
    return jsonify({"tasks": [dict(r) for r in rows]})


@tasks_bp.route("/<int:task_id>", methods=["GET"])
def get_task(task_id):
    """GET /api/tasks/<id> — 查询单个任务"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM task_history WHERE id = ?", (task_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(dict(row))
