"""
Logs API — 实时日志流
"""
import subprocess
import json
import os
from flask import Blueprint, jsonify, Response, stream_with_context, request

logs_bp = Blueprint("logs", __name__)

ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine")
VENV_PYTHON = os.path.join(ENGINE_DIR, ".venv", "bin", "python")
ENGINE_CLI = os.path.join(ENGINE_DIR, "engine_cli.py")


@logs_bp.route("/list", methods=["GET"])
def list_logs():
    """GET /api/logs/list — 列出日志文件"""
    cmd = [VENV_PYTHON, ENGINE_CLI, "list-logs", "--format=json"]
    r = subprocess.run(cmd, cwd=ENGINE_DIR, capture_output=True, text=True)
    if r.returncode != 0:
        return jsonify({"error": r.stderr or "Failed"}), 500
    try:
        data = json.loads(r.stdout)
        return jsonify(data)
    except Exception:
        return jsonify({"logs": []})


@logs_bp.route("/tail/<log_name>", methods=["GET"])
def tail_log(log_name):
    """GET /api/logs/tail/<name>?lines=100 — 读取日志尾部"""
    import os
    safe_name = os.path.basename(log_name)
    logs_dir = os.path.join(ENGINE_DIR, "logs")
    fpath = os.path.join(logs_dir, safe_name)

    if not os.path.exists(fpath):
        return jsonify({"error": "Log file not found"}), 404

    line_count = 100
    lines = []
    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    tail = all_lines[-line_count:]

    return jsonify({
        "name": safe_name,
        "total": len(all_lines),
        "lines": [l.rstrip("\n") for l in tail],
    })


@logs_bp.route("/stream", methods=["GET"])
def stream_logs():
    """GET /api/logs/stream?rule_name=<name> — SSE 实时推送日志（监控 run-all 或指定规则执行）

    Query params:
      - rule_name: 可选，监控 engine/data/<rule_name>/ 下最新输出文件
      - 不传 rule_name: 监控 engine/logs/ 下最新 .log 文件
    """
    import time
    rule_name = _args_get(request, "rule_name", "")

    def generate():
        last_mtime = 0.0
        last_size = 0
        last_content_hash = ""
        import hashlib

        def hash_file_content(path):
            try:
                with open(path, "rb") as f:
                    return hashlib.md5(f.read(8192)).hexdigest()
            except Exception:
                return ""

        def get_monitor_target():
            """返回要监控的文件路径，无则返回 None"""
            if rule_name:
                # 监控 engine/data/<rule_name>/ 下最新 .json 文件
                data_dir = os.path.join(ENGINE_DIR, "data", rule_name)
                if not os.path.isdir(data_dir):
                    return None
                files = [f for f in os.listdir(data_dir) if f.endswith(".json")]
                if not files:
                    return None
                files.sort(key=lambda f: os.path.getmtime(os.path.join(data_dir, f)), reverse=True)
                return os.path.join(data_dir, files[0])
            else:
                # 监控 engine/logs/ 下最新 .log 文件
                logs_dir = os.path.join(ENGINE_DIR, "logs")
                if not os.path.isdir(logs_dir):
                    return None
                files = [f for f in os.listdir(logs_dir) if f.endswith(".log")]
                if not files:
                    return None
                files.sort(key=lambda f: os.path.getmtime(os.path.join(logs_dir, f)), reverse=True)
                return os.path.join(logs_dir, files[0])

        def tail_file(path, last_pos=0):
            """读取文件新增内容，返回 (new_content, new_pos)"""
            try:
                size = os.path.getsize(path)
                if size == 0:
                    return "", 0
                if size > last_pos:
                    with open(path, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_pos)
                        new_content = f.read()
                        return new_content, size
                return "", last_pos
            except Exception:
                return "", last_pos

        target = get_monitor_target()
        if target:
            label = os.path.basename(os.path.dirname(target)) + "/" + os.path.basename(target)
            yield f"data: {json.dumps({'type': 'info', 'msg': f'监控: {label}'})}\n\n"
        else:
            yield f"data: {json.dumps({'type': 'info', 'msg': '暂无日志文件，等待数据...'})}\n\n"

        sent_header = False
        while True:
            try:
                target = get_monitor_target()
                if not target:
                    time.sleep(1)
                    continue

                if rule_name:
                    # JSON 文件：检查 mtime 或内容变化
                    mtime = os.path.getmtime(target)
                    content_hash = hash_file_content(target)
                    if content_hash != last_content_hash or mtime > last_mtime:
                        last_mtime = mtime
                        last_content_hash = content_hash
                        try:
                            with open(target, "r", encoding="utf-8") as f:
                                raw = f.read()
                            # 推送文件内容片段（最多前 500 字符）
                            preview = raw[:500] + ("...[已截断]" if len(raw) > 500 else "")
                            yield f"data: {json.dumps({'type': 'json_update', 'file': os.path.basename(target), 'preview': preview})}\n\n"
                        except Exception:
                            pass
                else:
                    # .log 文件：tail 新行
                    new_content, last_size = tail_file(target, last_size)
                    if new_content:
                        for line in new_content.rstrip("\n").split("\n"):
                            if line.strip():
                                yield f"data: {json.dumps({'type': 'log', 'line': line, 'file': os.path.basename(target)})}\n\n"

                time.sleep(1)
            except GeneratorExit:
                break
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'msg': str(e)})}\n\n"
                break

        yield f"data: {json.dumps({'event': 'done', 'msg': '日志流结束'})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _args_get(req, key, default=""):
    return req.args.get(key, default)
