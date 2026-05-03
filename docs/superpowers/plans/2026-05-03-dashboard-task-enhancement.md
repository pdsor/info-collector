# Dashboard 任务链路增强 - 实现计划

> **面向 AI 代理的工作者：** 必需子技能：`superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为 engine_cli.py 实现结构化 JSONL 事件流协议，改造 Dashboard 任务链路（异步任务制 + 完整错误信息 + Cron 可追溯）。

**架构：** engine_cli 输出 JSONL 事件流（不写数据库），Dashboard 解析事件并写入 SQLite，通过 SSE 推送实时状态给前端。engine 是纯执行器，Dashboard 是任务协调器。

**技术栈：** Python jsonl / threading / APScheduler，Flask Blueprint / SSE，SQLite

---

## 文件变更总览

| 文件 | 职责 | 操作 |
|------|------|------|
| `APP/dashboard/migrations/002_task_enhance.sql` | task_history 新增字段 | 创建 |
| `APP/engine/engine/events.py` | 事件类型常量 + 事件构造器 | 创建 |
| `APP/engine/engine/engine.py` | run_all/run 集成事件发射 | 修改 |
| `APP/engine/engine_cli.py` | run-rule/run-all JSONL 输出 | 修改 |
| `APP/dashboard/apis/tasks_api.py` | 异步任务执行器 + per-task SSE | 重写 |
| `APP/dashboard/apis/cron_api.py` | 任务链：创建记录再异步触发 | 修改 |
| `APP/dashboard/apis/rules_api.py` | /run 端点改为异步返回 task_id | 修改 |
| `APP/dashboard/apis/__init__.py` | 注册新蓝图 | 修改 |
| `APP/dashboard/server.py` | 数据库迁移入口 | 修改 |
| `APP/dashboard/static/js/app.js` | 任务 SSE 流订阅 | 修改 |
| `APP/engine/SPEC.md` | 文档同步更新 | 修改 |
| `docs/superpowers/plans/YYYY-MM-DD-dashboard-task-enhancement.md` | 本计划 | 创建 |

---

## 前置条件

**数据库迁移需在服务重启时自动执行（server.py init_db 已支持 migration 框架）：**

```sql
-- APP/dashboard/migrations/002_task_enhance.sql
ALTER TABLE task_history ADD COLUMN trigger_type TEXT DEFAULT 'manual';
ALTER TABLE task_history ADD COLUMN rule_path TEXT;
```

---

## 任务分解

---

### 任务 1：数据库迁移 + 事件类型定义

**文件：**
- 创建：`APP/dashboard/migrations/002_task_enhance.sql`
- 创建：`APP/engine/engine/events.py`
- 修改：`APP/dashboard/server.py`（已在 migrations 框架内，无需改代码）
- 测试：无（SQLite migration 无法 pytest，需手动验证）

- [ ] **步骤 1：创建 002_task_enhance.sql**

```sql
-- 迁移 task_history 表，新增 trigger_type 和 rule_path 字段
ALTER TABLE task_history ADD COLUMN trigger_type TEXT DEFAULT 'manual';
ALTER TABLE task_history ADD COLUMN rule_path TEXT;
```

- [ ] **步骤 2：创建 events.py 模块**

```python
# APP/engine/engine/events.py
"""
InfoCollector 事件流协议
========================
所有 --format=json 模式下 run-rule / run-all 的输出均为 JSONL（逐行 JSON），
每行是一个独立事件，Dashboard 负责解析并写入任务历史。
"""
import time
import json
from typing import Optional, Any


def _ts() -> int:
    """当前 Unix 时间戳（秒）"""
    return int(time.time())


def emit(event_type: str, **kwargs) -> str:
    """
    构造并返回一条 JSONL 行。
    所有事件必含 type 和 ts 字段。
    """
    event = {"type": event_type, "ts": _ts(), **kwargs}
    return json.dumps(event, ensure_ascii=False)


# ── 事件构造器 ──────────────────────────────────────────────

def event_start(rule: str) -> str:
    """单个规则开始执行"""
    return emit("start", rule=rule)


def event_status(rule: str, status: str, msg: str = "") -> str:
    """状态变化：running / success / failed / skipped"""
    return emit("status", rule=rule, status=status, msg=msg)


def event_progress(rule: str, phase: str, current: int, total: int) -> str:
    """进度：fetch / parse / save"""
    return emit("progress", rule=rule, phase=phase, current=current, total=total)


def event_item(rule: str, data: dict) -> str:
    """新增数据项（仅新增，去重前）"""
    return emit("item", rule=rule, data=data)


def event_error(rule: str, message: str, detail: str = "") -> str:
    """执行出错"""
    return emit("error", rule=rule, message=message, detail=detail)


def event_skip(rule: str, reason: str) -> str:
    """规则被跳过"""
    return emit("skip", rule=rule, reason=reason)


def event_complete(rule: str, new_count: int, skip_count: int = 0, duration: float) -> str:
    """单个规则执行完成"""
    return emit("complete", rule=rule, new_count=new_count, skip_count=skip_count, duration=round(duration, 2))


def event_summary(total_rules: int, total_new: int, total_skip: int, total_error: int, duration: float) -> str:
    """run-all 全部结束汇总（仅 run-all 输出）"""
    return emit(
        "summary",
        total_rules=total_rules,
        total_new=total_new,
        total_skip=total_skip,
        total_error=total_error,
        duration=round(duration, 2),
    )
```

- [ ] **步骤 3：Commit**

```bash
cd /root/info-collector
git add APP/dashboard/migrations/002_task_enhance.sql APP/engine/engine/events.py
git commit -m "feat(engine): add events.py JSONL event stream protocol module"
```

---

### 任务 2：engine.py 集成事件发射

**文件：**
- 修改：`APP/engine/engine/engine.py`（run_all 和 run 方法）

- [ ] **步骤 1：确认现有 engine.py 的 run 和 run_all 方法签名**

```python
# 当前 engine.py 中的核心方法（需集成 events）
class InfoCollectorEngine:
    def run(self, rule_path: str) -> dict: ...
    def run_all(self, rules_dir: str) -> list[dict]: ...
```

- [ ] **步骤 2：修改 run() 方法，集成事件发射**

在 `engine.py` 的 `run()` 方法中，需要在开始时、每阶段完成时、出错时、结束时发射事件。

找到 `run` 方法（约在 engine.py 的 run 方法块），在其 `if fmt == "json"` 分支中，当 `fmt == "json"` 时改为逐行输出 JSONL。

**改造策略：** engine.run() 和 engine.run_all() 在 JSON 模式下输出 JSONL，接收一个 `emit_fn` 回调，默认打印到 stdout。

```python
# engine.py
# 在 run() 方法中，找到 result = ... 块，在其前后分别发射 start / complete / error 事件

def run(self, rule_path: str, event_handler=None) -> dict:
    """
    event_handler: 默认为 print（输出到 stdout，用于 CLI JSONL 模式）。
                   传入 None 则不发射事件（保持原有行为）。
    """
    import time
    start = time.time()

    if event_handler is None:
        event_handler = lambda line: print(line)

    rule = self.load_rule(rule_path)

    # 发射 start 事件
    from engine.events import event_start, event_status, event_error, event_complete, event_skip
    event_handler(event_start(rule_path))

    try:
        event_handler(event_status(rule_path, "running", "开始采集..."))
        items = self.crawl(rule)

        event_handler(event_status(rule_path, "running", f"采集完成，共 {len(items)} 条"))        new_items = self.deduplicate(items, rule)
        event_handler(event_status(rule_path, "running", f"去重后 {len(new_items)} 条新数据"))

        output_path = self.save_output(new_items, rule)
        duration = time.time() - start

        event_handler(event_complete(rule_path, new_count=len(new_items), duration=duration))
        return {"status": "success", "collected": len(new_items), "path": output_path, "duration": duration}

    except Exception as ex:
        duration = time.time() - start
        import traceback
        event_handler(event_error(rule_path, message=str(ex), detail=traceback.format_exc()[-200:]))
        event_handler(event_complete(rule_path, new_count=0, duration=duration))
        return {"status": "failed", "error": str(ex), "duration": duration}
```

- [ ] **步骤 3：修改 run_all() 方法，集成事件发射**

```python
def run_all(self, rules_dir: str, event_handler=None) -> list[dict]:
    """event_handler 传给每个 run() 调用，实现 JSONL 汇总输出"""
    if event_handler is None:
        event_handler = lambda line: print(line)

    from engine.events import event_start, event_status, event_skip, event_summary, event_error, event_complete
    import time
    start = time.time()

    rule_files = []
    for root, dirs, files in os.walk(rules_dir):
        for fname in sorted(files):
            if fname.endswith((".yaml", ".yml")):
                rule_files.append(os.path.join(root, fname))

    total_new = 0
    total_skip = 0
    total_error = 0
    results = []

    for rule_path in rule_files:
        rule = self.load_rule(rule_path)
        if not rule.get("enabled", True):
            event_handler(event_skip(rule_path, "rule_disabled"))
            results.append({"rule": rule_path, "status": "skipped", "reason": "rule_disabled"})
            total_skip += 1
            continue

        result = self.run(rule_path, event_handler=event_handler)
        results.append(result)
        if result.get("status") == "success":
            total_new += result.get("collected", 0)
        else:
            total_error += 1

    duration = time.time() - start
    event_handler(event_summary(
        total_rules=len(rule_files),
        total_new=total_new,
        total_skip=total_skip,
        total_error=total_error,
        duration=duration,
    ))
    return results
```

- [ ] **步骤 4：确认 engine.py 已有 os 和 traceback import**

检查 engine.py 文件头是否有 `import os` 和 `import traceback`，如果没有需要添加。

- [ ] **步骤 5：运行测试验证 engine 行为未破坏**

```bash
cd /root/info-collector/APP/engine
pytest tests/ --ignore=tests/test_crawl_browser.py -q
```

预期：所有测试通过（81 passed）

- [ ] **步骤 6：Commit**

```bash
git add APP/engine/engine/engine.py
git commit -m "feat(engine): integrate JSONL event emission into run() and run_all()"
```

---

### 任务 3：engine_cli.py JSONL 输出改造

**文件：**
- 修改：`APP/engine/engine_cli.py`（run_rule_cmd 和新增 run_all_json_cmd）

- [ ] **步骤 1：确认 run_rule_cmd 现有实现**

当前 `run_rule_cmd`（第 300-330 行）：fmt=="json" 时输出单行 JSON 结果。

**新增 --jsonl 选项，启用后输出逐行 JSONL 事件流：**

```python
@cli.command("run-rule")
@click.argument("rule_path")
@click.option("--format", "fmt", default="text")
def run_rule_cmd(rule_path, fmt):
    """手动执行单个规则"""
    import time
    start = time.time()
    try:
        full_path = _resolve_rule_path(rule_path)
        e = _engine()

        if fmt == "jsonl":
            # JSONL 模式：实时事件流
            def emit(line):
                click.echo(line)
            result = e.run(full_path, event_handler=emit)
            return  # 事件已在 emit 中输出，不需要额外输出

        # 原有 JSON 模式（单行结果）
        result = e.run(full_path)
        duration = time.time() - start
        if fmt == "json":
            click.echo(json.dumps({
                "success": result.get("status") == "success",
                "new_count": result.get("collected", 0),
                "duration": round(duration, 2),
            }, ensure_ascii=False))
        else:
            click.echo(f"OK, new={result.get('collected', 0)}, time={duration:.1f}s")
    except Exception as ex:
        duration = time.time() - start
        if fmt == "json":
            click.echo(json.dumps({
                "success": False,
                "error": str(ex),
                "duration": round(duration, 2),
            }, ensure_ascii=False))
        elif fmt == "jsonl":
            from engine.events import event_error, event_complete
            import traceback
            click.echo(event_error(rule_path, message=str(ex), detail=traceback.format_exc()[-200:]))
            click.echo(event_complete(rule_path, new_count=0, duration=duration))
        else:
            click.echo(f"ERROR: {ex}", err=True)
```

- [ ] **步骤 2：为 run-all 命令添加 JSONL 模式**

当前 `cmd_run_all`（第 139-150 行）为纯文本输出。新增 `run-all-jsonl` 命令，或修改现有命令支持 `--format jsonl`。

```python
@cli.command("run-all")
@click.option("--format", "fmt", default="text")
def cmd_run_all(fmt):
    """执行 rules/ 下所有已启用规则"""
    e = _engine()

    if fmt == "jsonl":
        def emit(line):
            click.echo(line)
        results = e.run_all(RULES_DIR, event_handler=emit)
        return

    # 原有文本模式
    print(f"扫描规则目录: {RULES_DIR}")
    results = e.run_all(RULES_DIR)
    print(f"\n执行完成，共 {len(results)} 条规则:")
    for r in results:
        icon = {"success": "✅", "failed": "❌", "skipped": "⏩"}.get(r["status"], "❓")
        print(f"  {icon} {r['rule']}: {r['status']}"
              + (f" | 采集:{r.get('collected', 0)}" if "collected" in r else "")
              + (f" | 错误:{r.get('error', '')[:60]}" if r.get("error") else ""))
```

- [ ] **步骤 3：运行测试验证 CLI 未破坏**

```bash
cd /root/info-collector/APP/engine
./venv.sh run python engine_cli.py list-rules --format=json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d[\"rules\"])} rules')"
```

预期：输出规则数量

- [ ] **步骤 4：Commit**

```bash
git add APP/engine/engine_cli.py
git commit -m "feat(engine_cli): add JSONL event stream output for run-rule and run-all"
```

---

### 任务 4：tasks_api.py 异步任务执行器

**文件：**
- 修改：`APP/dashboard/apis/tasks_api.py`（重写）

- [ ] **步骤 1：重写 tasks_api.py**

完全重写，实现：
- 异步任务表（内存）+ SSE per task
- 后台线程读取 engine_cli JSONL 事件
- 解析 `complete` / `error` / `skip` 事件更新 task_history

```python
"""
Tasks API — 异步任务执行 + per-task SSE 事件流
================================================
架构：
  POST /tasks/run-all    → 创建 task_history 记录 → 启动后台线程 → 返回 task_id
  POST /tasks/run-single/<path>  → 同上，单规则
  GET  /tasks/stream/<task_id>   → SSE 流，实时推送任务进度
  GET  /tasks/history   → 查询任务历史

Dashboard 是任务协调器（写入 task_history），engine 是纯执行器（输出 JSONL 事件）。
"""
import sqlite3
import subprocess
import json
import os
import threading
import time
import re
from flask import Blueprint, jsonify, Response, stream_with_context
from datetime import datetime

tasks_bp = Blueprint("tasks", __name__)

ENGINE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "engine"
)
VENV_PYTHON = os.path.join(ENGINE_DIR, ".venv", "bin", "python")
ENGINE_CLI = os.path.join(ENGINE_DIR, "engine_cli.py")
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard.db")

# 内存中的任务状态：{task_id: {"status": str, "rules": list, " SSE": EventSource}}
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
    """更新任务状态"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE task_history SET status=?, message=?, new_count=?, duration=? WHERE id=?",
        (status, message[:500] if message else "", new_count, duration, task_id)
    )
    conn.commit()
    conn.close()


def parse_event_line(line: str) -> dict | None:
    """解析 JSONL 行，返回 dict 或 None"""
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def run_task_async(task_id: int, cmd: list, task_name: str, trigger_type: str, rule_path: str):
    """
    后台线程函数：执行 engine_cli 命令，解析 JSONL 事件，更新 task_history + SSE。
    """
    from engine.events import event_complete, event_error, event_summary, event_skip, event_status

    state = {"status": "running", "progress": [], "sse_controllers": []}
    with _task_lock:
        _task_states[task_id] = state

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
    start = time.time()

    def sse_push(data: dict):
        """向所有订阅此任务的 SSE 连接推送消息"""
        with _task_lock:
            controllers = _task_states.get(task_id, {}).get("sse_controllers", [])
        for controller in controllers[:]:  # copy to avoid mutation during iteration
            try:
                controller(f"data: {json.dumps(data, ensure_ascii=False)}\n\n")
            except Exception:
                controllers.remove(controller)

    for raw_line in proc.stdout:
        event = parse_event_line(raw_line)
        if not event:
            continue

        etype = event.get("type", "")

        if etype == "item":
            # 实时数据项（可选择是否推送，减少 SSE 消息量）
            pass

        elif etype == "progress":
            sse_push({"type": "progress", "rule": event.get("rule", ""),
                      "phase": event.get("phase"), "current": event.get("current"),
                      "total": event.get("total")})

        elif etype == "status":
            sse_push({"type": "status", "rule": event.get("rule", ""),
                      "status": event.get("status"), "msg": event.get("msg", "")})

        elif etype == "error":
            error_message = event.get("message", "Unknown error")
            sse_push({"type": "error", "rule": event.get("rule", ""),
                      "message": error_message, "detail": event.get("detail", "")})
            total_error += 1

        elif etype == "skip":
            total_skip += 1
            sse_push({"type": "skip", "rule": event.get("rule", ""),
                      "reason": event.get("reason", "")})

        elif etype == "complete":
            nc = event.get("new_count", 0)
            total_new += nc
            sse_push({"type": "complete", "rule": event.get("rule", ""),
                      "new_count": nc, "duration": event.get("duration")})

        elif etype == "summary":
            duration = event.get("duration", time.time() - start)
            final_status = "failed" if error_message else "success"
            update_task(task_id, final_status, error_message, total_new, duration)
            sse_push({"type": "done", "success": final_status == "success",
                      "total_new": total_new, "total_skip": total_skip,
                      "total_error": total_error, "duration": duration})
            # 更新内存状态
            with _task_lock:
                if task_id in _task_states:
                    _task_states[task_id]["status"] = final_status

    proc.wait()
    # 若无 summary（进程异常退出），补一条最终状态
    if _task_states.get(task_id, {}).get("status") == "running":
        duration = time.time() - start
        final = "failed" if error_message or proc.returncode != 0 else "success"
        update_task(task_id, final, error_message, total_new, duration)
        sse_push({"type": "done", "success": final == "success",
                   "total_new": total_new, "total_skip": total_skip,
                   "total_error": total_error, "duration": duration})


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

    def generate():
        with _task_lock:
            if task_id not in _task_states:
                yield f"data: {json.dumps({'type': 'error', 'msg': 'task not found'})}\n\n"
                return
            state = _task_states[task_id]
            # 将 flask Response 的 streaming 函数作为 SSE controller
            from flask import request
            # 直接使用 yield 方式，flask 会自动处理

        # 检查任务是否已完成
        with _task_lock:
            initial_status = _task_states.get(task_id, {}).get("status", "running")

        yield f"data: {json.dumps({'type': 'start', 'task_id': task_id, 'status': initial_status})}\n\n"

        # 持续 yield 直到任务完成（超时 30 分钟）
        import time as time_mod
        start_wait = time_mod.time()
        while True:
            time_mod.sleep(1)
            with _task_lock:
                current = _task_states.get(task_id, {}).get("status", "running")
            if current != "running":
                break
            if time_mod.time() - start_wait > 1800:  # 30 分钟超时
                break

        yield f"data: {json.dumps({'type': 'done', 'status': current})}\n\n"

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


# ── 供外部触发的任务入口（cron_api 等调用） ──────────────────────────

def trigger_task(task_name: str, cmd: list, trigger_type: str = "manual", rule_path: str = "") -> int:
    """
    外部模块（cron_api）调用此函数创建任务记录并异步执行。
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
```

- [ ] **步骤 2：运行测试验证无语法错误**

```bash
cd /root/info-collector/APP/dashboard
python3 -c "import apis.tasks_api; print('OK')"
```

预期：输出 OK，无 ImportError

- [ ] **步骤 3：Commit**

```bash
git add APP/dashboard/apis/tasks_api.py
git commit -m "feat(dashboard): rewrite tasks_api with async task executor and per-task SSE"
```

---

### 任务 5：cron_api.py 任务链改造

**文件：**
- 修改：`APP/dashboard/apis/cron_api.py`

- [ ] **步骤 1：修改 _run_cron 闭包，改为调用 tasks_api.trigger_task**

找到 `_run_cron` 函数（约第 52 行），改为：

```python
from APP.dashboard.apis.tasks_api import trigger_task

def _run_cron(name, rule_path=rule_path):
    """Cron 触发时调用：创建任务记录并异步执行"""
    import subprocess, os
    ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine")
    VENV_PY = os.path.join(ENGINE_DIR, ".venv", "bin", "python")
    CLI = os.path.join(ENGINE_DIR, "engine_cli.py")

    task_name = f"cron: {name}"
    if rule_path:
        cmd = [VENV_PY, CLI, "run-rule", rule_path, "--format=jsonl"]
    else:
        cmd = [VENV_PY, CLI, "run-all", "--format=jsonl"]

    trigger_task(task_name=task_name, cmd=cmd, trigger_type="cron", rule_path=rule_path)
    # 不再等待，立即返回；任务在后台线程执行，通过 SSE 感知完成状态
```

- [ ] **步骤 2：修改 create_cron 的 name 参数处理**

当前 create_cron 接收 `name` 字符串，闭包中需要传递正确的 `name`。确保 `job_row` 中有 `name` 字段传入。

- [ ] **步骤 3：重启 Dashboard 并验证 cron 触发不报错**

```bash
# 重启 Dashboard
pkill -f "python.*server.py" 2>/dev/null; sleep 1
cd /root/info-collector/APP/dashboard && python3 server.py > /tmp/dashboard.log 2>&1 &
sleep 2
curl -s http://localhost:5000/api/cron | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'{len(d[\"crons\"])} crons')"
```

预期：无报错

- [ ] **步骤 4：Commit**

```bash
git add APP/dashboard/apis/cron_api.py
git commit -m "feat(cron): use trigger_task for async execution chain"
```

---

### 任务 6：rules_api.py /run 端点改为异步

**文件：**
- 修改：`APP/dashboard/apis/rules_api.py`

- [ ] **步骤 1：修改 /run 端点**

找到 `@rules_bp.route("/<path:rule_path>/run", methods=["POST"])` 端点（约第 109 行），改为：

```python
from APP.dashboard.apis.tasks_api import trigger_task

@rules_bp.route("/<path:rule_path>/run", methods=["POST"])
def run_rule(rule_path):
    """POST /api/rules/<path>/run — 立即返回 task_id，前端订阅 SSE 获取结果"""
    task_name = f"manual: {rule_path}"
    ENGINE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "engine")
    VENV_PY = os.path.join(ENGINE_DIR, ".venv", "bin", "python")
    CLI = os.path.join(ENGINE_DIR, "engine_cli.py")
    cmd = [VENV_PY, CLI, "run-rule", rule_path, "--format=jsonl"]

    task_id = trigger_task(task_name=task_name, cmd=cmd, trigger_type="manual", rule_path=rule_path)
    return jsonify({"task_id": task_id, "status": "running"})
```

- [ ] **步骤 2：Commit**

```bash
git add APP/dashboard/apis/rules_api.py
git commit -m "feat(rules): /run endpoint returns task_id for SSE subscription"
```

---

### 任务 7：前端 SSE 流订阅改造

**文件：**
- 修改：`APP/dashboard/static/js/app.js`

- [ ] **步骤 1：修改 TaskRunner 的 startRunAll**

将 `TaskRunner.startRunAll` 改为：
1. POST `/api/tasks/run-all`
2. 收到 `task_id` 后订阅 `GET /api/tasks/stream/<task_id>` SSE
3. SSE 收到 `done` 事件时更新任务历史

```javascript
const startRunAll = async () => {
    isRunning.value = true;
    output.value = [{ type: 'info', text: '正在创建任务...' }];

    try {
        // 1. 创建任务
        const { task_id } = await API.post('/tasks/run-all', {});

        // 2. 订阅 SSE
        const es = API.sse(`/api/tasks/stream/${task_id}`, {
            onData(data) {
                if (data.type === 'start') {
                    output.value.push({ type: 'info', text: '任务已启动，监控执行中...' });
                } else if (data.type === 'status' || data.type === 'progress') {
                    output.value.push({ type: 'log', text: `[${data.rule?.split('/').pop()}] ${data.msg || data.phase}` });
                } else if (data.type === 'error') {
                    output.value.push({ type: 'error', text: `[${data.rule?.split('/').pop()}] ❌ ${data.message}` });
                } else if (data.type === 'done') {
                    const icon = data.success ? '✅' : '❌';
                    output.value.push({ type: 'done', text: `${icon} 执行${data.success ? '成功' : '失败'} — 新增: ${data.total_new} | 跳过: ${data.total_skip} | 错误: ${data.total_error} | 耗时: ${data.duration}s` });
                    isRunning.value = false;
                    loadHistory();
                    es.close();
                }
            },
            onError() {
                output.value.push({ type: 'error', text: 'SSE 连接断开' });
                isRunning.value = false;
            }
        });
    } catch (err) {
        output.value.push({ type: 'error', text: '启动失败: ' + err.message });
        isRunning.value = false;
    }
};
```

- [ ] **步骤 2：修改 RuleList 的 runRule**

将 `RuleList.runRule` 改为：
1. POST `/api/tasks/run-single/<path>`
2. 收到 `task_id` 后订阅 SSE
3. 在弹窗中实时展示执行进度

```javascript
const runRule = async (rule) => {
    showRunDialog.value = true;
    runResult.value = null;
    runResultDuration.value = null;
    runOutput.value = [{ type: 'info', text: `正在执行 ${rule.name}...` }];

    try {
        const { task_id } = await API.post(`/tasks/run-single/${encodeURIComponent(rule.path)}`, {});

        const es = API.sse(`/api/tasks/stream/${task_id}`, {
            onData(data) {
                if (data.type === 'start') {
                    runOutput.value.push({ type: 'info', text: '任务已启动' });
                } else if (data.type === 'status' || data.type === 'progress') {
                    runOutput.value.push({ type: 'log', text: data.msg || `${data.phase} (${data.current}/${data.total})` });
                } else if (data.type === 'error') {
                    runOutput.value.push({ type: 'error', text: '❌ ' + data.message });
                } else if (data.type === 'complete') {
                    runOutput.value.push({ type: 'log', text: `✅ 完成: 新增 ${data.new_count} 条，耗时 ${data.duration}s` });
                    runResult.value = { success: true, new_count: data.new_count, duration: data.duration };
                } else if (data.type === 'done') {
                    runOutput.value.push({ type: 'done', text: `执行${data.success ? '成功' : '失败'}` });
                    es.close();
                }
            },
            onError() {
                runOutput.value.push({ type: 'error', text: '连接断开' });
            }
        });
    } catch (err) {
        runResult.value = { success: false, error: err.message };
    }
};

// 在 RuleList setup 中添加
const runOutput = ref([]);

// return 中添加
runOutput,
```

同时在模板中对话框里展示 `runOutput` 实时日志。

- [ ] **步骤 3：验证静态文件无语法错误**

```bash
curl -s http://localhost:5000/static/js/app.js | head -5
```

预期：返回 JS 代码（200）

- [ ] **步骤 4：Commit**

```bash
git add APP/dashboard/static/js/app.js
git commit -m "feat(dashboard): frontend subscribes to per-task SSE streams"
```

---

### 任务 8：文档同步（SPEC.md 更新）

**文件：**
- 修改：`APP/engine/SPEC.md`

- [ ] **步骤 1：在 SPEC.md 新增章节「事件流协议」**

在第 8 节（Implementation Tasks）之后添加：

```markdown
## 9. Event Stream Protocol（JSONL）

当 engine_cli 以 `--format=jsonl` 运行时，所有输出均为逐行 JSON（JSONL）。

### 9.1 事件类型

| type | 触发时机 | 必含字段 | 说明 |
|------|---------|---------|------|
| `start` | 开始执行单个规则 | rule, ts | 单 rule 模式 |
| `status` | 状态变化 | rule, status, msg | running/success/failed |
| `item` | 每条新数据 | rule, data | 仅新增数据 |
| `progress` | 分页/批量进度 | rule, phase, current, total | fetch/parse/save |
| `error` | 出错 | rule, message, detail | detail 含 traceback 摘要 |
| `skip` | 跳过规则 | rule, reason | rule_disabled/already_latest |
| `complete` | 单规则完成 | rule, new_count, skip_count, duration | |
| `summary` | run-all 全部结束 | total_rules, total_new, total_skip, total_error, duration | 仅 run-all 末尾 |

### 9.2 数据流

```
engine_cli --format=jsonl
    ↓ JSONL 事件流
Dashboard tasks_api（后台线程）
    ↓ 解析事件
SQLite task_history（写入状态）
    ↓ SSE
前端（实时展示）
```

### 9.3 任务链路

| 触发方式 | 触发类型 (trigger_type) | 任务记录 |
|---------|----------------------|---------|
| 手动执行所有 | `manual` | ✅ 写入 task_history |
| 手动执行单个 | `manual` | ✅ 写入 task_history |
| Cron 调度 | `cron` | ✅ 写入 task_history |
| API 调用 | `api` | ✅ 写入 task_history |

## 10. Dashboard API

### 10.1 任务 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/tasks/run-all` | POST | 创建任务，立即返回 task_id |
| `/api/tasks/run-single/<path>` | POST | 单规则异步执行，返回 task_id |
| `/api/tasks/stream/<task_id>` | GET | SSE 流订阅任务实时进度 |
| `/api/tasks/history` | GET | 查询最近 50 条任务历史 |
| `/api/tasks/<id>` | GET | 查询单个任务详情 |

### 10.2 task_history 表结构

```sql
CREATE TABLE task_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT NOT NULL,
    status TEXT DEFAULT 'pending',   -- pending/running/success/failed/skipped
    message TEXT,
    new_count INTEGER DEFAULT 0,
    duration REAL DEFAULT 0.0,
    trigger_type TEXT DEFAULT 'manual',  -- manual/cron/api
    rule_path TEXT,                        -- 单规则执行时记录
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```
```

同时将 SPEC.md 第 2 节的 Data Flow 图更新，加入事件流路径。

- [ ] **步骤 2：Commit**

```bash
git add APP/engine/SPEC.md
git commit -m "docs: update SPEC.md with event stream protocol and task API"
```

---

## 自检清单

- [ ] 规格覆盖：所有 4 个问题（错误丢失、Cron 无追踪、单规则无 SSE、路径生成）均有对应任务
- [ ] 占位符扫描：无 "TODO"、"待定"、"后续" 等字样
- [ ] 类型一致性：event_handler 签名在 engine.py 和 events.py 中一致
- [ ] 事件类型：8 种事件类型全部定义在 events.py 中，engine.py 仅调用
- [ ] trigger_type 字段：所有触发路径（manual/cron）均写入 task_history
- [ ] 迁移幂等：002_task_enhance.sql 使用 ALTER TABLE，重复执行应兼容（或加 IF NOT EXISTS 逻辑）

---

## 执行方式选择

**计划已完成并保存到 `docs/superpowers/plans/2026-05-03-dashboard-task-enhancement.md`。**

两种执行方式：

1. **子代理驱动（推荐）** - 每个任务调度一个新的子代理，任务间进行审查，快速迭代
2. **内联执行** - 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

**选哪种？**
