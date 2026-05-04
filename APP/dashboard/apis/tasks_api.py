"""
Tasks API — 异步任务执行 + per-task SSE 事件流
================================================
架构：
  POST /api/tasks/run-all        → 创建 task_history 记录 → 启动后台线程 → 返回 task_id
  POST /api/tasks/run-single/<path>  → 同上，单规则
  GET  /api/tasks/stream/<task_id>   → SSE 流，实时推送任务进度
  GET  /api/tasks/history           → 查询任务历史
  GET  /api/tasks/<id>             → 查询单个任务详情

Dashboard 是任务协调器（写入 task_history），engine 是纯执行器（输出 JSONL 事件）。
"""
import sqlite3
import subprocess
import json
import os
import threading
import time as time_mod
from flask import Blueprint, jsonify, Response, stream_with_context

tasks_bp = Blueprint("tasks", __name__)

ENGINE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "engine"
)
VENV_PYTHON = os.path.join(ENGINE_DIR, ".venv", "bin", "python")
ENGINE_CLI = os.path.join(ENGINE_DIR, "engine_cli.py")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard.db")

# 内存任务状态：{task_id: {"status": str, "lock": threading.Lock, "sse_queues": [queues]}}
_task_states: dict[int, dict] = {}
_task_lock = threading.Lock()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def record_task(name: str, status: str, message: str = "", new_count: int = 0,
                duration: float = 0.0, trigger_type: str = "manual",
                rule_path: str = "") -> int:
    """写入 task_history，返回 task_id"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO task_history (task_name, status, message, new_count, duration, trigger_type, rule_path) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, status, message, new_count, duration, trigger_type, rule_path or None)
    )
    conn.commit()
    task_id = cur.lastrowid
    conn.close()
    return task_id


def update_task(task_id: int, status: str, message: str = "", new_count: int = 0, duration: float = 0.0):
    """更新 task_history 记录"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE task_history SET status=?, message=?, new_count=?, duration=? WHERE id=?",
        (status, message[:500] if message else "", new_count, duration, task_id)
    )
    conn.commit()
    conn.close()


def parse_event_line(line: str):
    """解析 JSONL 行，返回 dict 或 None"""
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def _sse_push(task_id: int, data: dict):
    """向所有订阅此任务的 SSE 连接推送消息"""
    with _task_lock:
        state = _task_states.get(task_id)
        if not state:
            return
        queues = list(state.get("sse_queues", []))
    for q in queues:
        try:
            q.put(data)
        except Exception:
            pass


def run_task_async(task_id: int, cmd: list, task_name: str, trigger_type: str, rule_path: str):
    """
    后台线程函数：执行 engine_cli JSONL 命令，解析事件，更新 task_history + SSE。
    """
    # 初始化内存状态
    import queue
    with _task_lock:
        _task_states[task_id] = {
            "status": "running",
            "sse_queues": [],          # 所有订阅的 SSE response queues
            "lock": threading.Lock(),
        }
        state = _task_states[task_id]

    proc = subprocess.Popen(
        cmd,
        cwd=ENGINE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
    )

    total_new = 0
    total_skip = 0
    total_error = 0
    error_message = ""
    start = time_mod.time()

    for raw_line in proc.stdout:
        event = parse_event_line(raw_line)
        if not event:
            continue

        etype = event.get("type", "")

        if etype == "status":
            _sse_push(task_id, {
                "type": "status",
                "rule": os.path.basename(event.get("rule", "")),
                "status": event.get("status"),
                "msg": event.get("msg", ""),
            })

        elif etype == "progress":
            _sse_push(task_id, {
                "type": "progress",
                "rule": os.path.basename(event.get("rule", "")),
                "phase": event.get("phase"),
                "current": event.get("current"),
                "total": event.get("total"),
            })

        elif etype == "error":
            error_message = event.get("message", "Unknown error")
            total_error += 1
            _sse_push(task_id, {
                "type": "error",
                "rule": os.path.basename(event.get("rule", "")),
                "message": error_message,
                "detail": event.get("detail", ""),
            })

        elif etype == "skip":
            total_skip += 1
            _sse_push(task_id, {
                "type": "skip",
                "rule": os.path.basename(event.get("rule", "")),
                "reason": event.get("reason", ""),
            })

        elif etype == "complete":
            nc = event.get("new_count", 0)
            total_new += nc
            _sse_push(task_id, {
                "type": "complete",
                "rule": os.path.basename(event.get("rule", "")),
                "new_count": nc,
                "duration": event.get("duration"),
            })

        elif etype == "summary":
            duration = event.get("duration", time_mod.time() - start)
            final_status = "failed" if error_message else "success"
            update_task(task_id, final_status, error_message, total_new, duration)
            _sse_push(task_id, {
                "type": "done",
                "success": final_status == "success",
                "total_new": total_new,
                "total_skip": total_skip,
                "total_error": total_error,
                "duration": duration,
            })
            with _task_lock:
                if task_id in _task_states:
                    _task_states[task_id]["status"] = final_status

    proc.wait()

    # 若无 summary（进程异常退出），补一条最终状态
    with _task_lock:
        current = _task_states.get(task_id, {}).get("status", "running")

    if current == "running":
        duration = time_mod.time() - start
        final = "failed" if error_message or proc.returncode != 0 else "success"
        update_task(task_id, final, error_message, total_new, duration)
        _sse_push(task_id, {
            "type": "done",
            "success": final == "success",
            "total_new": total_new,
            "total_skip": total_skip,
            "total_error": total_error,
            "duration": duration,
        })
        with _task_lock:
            if task_id in _task_states:
                _task_states[task_id]["status"] = final

    # 通知所有 SSE 连接结束
    with _task_lock:
        if task_id in _task_states:
            _task_states[task_id]["status"] = "done"


# ── API 端点 ──────────────────────────────────────────────────

@tasks_bp.route("/run-all", methods=["POST"])
def run_all():
    """POST /api/tasks/run-all — 创建任务记录，立即返回 task_id"""
    task_id = record_task("run-all", "running", "等待执行...", trigger_type="manual")
    cmd = [VENV_PYTHON, ENGINE_CLI, "run-all", "--format=jsonl"]
    thread = threading.Thread(
        target=run_task_async,
        args=(task_id, cmd, "run-all", "manual", ""),
        daemon=True,
    )
    thread.start()
    return jsonify({"task_id": task_id, "status": "running"})


@tasks_bp.route("/run-single/<path:rule_path>", methods=["POST"])
def run_single(rule_path):
    """POST /api/tasks/run-single/<path> — 单规则异步执行"""
    task_name = f"run: {rule_path}"
    task_id = record_task(task_name, "running", f"执行 {rule_path}...", trigger_type="manual", rule_path=rule_path)
    cmd = [VENV_PYTHON, ENGINE_CLI, "run-rule", rule_path, "--format=jsonl"]
    thread = threading.Thread(
        target=run_task_async,
        args=(task_id, cmd, task_name, "manual", rule_path),
        daemon=True,
    )
    thread.start()
    return jsonify({"task_id": task_id, "status": "running"})


@tasks_bp.route("/stream/<int:task_id>", methods=["GET"])
def stream_task(task_id):
    """GET /api/tasks/stream/<task_id> — SSE 订阅单个任务实时进度"""
    import queue

    q: queue.Queue = queue.Queue()

    # 将队列注册到任务状态
    with _task_lock:
        if task_id in _task_states:
            _task_states[task_id]["sse_queues"].append(q)
        else:
            # 任务不存在，发送错误并立即返回
            def generate_error():
                yield f"data: {json.dumps({'type': 'error', 'msg': 'task not found'})}\n\n"
            return Response(
                stream_with_context(generate_error()),
                mimetype="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

    def generate():
        # 先发送初始状态
        with _task_lock:
            initial = _task_states.get(task_id, {}).get("status", "running")
        yield f"data: {json.dumps({'type': 'start', 'task_id': task_id, 'status': initial})}\n\n"

        # 持续从队列中读取，直到任务完成（最多 30 分钟）
        while True:
            try:
                data = q.get(timeout=60)
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                if data.get("type") == "done":
                    break
            except queue.Empty:
                # 超时检查任务是否已结束
                with _task_lock:
                    status = _task_states.get(task_id, {}).get("status", "running")
                if status in ("done", "success", "failed"):
                    break
                # 发送心跳
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"

        # 清理队列引用
        with _task_lock:
            if task_id in _task_states:
                try:
                    _task_states[task_id]["sse_queues"].remove(q)
                except ValueError:
                    pass

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
        "SELECT id, task_name, status, message, new_count, duration, trigger_type, rule_path, created_at "
        "FROM task_history ORDER BY created_at DESC LIMIT 50"
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


# ── 供外部模块调用的统一入口 ─────────────────────────────────

def trigger_task(task_name: str, cmd: list, trigger_type: str = "manual", rule_path: str = "") -> int:
    """
    cron_api 等模块调用此函数：创建任务记录并异步执行。
    返回 task_id。
    """
    task_id = record_task(task_name, "running", f"触发 {trigger_type}...", trigger_type=trigger_type, rule_path=rule_path)
    thread = threading.Thread(
        target=run_task_async,
        args=(task_id, cmd, task_name, trigger_type, rule_path),
        daemon=True,
    )
    thread.start()
    return task_id
