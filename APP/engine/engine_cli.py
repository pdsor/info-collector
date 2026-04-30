#!/usr/bin/env python3
"""
InfoCollector Engine CLI
========================
规范入口：通过 venv.sh run engine_cli.py 调用，
不在 venv 中时会主动检查并退出。

用法:
  python3 engine_cli.py --help
  python3 engine_cli.py run-all
  python3 engine_cli.py run <rule_name>
  python3 engine_cli.py rules
  python3 engine_cli.py state
  python3 engine_cli.py scan

JSON 输出命令:
  python3 engine_cli.py list-rules --format=json
  python3 engine_cli.py get-rule <path> --format=json
  python3 engine_cli.py put-rule <path> --yaml-content "..."
  python3 engine_cli.py delete-rule <path>
  python3 engine_cli.py enable-rule <path> --enable=true|false
  python3 engine_cli.py run-rule <path> --format=json
  python3 engine_cli.py list-logs --format=json
  python3 engine_cli.py read-log <name> --lines=N --format=json
"""

import sys
import os

# ── Venv Guard ──────────────────────────────────────────────
_VENV_PATH = os.path.join(os.path.dirname(__file__), ".venv", "bin", "python")
if sys.executable != _VENV_PATH and os.path.exists(os.path.join(os.path.dirname(__file__), ".venv")):
    print("ERROR: 请使用虚拟环境运行此脚本。", file=sys.stderr)
    print("正确方式: ./venv.sh run python engine_cli.py [...]\n或激活虚拟环境: source .venv/bin/activate", file=sys.stderr)
    sys.exit(1)

# ── Imports ──────────────────────────────────────────────────
import json
import click

# Add engine package to path
sys.path.insert(0, os.path.dirname(__file__))

from engine.engine import InfoCollectorEngine


# ── Path Helpers ─────────────────────────────────────────────
# ENGINE_ROOT = APP/engine/ 的父目录（即项目根目录 APP/）
ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(os.path.dirname(__file__), "rules")
STATE_DIR = os.path.join(os.path.dirname(__file__), "output")
DEDUP_DB = os.path.join(os.path.dirname(__file__), "dedup.db")


def _engine(state_dir=None):
    if state_dir is None:
        state_dir = STATE_DIR
    return InfoCollectorEngine(
        dedup_db_path=DEDUP_DB,
        state_dir=state_dir,
    )


def _all_rule_files(rules_dir: str):
    """Recursively yield all YAML file paths under rules_dir."""
    for root, dirs, files in os.walk(rules_dir):
        for fname in sorted(files):
            if fname.endswith(".yaml") or fname.endswith(".yml"):
                yield os.path.join(root, fname)


def _rule_path(name: str, rules_dir=None) -> str:
    """Find rule YAML path by rule name (search recursively)."""
    if rules_dir is None:
        rules_dir = RULES_DIR
    import yaml
    for fpath in _all_rule_files(rules_dir):
        with open(fpath, encoding="utf-8") as f:
            rule = yaml.safe_load(f)
        if rule and rule.get("name") == name:
            return fpath
    return None


def _resolve_rule_path(rule_path: str) -> str:
    """Resolve relative rule path to absolute path under engine/rules/."""
    # rule_path is relative to APP/engine/, e.g. "rules/数据要素/tmtpost.yaml"
    return os.path.join(os.path.dirname(__file__), rule_path)


def _print_state(state_mgr):
    """Pretty print current state.json"""
    rules = state_mgr.get_rules()
    executions = state_mgr.get_executions(limit=20)
    errors = state_mgr.get_errors(limit=10)
    stats = state_mgr.get_stats()
    state = state_mgr._state
    subjects = state.get("subjects", {})

    print("\n═══ 事项概览 ═══")
    for sub, info in subjects.items():
        rule_count = len(info.get("rule_names", []))
        print(f"  📁 {sub} ({rule_count} 条来源)")

    print("\n═══ 全局统计 ═══")
    print(f"  总运行次数 : {stats.get('total_runs', 0)}")
    print(f"  总采集条数 : {stats.get('total_collected', 0)}")
    print(f"  失败次数   : {stats.get('total_failed', 0)}")

    print(f"\n═══ 规则列表 ({len(rules)} 条) ═══")
    for r in rules:
        status_icon = "✅" if r["last_run_status"] == "success" else (
            "❌" if r["last_run_status"] == "failed" else "⏳")
        sub = r.get("subject", "—")
        print(f"  {status_icon} {r['name']} | {r.get('platform','')} | "
              f"[{sub}] | 启用:{r['enabled']} | 最近:{r.get('last_collected', 0)}条")

    if executions:
        print(f"\n═══ 最近执行 ({len(executions)} 条) ═══")
        for e in executions[:10]:
            icon = {"success": "✅", "failed": "❌", "running": "🔄"}.get(e["status"], "⏳")
            dur = f"{e['duration_sec']}s" if e.get("duration_sec") else "—"
            print(f"  {icon} {e['rule_name']} | {e['status']} | "
                  f"采集:{e.get('collected', 0)} | 耗时:{dur}")

    if errors:
        print(f"\n═══ 最近错误 ({len(errors)} 条) ═══")
        for e in errors[:5]:
            print(f"  ❌ [{e['rule_name']}] {e['error'][:80]}")


# ── Legacy Commands (preserved from original CLI) ─────────────
@click.group()
def cli():
    """InfoCollector Engine CLI"""
    pass


@cli.command("run-all")
def cmd_run_all():
    """执行 rules/ 下所有已启用规则"""
    e = _engine()
    print(f"扫描规则目录: {RULES_DIR}")
    results = e.run_all(RULES_DIR)
    print(f"\n执行完成，共 {len(results)} 条规则:")
    for r in results:
        icon = {"success": "✅", "failed": "❌", "skipped": "⏩"}.get(r["status"], "❓")
        print(f"  {icon} {r['rule']}: {r['status']}"
              + (f" | 采集:{r.get('collected', 0)}" if "collected" in r else "")
              + (f" | 错误:{r.get('error', '')[:60]}" if r.get("error") else ""))


@cli.command("run")
@click.argument("rule_name")
def cmd_run(rule_name):
    """执行指定规则（按规则名称）"""
    rule_path = _rule_path(rule_name)
    if not rule_path:
        click.echo(f"错误: 未找到规则 '{rule_name}'", err=True)
        sys.exit(1)
    e = _engine()
    print(f"执行规则: {rule_name} ({rule_path})")
    result = e.run(rule_path)
    icon = {"success": "✅", "failed": "❌", "skipped": "⏩"}.get(result["status"], "❓")
    print(f"  {icon} 状态: {result['status']}"
          + (f" | 采集: {result.get('collected', 0)} 条" if "collected" in result else "")
          + (f" | 去重过滤: {result.get('dedup_filtered', 0)} 条" if "dedup_filtered" in result else "")
          + (f"\n  错误: {result.get('error', '')}" if result.get("error") else ""))


@cli.command("rules")
def cmd_rules():
    """列出所有可用规则"""
    if not os.path.isdir(RULES_DIR):
        click.echo(f"规则目录不存在: {RULES_DIR}")
        sys.exit(1)
    import yaml
    print(f"═══ 规则文件 ({RULES_DIR}) ═══")
    for fpath in _all_rule_files(RULES_DIR):
        with open(fpath, encoding="utf-8") as f:
            rule = yaml.safe_load(f)
        enabled = "✅" if rule.get("enabled", True) else "❌"
        name = rule.get("name", os.path.basename(fpath))
        platform = rule.get("source", {}).get("platform", "—")
        stype = rule.get("source", {}).get("type", "—")
        subject = rule.get("subject") or rule.get("source", {}).get("subject", "—")
        print(f"  {enabled} {name} [{platform}|{subject}] <{stype}>")


@cli.command("state")
def cmd_state():
    """查看当前采集状态"""
    state_file = os.path.join(STATE_DIR, "state.json")
    if not os.path.exists(state_file):
        click.echo("state.json 尚不存在，先运行一次采集任务。")
        sys.exit(0)
    e = _engine(state_dir=STATE_DIR)
    _print_state(e.state_mgr)


@cli.command("scan")
def cmd_scan():
    """扫描规则目录并注册到 state.json"""
    e = _engine(state_dir=STATE_DIR)
    count = e.state_mgr.scan_and_register_rules(RULES_DIR)
    click.echo(f"已注册 {count} 条规则到 state.json")


# ── New JSON-capable Commands ─────────────────────────────────

@cli.command("list-rules")
@click.option("--format", "fmt", default="text")
def list_rules_cmd(fmt):
    """列出所有已注册规则（从 state.json 读取）"""
    from engine.state import StateManager
    state_mgr = StateManager(STATE_DIR)
    state = state_mgr._state
    rules = []
    for name, info in state.get("rules", {}).items():
        rules.append({
            "name": info.get("name", name),
            "platform": info.get("platform", ""),
            "subject": info.get("subject", ""),
            "path": info.get("path", ""),
            "enabled": info.get("enabled", True),
            "last_run": info.get("last_run"),
            "last_status": info.get("last_status"),
        })
    if fmt == "json":
        click.echo(json.dumps({"rules": rules}, ensure_ascii=False))
    else:
        for r in rules:
            click.echo(f"{r['subject']}/{r['platform']} {r['name']} [{'ON' if r['enabled'] else 'OFF'}]")


@cli.command("get-rule")
@click.argument("rule_path")
@click.option("--format", "fmt", default="text")
def get_rule_cmd(rule_path, fmt):
    """读取规则 YAML 文件内容"""
    full_path = _resolve_rule_path(rule_path)
    if not os.path.exists(full_path):
        result = {"error": "文件不存在"}
        click.echo(json.dumps(result, ensure_ascii=False), err=True)
        return
    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()
    if fmt == "json":
        click.echo(json.dumps({"yaml": content, "path": rule_path}, ensure_ascii=False))
    else:
        click.echo(content)


@cli.command("put-rule")
@click.argument("rule_path")
@click.option("--yaml-content", default=None)
def put_rule_cmd(rule_path, yaml_content):
    """写入规则 YAML 文件"""
    full_path = _resolve_rule_path(rule_path)
    if yaml_content is None:
        yaml_content = click.get_text_stream("stdin").read()
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    click.echo(json.dumps({"success": True}))


@cli.command("delete-rule")
@click.argument("rule_path")
def delete_rule_cmd(rule_path):
    """删除规则 YAML 文件"""
    full_path = _resolve_rule_path(rule_path)
    if not os.path.exists(full_path):
        click.echo(json.dumps({"error": "文件不存在"}), err=True)
        return
    os.remove(full_path)
    click.echo(json.dumps({"success": True}))


@cli.command("enable-rule")
@click.argument("rule_path")
@click.option("--enable", "enabled", type=bool, default=None)
def enable_rule_cmd(rule_path, enabled):
    """启用/停用规则（修改 YAML 中 source.enabled 字段）"""
    import yaml
    full_path = _resolve_rule_path(rule_path)
    if not os.path.exists(full_path):
        click.echo(json.dumps({"error": "文件不存在"}), err=True)
        return
    with open(full_path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    if enabled is None:
        enabled = not doc.get("source", {}).get("enabled", True)
    if "source" not in doc:
        doc["source"] = {}
    doc["source"]["enabled"] = enabled
    with open(full_path, "w", encoding="utf-8") as f:
        yaml.dump(doc, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    click.echo(json.dumps({"success": True, "enabled": enabled}))


@cli.command("run-rule")
@click.argument("rule_path")
@click.option("--format", "fmt", default="text")
def run_rule_cmd(rule_path, fmt):
    """手动执行单个规则，返回 JSON 结果"""
    import time
    start = time.time()
    try:
        # rule_path here is a file path, use _resolve_rule_path for full path
        full_path = _resolve_rule_path(rule_path)
        e = _engine()
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
        else:
            click.echo(f"ERROR: {ex}", err=True)


@cli.command("list-logs")
@click.option("--format", "fmt", default="text")
def list_logs_cmd(fmt):
    """列出 engine/logs/ 下的日志文件"""
    from datetime import datetime
    logs_dir = os.path.join(os.path.dirname(__file__), "logs")
    if not os.path.exists(logs_dir):
        logs = []
    else:
        logs = []
        for fname in sorted(os.listdir(logs_dir), reverse=True):
            if fname.endswith(".log"):
                fpath = os.path.join(logs_dir, fname)
                logs.append({
                    "name": fname,
                    "size": os.path.getsize(fpath),
                    "modified_at": datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat()
                })
    if fmt == "json":
        click.echo(json.dumps({"logs": logs}, ensure_ascii=False))
    else:
        for l in logs:
            click.echo(f"{l['name']} ({l['size']} bytes)")


@cli.command("read-log")
@click.argument("log_name")
@click.option("--lines", "line_count", default=100, type=int)
@click.option("--format", "fmt", default="text")
def read_log_cmd(log_name, line_count, fmt):
    """读取日志文件内容"""
    safe_name = os.path.basename(log_name)  # 防止路径穿越
    logs_dir = os.path.join(os.path.dirname(__file__), "logs")
    fpath = os.path.join(logs_dir, safe_name)
    if not os.path.exists(fpath):
        click.echo(json.dumps({"error": "日志文件不存在"}), err=True)
        return
    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    tail = all_lines[-line_count:]
    if fmt == "json":
        click.echo(json.dumps({
            "lines": [l.rstrip("\n") for l in tail],
            "total": len(all_lines)
        }, ensure_ascii=False))
    else:
        for line in tail:
            click.echo(line.rstrip("\n"))


# ── Main ─────────────────────────────────────────────────────
if __name__ == "__main__":
    cli()
