#!/usr/bin/env python3
"""
InfoCollector Engine CLI
========================
规范入口：通过 venv.sh run engine_cli.py 调用，
不在 venv 中时会主动检查并退出。

用法:
  python3 engine_cli.py --help
  python3 engine_cli.py --run-all
  python3 engine_cli.py --run <rule_name>
  python3 engine_cli.py --rules
  python3 engine_cli.py --state
  python3 engine_cli.py --scan
"""

import sys
import os

# ── Venv Guard ──────────────────────────────────────────────
_VENV_PATH = os.path.join(os.path.dirname(__file__), ".venv", "bin", "python")
if sys.executable != _VENV_PATH and os.path.exists(os.path.join(os.path.dirname(__file__), ".venv")):
    print("ERROR: 请使用虚拟环境运行此脚本。", file=sys.stderr)
    print("正确方式: ./venv.sh run python engine_cli.py [...]", file=sys.stderr)
    print("或激活虚拟环境: source .venv/bin/activate", file=sys.stderr)
    sys.exit(1)

# ── Imports ──────────────────────────────────────────────────
import argparse
import json
import os
from pathlib import Path

# Add engine package to path
sys.path.insert(0, os.path.dirname(__file__))

from engine.engine import InfoCollectorEngine


# ── Helpers ──────────────────────────────────────────────────
def _engine(state_dir=None):
    if state_dir is None:
        state_dir = os.path.join(os.path.dirname(__file__), "output")
    return InfoCollectorEngine(
        dedup_db_path=os.path.join(os.path.dirname(__file__), "dedup.db"),
        state_dir=state_dir,
    )


def _rule_path(name: str, rules_dir=None) -> str:
    if rules_dir is None:
        rules_dir = os.path.join(os.path.dirname(__file__), "rules")
    for fname in os.listdir(rules_dir):
        if fname.endswith(".yaml") or fname.endswith(".yml"):
            import yaml
            with open(os.path.join(rules_dir, fname)) as f:
                rule = yaml.safe_load(f)
            if rule and rule.get("name") == name:
                return os.path.join(rules_dir, fname)
    return None


def _print_state(state_mgr):
    """Pretty print current state.json"""
    rules = state_mgr.get_rules()
    executions = state_mgr.get_executions(limit=20)
    errors = state_mgr.get_errors(limit=10)
    stats = state_mgr.get_stats()

    print("\n═══ 全局统计 ═══")
    print(f"  总运行次数 : {stats.get('total_runs', 0)}")
    print(f"  总采集条数 : {stats.get('total_collected', 0)}")
    print(f"  失败次数   : {stats.get('total_failed', 0)}")

    print(f"\n═══ 规则列表 ({len(rules)} 条) ═══")
    for r in rules:
        status_icon = "✅" if r["last_run_status"] == "success" else (
            "❌" if r["last_run_status"] == "failed" else "⏳")
        print(f"  {status_icon} {r['name']} | {r.get('platform','')} | "
              f"启用:{r['enabled']} | 最近采集:{r.get('last_collected', 0)}条")

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


# ── Commands ─────────────────────────────────────────────────
def cmd_run_all(args):
    rules_dir = os.path.join(os.path.dirname(__file__), "rules")
    e = _engine()
    print(f"扫描规则目录: {rules_dir}")
    results = e.run_all(rules_dir)
    print(f"\n执行完成，共 {len(results)} 条规则:")
    for r in results:
        icon = {"success": "✅", "failed": "❌", "skipped": "⏩"}.get(r["status"], "❓")
        print(f"  {icon} {r['rule']}: {r['status']}"
              + (f" | 采集:{r.get('collected', 0)}" if "collected" in r else "")
              + (f" | 错误:{r.get('error', '')[:60]}" if r.get("error") else ""))


def cmd_run(args):
    rule_path = _rule_path(args.rule_name)
    if not rule_path:
        print(f"错误: 未找到规则 '{args.rule_name}'", file=sys.stderr)
        sys.exit(1)
    e = _engine()
    print(f"执行规则: {args.rule_name} ({rule_path})")
    result = e.run(rule_path)
    icon = {"success": "✅", "failed": "❌", "skipped": "⏩"}.get(result["status"], "❓")
    print(f"  {icon} 状态: {result['status']}"
          + (f" | 采集: {result.get('collected', 0)} 条" if "collected" in result else "")
          + (f" | 去重过滤: {result.get('dedup_filtered', 0)} 条" if "dedup_filtered" in result else "")
          + (f"\n  错误: {result.get('error', '')}" if result.get("error") else ""))


def cmd_rules(args):
    rules_dir = os.path.join(os.path.dirname(__file__), "rules")
    if not os.path.isdir(rules_dir):
        print(f"规则目录不存在: {rules_dir}")
        sys.exit(1)
    import yaml
    print(f"═══ 规则文件 ({rules_dir}) ═══")
    for fname in sorted(os.listdir(rules_dir)):
        if not (fname.endswith(".yaml") or fname.endswith(".yml")):
            continue
        fpath = os.path.join(rules_dir, fname)
        with open(fpath) as f:
            rule = yaml.safe_load(f)
        enabled = "✅" if rule.get("enabled", True) else "❌"
        name = rule.get("name", fname)
        platform = rule.get("source", {}).get("platform", "—")
        stype = rule.get("source", {}).get("type", "—")
        print(f"  {enabled} {name} [{platform}] <{stype}>")


def cmd_state(args):
    state_dir = os.path.join(os.path.dirname(__file__), "output")
    state_file = os.path.join(state_dir, "state.json")
    if not os.path.exists(state_file):
        print("state.json 尚不存在，先运行一次采集任务。")
        sys.exit(0)
    e = _engine(state_dir=state_dir)
    _print_state(e.state_mgr)


def cmd_scan(args):
    rules_dir = os.path.join(os.path.dirname(__file__), "rules")
    state_dir = os.path.join(os.path.dirname(__file__), "output")
    e = _engine(state_dir=state_dir)
    count = e.state_mgr.scan_and_register_rules(rules_dir)
    print(f"已注册 {count} 条规则到 state.json")


# ── Main ─────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="InfoCollector Engine CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("run-all", help="执行 rules/ 下所有已启用规则").set_defaults(func=cmd_run_all)

    run_parser = sub.add_parser("run", help="执行指定规则")
    run_parser.add_argument("rule_name", help="规则名称")
    run_parser.set_defaults(func=cmd_run)

    sub.add_parser("rules", help="列出所有可用规则").set_defaults(func=cmd_rules)
    sub.add_parser("state", help="查看当前采集状态").set_defaults(func=cmd_state)
    sub.add_parser("scan", help="扫描规则目录并注册到 state.json").set_defaults(func=cmd_scan)

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        print("\n快速开始:")
        print("  ./venv.sh run python engine_cli.py scan       # 注册规则到 state.json")
        print("  ./venv.sh run python engine_cli.py rules      # 查看所有规则")
        print("  ./venv.sh run python engine_cli.py run-all    # 执行全部规则")
        print("  ./venv.sh run python engine_cli.py state      # 查看采集状态")
        return

    args.func(args)


if __name__ == "__main__":
    main()
