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
from datetime import date, datetime
from decimal import Decimal
from flask import Blueprint, jsonify, Response, stream_with_context
from sqlalchemy import create_engine, text

from APP.engine.engine.config import get_pg_dsn

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

STATUS_TO_NG = {
    "running": "RUNNING",
    "success": "SUCCESS",
    "completed": "SUCCESS",
    "failed": "FAILED",
    "cancelled": "CANCELLED",
    "partial_success": "PARTIAL_SUCCESS",
}


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


def to_ng_status(status: str) -> str:
    """映射为 NG v2.2 任务状态。"""
    return STATUS_TO_NG.get((status or "").lower(), "PENDING")


def _json_safe(value):
    """把数据库返回值转换为 Flask JSON 可稳定序列化的结构。"""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: _json_safe(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_json_safe(inner) for inner in value]
    return value


def _row_to_json(row) -> dict:
    return {key: _json_safe(value) for key, value in dict(row).items()}


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

    # 确保 task_logs 表存在
    try:
        conn_mig = sqlite3.connect(DB_PATH)
        conn_mig.executescript(open(os.path.join(os.path.dirname(__file__), "..", "migrations", "002_task_logs.sql")).read())
        conn_mig.close()
    except Exception:
        pass

    for raw_line in proc.stdout:
        event = parse_event_line(raw_line)

        # 持久化事件到 task_logs 表
        if event:
            try:
                conn2 = sqlite3.connect(DB_PATH)
                cur2 = conn2.cursor()
                cur2.execute(
                    "INSERT INTO task_logs (task_id, event_json) VALUES (?, ?)",
                    (task_id, raw_line.strip())
                )
                conn2.commit()
                conn2.close()
            except Exception:
                pass

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
            "event": "done",   # 前端通过 addEventListener('done', ...) 捕获
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
                # 有 event 字段时使用命名事件（event: name），否则用普通 data:
                if data.get("event"):
                    yield f"event: {data['event']}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                if data.get("type") == "done":
                    break
            except queue.Empty:
                # 超时检查任务是否已结束
                with _task_lock:
                    status = _task_states.get(task_id, {}).get("status", "running")
                if status in ("done", "success", "failed"):
                    break
                # 发送心跳 — 使用 event: 命名行，前端通过 addEventListener 捕获
                yield f"event: heartbeat\ndata: {json.dumps({'type': 'heartbeat'})}\n\n"

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
    tasks = []
    for row in rows:
        item = dict(row)
        item["ng_status"] = to_ng_status(item.get("status"))
        tasks.append(item)
    return jsonify({"tasks": tasks})


def _get_task_record(task_id: int) -> dict | None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM task_history WHERE id = ?", (task_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    item["ng_status"] = to_ng_status(item.get("status"))
    return item


@tasks_bp.route("/<int:task_id>", methods=["GET"])
def get_task(task_id):
    """GET /api/tasks/<id> — 查询单个任务"""
    item = _get_task_record(task_id)
    if not item:
        return jsonify({"error": "Task not found"}), 404
    item["collection_run"] = _find_collection_run_for_task(item)
    return jsonify(item)


def _find_collection_run_for_task(task: dict) -> dict | None:
    """按任务时间和规则路径定位 PostgreSQL 中的采集运行记录。"""
    created_at = task.get("created_at")
    if not created_at:
        return None
    try:
        engine = create_engine(get_pg_dsn(), pool_pre_ping=True, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            params = {"created_at": created_at}
            rule_clause = ""
            if task.get("rule_path"):
                rule_clause = "and rule_path like :rule_path"
                params["rule_path"] = f"%{task['rule_path']}"
            row = conn.execute(text(f"""
                select id::text, rule_name, rule_path, subject, platform, status,
                       total_collected, saved_count, dedup_filtered, output_path,
                       started_at, finished_at, duration_seconds
                from collection_runs
                where started_at >= ((cast(:created_at as timestamp) at time zone 'Asia/Shanghai') - interval '5 minutes')
                  and started_at <= ((cast(:created_at as timestamp) at time zone 'Asia/Shanghai') + interval '5 minutes')
                  {rule_clause}
                order by started_at desc
                limit 1
            """), params).mappings().first()
            return _row_to_json(row) if row else None
    except Exception:
        return None


def _load_archive_summaries(conn, urls: list[str]) -> dict[str, dict]:
    """按 URL 批量读取最新归档正文摘要。"""
    urls = [url for url in urls if url]
    if not urls:
        return {}
    page_rows = conn.execute(text("""
        select distinct on (source_url)
               id::text, source_url, title, content_hash, contains_ocr, fetched_at
        from archive_pages
        where source_url = any(:urls)
        order by source_url, fetched_at desc
    """), {"urls": urls}).mappings().all()
    if not page_rows:
        return {}

    page_by_id = {_row_to_json(row)["id"]: _row_to_json(row) for row in page_rows}
    block_rows = conn.execute(text("""
        select page_id::text, block_order, block_type, text
        from archive_blocks
        where page_id::text = any(:page_ids)
        order by page_id, block_order
    """), {"page_ids": list(page_by_id.keys())}).mappings().all()
    ocr_rows = conn.execute(text("""
        select page_id::text, status, ocr_text, elapsed_seconds, manual_review_required
        from ocr_results
        where page_id::text = any(:page_ids)
        order by page_id, created_at
    """), {"page_ids": list(page_by_id.keys())}).mappings().all()

    blocks_by_page = {page_id: [] for page_id in page_by_id}
    for row in block_rows:
        block = _row_to_json(row)
        page_id = block.pop("page_id")
        if block.get("text"):
            blocks_by_page.setdefault(page_id, []).append(block)

    ocr_by_page = {page_id: [] for page_id in page_by_id}
    for row in ocr_rows:
        ocr = _row_to_json(row)
        page_id = ocr.pop("page_id")
        if ocr.get("ocr_text"):
            ocr_by_page.setdefault(page_id, []).append(ocr)

    archive_by_url = {}
    for page in page_by_id.values():
        page_id = page["id"]
        blocks = blocks_by_page.get(page_id, [])
        ocr_results = ocr_by_page.get(page_id, [])
        body_text = "\n\n".join(
            block["text"] for block in blocks if block.get("block_type") in ("paragraph", "heading") and block.get("text")
        )
        ocr_text = "\n\n".join(ocr["ocr_text"] for ocr in ocr_results if ocr.get("ocr_text"))
        archive_by_url[page["source_url"]] = {
            "page_id": page_id,
            "title": page.get("title"),
            "content_hash": page.get("content_hash"),
            "contains_ocr": page.get("contains_ocr"),
            "fetched_at": page.get("fetched_at"),
            "body_text": body_text,
            "ocr_text": ocr_text,
            "blocks": blocks,
            "ocr_results": ocr_results,
        }
    return archive_by_url


@tasks_bp.route("/<int:task_id>/items", methods=["GET"])
def get_task_items(task_id):
    """GET /api/tasks/<id>/items — 查询本次运行 raw/deduped/filtered 明细。"""
    task = _get_task_record(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    task["collection_run"] = _find_collection_run_for_task(task)
    run = task.get("collection_run")
    if not run:
        return jsonify({"run": None, "items": {"raw": [], "deduped": [], "filtered": []}})
    try:
        engine = create_engine(get_pg_dsn(), pool_pre_ping=True, connect_args={"connect_timeout": 5})
        with engine.connect() as conn:
            rows = conn.execute(text("""
                select
                    ri.item_stage,
                    ri.raw_id,
                    ri.url,
                    ri.title,
                    ri.content_hash,
                    ri.filter_reason,
                    ri.matched_existing_id,
                    ri.data,
                    ri.governance,
                    ri.collected_at,
                    old.id::text as old_item_id,
                    old.title as old_title,
                    old.url as old_url,
                    old.content_hash as old_content_hash,
                    old.collected_at as old_collected_at
                from collection_run_items ri
                left join lateral (
                    select id, title, url, content_hash, collected_at
                    from collection_items ci
                    where ci.platform = ri.platform
                      and ci.raw_id = ri.raw_id
                      and ci.id::text <> coalesce(ri.matched_existing_id, '')
                    order by ci.collected_at desc
                    limit 1
                ) old on ri.item_stage = 'filtered'
                where ri.run_id = :run_id
                order by ri.item_stage, ri.title nulls last, ri.raw_id nulls last
            """), {"run_id": run["id"]}).mappings().all()
            archive_by_url = _load_archive_summaries(
                conn,
                sorted({row["url"] for row in rows if row["url"]}),
            )
        grouped = {"raw": [], "deduped": [], "filtered": []}
        for row in rows:
            item = _row_to_json(row)
            stage = item.pop("item_stage")
            old_item_id = item.pop("old_item_id", None)
            old_title = item.pop("old_title", None)
            old_url = item.pop("old_url", None)
            old_content_hash = item.pop("old_content_hash", None)
            old_collected_at = item.pop("old_collected_at", None)
            if old_item_id:
                item["matched_existing_item"] = {
                    "id": old_item_id,
                    "title": old_title,
                    "url": old_url,
                    "content_hash": old_content_hash,
                    "collected_at": old_collected_at,
                }
            if item.get("url") in archive_by_url:
                item["archive"] = archive_by_url[item["url"]]
            grouped.setdefault(stage, []).append(item)
        return jsonify({"run": run, "items": grouped})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@tasks_bp.route("/<int:task_id>/logs", methods=["GET"])
def get_task_logs(task_id):
    """GET /api/tasks/<task_id>/logs — 获取任务的全部日志事件（NDJSON）"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT event_json FROM task_logs WHERE task_id = ? ORDER BY id", (task_id,))
    rows = cur.fetchall()
    conn.close()

    def generate():
        for row in rows:
            yield row["event_json"] + "\n"

    return Response(
        stream_with_context(generate()),
        mimetype="application/x-ndjson",
    )


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
