"""StateManager - 采集状态记录与查询"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


class StateManager:
    """管理采集系统的实时状态（规则配置 + 执行历史 + 错误日志）"""

    STATE_FILE = "state.json"

    # 状态常量
    STATUS_PENDING = "pending"      # 待执行
    STATUS_RUNNING = "running"     # 执行中
    STATUS_SUCCESS = "success"     # 成功
    STATUS_FAILED = "failed"       # 失败
    STATUS_DISABLED = "disabled"   # 已禁用

    def __init__(self, state_dir: str = "."):
        self.state_dir = state_dir
        self.state_file = os.path.join(state_dir, self.STATE_FILE)
        self._ensure_state_dir()
        self._state = self._load()

    def _ensure_state_dir(self):
        os.makedirs(self.state_dir, exist_ok=True)

    def _load(self) -> dict:
        """加载状态文件，不存在则返回空结构"""
        if not os.path.exists(self.state_file):
            return self._empty_state()
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            # Migration: add 'subjects' key if missing (old state format)
            if "subjects" not in state:
                state["subjects"] = {}
            return state
        except (json.JSONDecodeError, IOError):
            return self._empty_state()

    def _empty_state(self) -> dict:
        return {
            "subjects": {},   # subject_name -> {display_name, rule_names}
            "rules": {},      # rule_name -> rule_config
            "executions": [], # 最近 N 条执行记录
            "errors": [],     # 最近 N 条错误
            "stats": {
                "total_collected": 0,
                "total_runs": 0,
                "total_failed": 0,
            }
        }

    def _save(self):
        """持久化状态到文件"""
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)

    # ── 规则管理 ──────────────────────────────────────────────

    def register_rule(self, rule_path: str, rule: dict) -> str:
        """注册或更新规则，同时注册/更新 subject。返回规则唯一标识（name）。"""
        name = rule.get("name", os.path.basename(rule_path))
        enabled = rule.get("enabled", True)
        subject = rule.get("subject") or rule.get("source", {}).get("subject")

        # Register subject if not exists, update rule_names list otherwise
        if subject:
            if subject not in self._state["subjects"]:
                self._state["subjects"][subject] = {
                    "display_name": subject,
                    "rule_names": [],
                }
            subject_entry = self._state["subjects"][subject]
            if name not in subject_entry["rule_names"]:
                subject_entry["rule_names"].append(name)

        rule_entry = {
            "name": name,
            "version": rule.get("version", "1.0.0"),
            "description": rule.get("description", ""),
            "subject": subject or "",
            "platform": rule.get("source", {}).get("platform", ""),
            "source_type": rule.get("source", {}).get("type", "html"),
            "url": rule.get("source", {}).get("url") or rule.get("source", {}).get("base_url", ""),
            "enabled": enabled,
            "rule_path": rule_path,
            "registered_at": datetime.now().isoformat(),
            "last_run_at": None,
            "last_run_status": None,
            "last_collected": 0,
            "last_dedup_filtered": 0,
            "last_error": None,
            "total_runs": 0,
            "total_collected": 0,
        }

        self._state["rules"][name] = rule_entry
        self._save()
        return name

    def set_rule_enabled(self, name: str, enabled: bool):
        """启用/禁用规则"""
        if name in self._state["rules"]:
            self._state["rules"][name]["enabled"] = enabled
            self._save()

    def get_rules(self) -> list:
        """获取所有规则列表"""
        return list(self._state["rules"].values())

    def get_rule(self, name: str) -> Optional[dict]:
        return self._state["rules"].get(name)

    # ── 执行记录 ──────────────────────────────────────────────

    def record_start(self, rule_name: str) -> str:
        """记录任务开始，返回 execution_id"""
        execution_id = f"exec_{datetime.now().strftime('%Y%m%d%H%M%S')}_{rule_name}"
        exec_entry = {
            "execution_id": execution_id,
            "rule_name": rule_name,
            "status": self.STATUS_RUNNING,
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "duration_sec": None,
            "collected": 0,
            "dedup_filtered": 0,
            "error": None,
        }
        self._state["executions"].insert(0, exec_entry)
        # 只保留最近 100 条执行记录
        self._state["executions"] = self._state["executions"][:100]
        self._save()
        return execution_id

    def _resolve_http_path(self, output_path: str) -> str:
        """将本地 output_path 转为 HTTP 可访问的绝对路径。

        engine CWD 可能是项目根 /root/info-collector/ 或 APP/engine/ 目录，
        但 HTTP 服务根固定在项目根 /root/info-collector/。
        """
        if not output_path:
            return output_path
        # 统一转为绝对路径（基于 state_dir）
        if not os.path.isabs(output_path):
            abs_path = os.path.abspath(os.path.join(self.state_dir, '..', output_path.lstrip('./')))
        else:
            abs_path = output_path
        # 对于绝对路径（如 /tmp/...），计算相对于项目根的路径
        try:
            rel = os.path.relpath(abs_path, '/root/info-collector')
            # 去掉 ../ 前缀，转为 HTTP 绝对路径
            while rel.startswith('../'):
                rel = rel[3:]
            return '/' + rel if rel != '.' else '/'
        except ValueError:
            return output_path

    def record_finish(self, execution_id: str, rule_name: str,
                      collected: int, dedup_filtered: int,
                      output_path: str, error: str = None):
        """记录任务完成"""
        now = datetime.now()
        status = self.STATUS_FAILED if error else self.STATUS_SUCCESS

        for exec_entry in self._state["executions"]:
            if exec_entry["execution_id"] == execution_id:
                started = datetime.fromisoformat(exec_entry["started_at"])
                exec_entry["status"] = status
                exec_entry["finished_at"] = now.isoformat()
                exec_entry["duration_sec"] = round((now - started).total_seconds(), 1)
                exec_entry["collected"] = collected
                exec_entry["dedup_filtered"] = dedup_filtered
                exec_entry["error"] = error
                exec_entry["output_path"] = self._resolve_http_path(output_path)
                break

        # 更新规则统计
        if rule_name in self._state["rules"]:
            r = self._state["rules"][rule_name]
            r["last_run_at"] = now.isoformat()
            r["last_run_status"] = status
            r["last_collected"] = collected
            r["last_dedup_filtered"] = dedup_filtered
            r["total_runs"] = r.get("total_runs", 0) + 1
            r["total_collected"] = r.get("total_collected", 0) + collected
            if error:
                r["last_error"] = error[:200]

        # 更新全局统计
        self._state["stats"]["total_runs"] += 1
        self._state["stats"]["total_collected"] += collected
        if error:
            self._state["stats"]["total_failed"] += 1

        # 记录错误详情
        if error:
            self._state["errors"].insert(0, {
                "rule_name": rule_name,
                "execution_id": execution_id,
                "error": error[:500],
                "occurred_at": now.isoformat(),
            })
            self._state["errors"] = self._state["errors"][:50]  # 保留最近50条

        self._save()

    def get_executions(self, limit: int = 20) -> list:
        """获取最近执行记录"""
        return self._state["executions"][:limit]

    def get_errors(self, limit: int = 20) -> list:
        """获取最近错误记录"""
        return self._state["errors"][:limit]

    def get_stats(self) -> dict:
        """获取全局统计"""
        return self._state.get("stats", {})

    # ── 全量规则扫描注册 ──────────────────────────────────────

    def scan_and_register_rules(self, rules_dir: str) -> int:
        """扫描 rules 目录（含子目录），自动注册所有 YAML 规则文件。"""
        import yaml
        count = 0

        def scan_dir(directory: str):
            nonlocal count
            for entry in sorted(os.listdir(directory)):
                full_path = os.path.join(directory, entry)
                if os.path.isdir(full_path):
                    # Recurse into subject subdirectories
                    scan_dir(full_path)
                elif entry.endswith(".yaml") or entry.endswith(".yml"):
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            rule = yaml.safe_load(f)
                        if rule and "name" in rule:
                            self.register_rule(full_path, rule)
                            count += 1
                    except Exception:
                        pass

        scan_dir(rules_dir)
        return count
