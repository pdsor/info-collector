"""Test StateManager functionality"""
import pytest
import tempfile
import os
import json


class TestStateManager:
    """Test state management functionality"""

    def setup_method(self):
        """Setup test state directory"""
        from engine.state import StateManager

        self.temp_dir = tempfile.mkdtemp()
        self.state_mgr = StateManager(state_dir=self.temp_dir)

    def teardown_method(self):
        """Cleanup"""
        import shutil
        if hasattr(self, 'state_mgr'):
            # Close any open connections
            pass
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_state_file_created(self):
        """Test that state.json is created after first mutation"""
        state_file = os.path.join(self.temp_dir, "state.json")
        # Empty init does NOT write file (lazy save)
        assert not os.path.exists(state_file)
        # First mutation triggers write
        self.state_mgr.register_rule("/path/test.yaml", {
            "name": "Test",
            "source": {"platform": "t", "type": "html"},
            "enabled": True,
        })
        assert os.path.exists(state_file)
        with open(state_file) as f:
            data = json.load(f)
        assert "rules" in data
        assert "executions" in data
        assert "errors" in data

    def test_register_rule(self):
        """Test registering a rule"""
        rule = {
            "name": "测试规则",
            "version": "1.0.0",
            "description": "测试描述",
            "source": {"platform": "test", "type": "html"},
            "enabled": True,
        }

        name = self.state_mgr.register_rule("/path/to/rule.yaml", rule)

        assert name == "测试规则"
        rules = self.state_mgr.get_rules()
        assert len(rules) == 1
        assert rules[0]["name"] == "测试规则"
        assert rules[0]["platform"] == "test"
        assert rules[0]["enabled"] is True

    def test_register_rule_updates_existing(self):
        """Test re-registering updates existing rule"""
        rule1 = {"name": "规则A", "source": {"platform": "p1", "type": "html"}, "enabled": True}
        rule2 = {"name": "规则A", "source": {"platform": "p1", "type": "html"}, "enabled": False}

        self.state_mgr.register_rule("/path/a.yaml", rule1)
        self.state_mgr.register_rule("/path/a.yaml", rule2)

        rules = self.state_mgr.get_rules()
        assert len(rules) == 1
        assert rules[0]["enabled"] is False

    def test_set_rule_enabled(self):
        """Test enabling/disabling a rule"""
        rule = {"name": "规则B", "source": {"platform": "p1", "type": "html"}, "enabled": True}
        self.state_mgr.register_rule("/path/b.yaml", rule)

        self.state_mgr.set_rule_enabled("规则B", False)
        assert self.state_mgr.get_rule("规则B")["enabled"] is False

        self.state_mgr.set_rule_enabled("规则B", True)
        assert self.state_mgr.get_rule("规则B")["enabled"] is True

    def test_record_start_and_finish(self):
        """Test recording task start and finish"""
        rule = {"name": "规则C", "source": {"platform": "p1", "type": "html"}, "enabled": True}
        self.state_mgr.register_rule("/path/c.yaml", rule)

        exec_id = self.state_mgr.record_start("规则C")
        assert exec_id.startswith("exec_")

        self.state_mgr.record_finish(exec_id, "规则C", collected=10, dedup_filtered=2, output_path="/out/c.json")

        executions = self.state_mgr.get_executions(limit=5)
        assert len(executions) == 1
        assert executions[0]["status"] == "success"
        assert executions[0]["collected"] == 10
        assert executions[0]["dedup_filtered"] == 2

    def test_record_failure(self):
        """Test recording task failure"""
        rule = {"name": "规则D", "source": {"platform": "p1", "type": "html"}, "enabled": True}
        self.state_mgr.register_rule("/path/d.yaml", rule)

        exec_id = self.state_mgr.record_start("规则D")
        self.state_mgr.record_finish(exec_id, "规则D", 0, 0, "", error="NetworkError: timeout")

        executions = self.state_mgr.get_executions()
        assert executions[0]["status"] == "failed"
        assert executions[0]["error"] == "NetworkError: timeout"

        errors = self.state_mgr.get_errors()
        assert len(errors) == 1
        assert errors[0]["error"] == "NetworkError: timeout"

    def test_global_stats_updated(self):
        """Test global stats are updated after runs"""
        rule = {"name": "规则E", "source": {"platform": "p1", "type": "html"}, "enabled": True}
        self.state_mgr.register_rule("/path/e.yaml", rule)

        exec_id = self.state_mgr.record_start("规则E")
        self.state_mgr.record_finish(exec_id, "规则E", collected=5, dedup_filtered=1, output_path="/out/e.json")

        stats = self.state_mgr.get_stats()
        assert stats["total_runs"] == 1
        assert stats["total_collected"] == 5

        # Record a failure
        exec_id2 = self.state_mgr.record_start("规则E")
        self.state_mgr.record_finish(exec_id2, "规则E", 0, 0, "", error="Error")

        stats2 = self.state_mgr.get_stats()
        assert stats2["total_runs"] == 2
        assert stats2["total_failed"] == 1

    def test_scan_and_register_rules(self):
        """Test scanning rules directory"""
        rules_dir = os.path.join(self.temp_dir, "rules")
        os.makedirs(rules_dir)

        # Write test rule files
        import yaml
        for name in ["rule_a.yaml", "rule_b.yaml"]:
            with open(os.path.join(rules_dir, name), "w") as f:
                yaml.dump({
                    "name": name.replace(".yaml", ""),
                    "source": {"platform": "test", "type": "html"}
                }, f)

        count = self.state_mgr.scan_and_register_rules(rules_dir)
        assert count == 2
        assert len(self.state_mgr.get_rules()) == 2

    def test_get_rules_returns_list(self):
        """Test get_rules returns a list"""
        rule = {"name": "规则F", "source": {"platform": "p1", "type": "html"}, "enabled": True}
        self.state_mgr.register_rule("/path/f.yaml", rule)

        rules = self.state_mgr.get_rules()
        assert isinstance(rules, list)
        assert len(rules) == 1
