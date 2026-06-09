"""当前 YAML 规则作用域工具。"""

import os

import yaml

DASHBOARD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.dirname(DASHBOARD_DIR)
ENGINE_DIR = os.path.join(APP_DIR, "engine")
RULES_DIR = os.path.join(ENGINE_DIR, "rules")


def iter_rule_files(rules_dir: str = RULES_DIR):
    """遍历当前真实存在的 YAML 规则文件。"""
    if not os.path.isdir(rules_dir):
        return
    for root, dirs, files in os.walk(rules_dir):
        dirs.sort()
        for fname in sorted(files):
            if fname.endswith((".yaml", ".yml")):
                yield os.path.join(root, fname)


def normalize_rule_path(path: str) -> str:
    """统一规则路径为相对 APP/engine 的 POSIX 风格路径。"""
    if not path:
        return ""
    if os.path.isabs(path):
        try:
            path = os.path.relpath(path, ENGINE_DIR)
        except ValueError:
            pass
    return path.replace("\\", "/")


def current_rule_scopes() -> set[tuple[str, str]]:
    """返回当前 YAML 中声明的 (subject, platform) 集合。"""
    scopes: set[tuple[str, str]] = set()
    for path in iter_rule_files():
        try:
            with open(path, "r", encoding="utf-8") as f:
                rule = yaml.safe_load(f) or {}
        except Exception:
            continue
        if not isinstance(rule, dict):
            continue
        source = rule.get("source") or {}
        subject = rule.get("subject") or source.get("subject") or ""
        platform = source.get("platform") or rule.get("source_id") or os.path.splitext(os.path.basename(path))[0]
        if subject and platform:
            scopes.add((str(subject), str(platform)))
    return scopes


def is_current_scope(subject: str, platform: str) -> bool:
    """判断产物是否属于当前 YAML 规则作用域。"""
    scopes = current_rule_scopes()
    if not scopes:
        return False
    return (str(subject or ""), str(platform or "")) in scopes
