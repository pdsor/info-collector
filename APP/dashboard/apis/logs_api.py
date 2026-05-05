"""
Logs API — 实时日志流
"""
import subprocess
import json
import os
from flask import Blueprint, jsonify, Response, stream_with_context

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
    """GET /api/logs/stream — SSE 实时推送最新日志
    Query params:
      - rule_name: 可选，指定规则名称，读取 engine/data/<rule_name>/ 下最新输出文件
      - 无 rule_name 时: 读取 engine/logs/ 下最新 .log 文件（原有行为）
    """
    import time
    from flask import request

    rule_name = request.args.get("rule_name", "")

    def generate():
        last_mtime = 0.0
        last_size = 0
        last_content_hash = ""  # 用于检测文件内容变化

        # 当 rule_name 指定时，读取 engine/data/<rule_name>/ 下的最新输出
        if rule_name:
            import hashlib
            data_dir = os.path.join(ENGINE_DIR, "data", rule_name)
            yield f"data: {json.dumps({'type': 'info', 'msg': f'监控输出: {rule_name}'})}\n\n"

            while True:
                try:
                    if not os.path.exists(data_dir):
                        time.sleep(1)
                        continue

                    # 找到最新的 .json 文件
                    json_files = [f for f in os.listdir(data_dir) if f.endswith(".json")]
                    if not json_files:
                        time.sleep(1)
                        continue

                    latest_file = sorted(
                        json_files,
                        key=lambda f: os.path.getmtime(os.path.join(data_dir, f)),
                        reverse=True
                    )[0]
                    fpath = os.path.join(data_dir, latest_file)
                    stat = os.stat(fpath)

                    # 检测文件是否有变化
                    content = ""
                    if stat.st_size > 0:
                        try:
                            content = open(fpath, "r", encoding="utf-8", errors="replace").read()
                            content_hash = hashlib.md5(content.encode()).hexdigest()
                        except Exception:
                            content_hash = ""

                        if content_hash != last_content_hash:
                            last_content_hash = content_hash
                            # 发送新内容（截取前 200 字符作为摘要）
                            for line in content.splitlines():
                                if line.strip():
                                    preview = line.strip()[:200]
                                    yield f"data: {json.dumps({'type': 'log', 'line': preview, 'file': latest_file})}\n\n"
                        last_size = stat.st_size
                        last_mtime = stat.st_mtime

                    time.sleep(1)
                except GeneratorExit:
                    break
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'msg': str(e)})}\n\n"
                    break

            # 任务结束时发送 done 事件
            yield f"event: done\ndata: {json.dumps({'type': 'done', 'msg': '日志流结束'})}\n\n"

        else:
            # 原有行为: 读取 engine/logs/*.log
            last_pos = 0
            logs_dir = os.path.join(ENGINE_DIR, "logs")

            def get_latest_log():
                if not os.path.exists(logs_dir):
                    return None
                files = [f for f in os.listdir(logs_dir) if f.endswith(".log")]
                if not files:
                    return None
                files.sort(key=lambda f: os.path.getmtime(os.path.join(logs_dir, f)), reverse=True)
                return files[0]

            latest = get_latest_log()
            if latest:
                yield f"data: {json.dumps({'type': 'info', 'msg': f'监控日志: {latest}'})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'info', 'msg': '暂无日志文件'})}\n\n"

            while True:
                try:
                    latest = get_latest_log()
                    if latest:
                        fpath = os.path.join(logs_dir, latest)
                        size = os.path.getsize(fpath)
                        if size > last_pos:
                            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                                f.seek(last_pos)
                                new_lines = f.readlines()
                                last_pos = size
                                for line in new_lines:
                                    if line.strip():
                                        yield f"data: {json.dumps({'type': 'log', 'line': line.rstrip(), 'file': latest})}\n\n"
                    time.sleep(1)
                except GeneratorExit:
                    break
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'msg': str(e)})}\n\n"
                    break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
