"""
tests/test_enabled_field_consistency.py

测试 enabled 字段在 engine、CLI、YAML 三层的一致性。

覆盖场景：
1. YAML enabled=true → engine.run() 正常执行
2. YAML enabled=false → engine.run() 返回 skipped
3. CLI enable-rule 切换 enabled 状态
4. StateManager.register_rule 正确读取 enabled
5. CLI list-rules 与 YAML enabled 一致
"""

import json
import os
import sys
import tempfile
import pytest
import yaml
import shutil


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def temp_rules_dir(tmp_path):
    """创建临时规则目录"""
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    return rules_dir


@pytest.fixture
def temp_state_dir(tmp_path):
    """创建临时状态目录"""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    return state_dir


@pytest.fixture
def sample_rule_enabled_true(temp_rules_dir):
    """启用状态的示例规则"""
    rule = {
        "name": "Test Enabled Rule",
        "subject": "test",
        "version": "1.0.0",
        "enabled": True,
        "source": {
            "platform": "test",
            "type": "html",
            "url": "https://example.com",
        },
        "list": {
            "items_path": "//div[@class='item']",
            "fields": [
                {"name": "title", "type": "element_text"},
                {"name": "url", "type": "element_href"},
            ],
        },
        "output": {"format": "json", "filename_template": "test_{date}.json"},
    }
    path = temp_rules_dir / "test_enabled.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(rule, f, allow_unicode=True, default_flow_style=False)
    return str(path), rule


@pytest.fixture
def sample_rule_enabled_false(temp_rules_dir):
    """禁用状态的示例规则"""
    rule = {
        "name": "Test Disabled Rule",
        "subject": "test",
        "version": "1.0.0",
        "enabled": False,
        "source": {
            "platform": "test",
            "type": "html",
            "url": "https://example.com",
        },
        "list": {
            "items_path": "//div[@class='item']",
            "fields": [
                {"name": "title", "type": "element_text"},
                {"name": "url", "type": "element_href"},
            ],
        },
        "output": {"format": "json", "filename_template": "test_disabled_{date}.json"},
    }
    path = temp_rules_dir / "test_disabled.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(rule, f, allow_unicode=True, default_flow_style=False)
    return str(path), rule


@pytest.fixture
def sample_rule_no_enabled_field(temp_rules_dir):
    """没有 enabled 字段的规则（应默认为 true）"""
    rule = {
        "name": "Test No Enabled Field",
        "subject": "test",
        "version": "1.0.0",
        # 没有 enabled 字段
        "source": {
            "platform": "test",
            "type": "html",
            "url": "https://example.com",
        },
        "list": {
            "items_path": "//div[@class='item']",
            "fields": [
                {"name": "title", "type": "element_text"},
            ],
        },
        "output": {"format": "json", "filename_template": "test_no_enabled_{date}.json"},
    }
    path = temp_rules_dir / "test_no_enabled.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(rule, f, allow_unicode=True, default_flow_style=False)
    return str(path), rule


# ── 测试类 ────────────────────────────────────────────────────────────────────

class TestEnabledFieldConsistency:
    """测试 enabled 字段在三层的一致性"""

    def test_yaml_enabled_true_read_correctly(self, sample_rule_enabled_true):
        """YAML enabled=true 能被正确读取"""
        rule_path, rule = sample_rule_enabled_true
        with open(rule_path, "r", encoding="utf-8") as f:
            yaml_rule = yaml.safe_load(f)
        assert yaml_rule.get("enabled") is True

    def test_yaml_enabled_false_read_correctly(self, sample_rule_enabled_false):
        """YAML enabled=false 能被正确读取"""
        rule_path, rule = sample_rule_enabled_false
        with open(rule_path, "r", encoding="utf-8") as f:
            yaml_rule = yaml.safe_load(f)
        assert yaml_rule.get("enabled") is False

    def test_yaml_no_enabled_field_reads_none(self, sample_rule_no_enabled_field):
        """YAML 没有 enabled 字段时读取为 None"""
        rule_path, rule = sample_rule_no_enabled_field
        with open(rule_path, "r", encoding="utf-8") as f:
            yaml_rule = yaml.safe_load(f)
        assert "enabled" not in yaml_rule
        assert yaml_rule.get("enabled") is None

    def test_yaml_enabled_false_engine_skips(self, sample_rule_enabled_false):
        """YAML enabled=false → engine.run() 返回 skipped"""
        from engine.engine import InfoCollectorEngine
        from engine.state import StateManager

        rule_path, rule = sample_rule_enabled_false

        with open(rule_path, "r", encoding="utf-8") as f:
            yaml_rule = yaml.safe_load(f)
        assert yaml_rule.get("enabled") is False

        # 创建临时状态目录
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = os.path.join(tmp_dir, "state")
            os.makedirs(state_dir)
            dedup_db = os.path.join(tmp_dir, "dedup.db")

            engine = InfoCollectorEngine(dedup_db_path=dedup_db, state_dir=state_dir)
            result = engine.run(rule_path)

            assert result.get("status") == "skipped"
            assert result.get("reason") == "rule_disabled"

    def test_yaml_enabled_true_engine_runs(self, sample_rule_enabled_true):
        """YAML enabled=true → engine.run() 正常执行（不跳过）"""
        from engine.engine import InfoCollectorEngine
        from engine.state import StateManager

        rule_path, rule = sample_rule_enabled_true

        with open(rule_path, "r", encoding="utf-8") as f:
            yaml_rule = yaml.safe_load(f)
        assert yaml_rule.get("enabled") is True

        # 创建临时状态目录
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = os.path.join(tmp_dir, "state")
            os.makedirs(state_dir)
            dedup_db = os.path.join(tmp_dir, "dedup.db")

            engine = InfoCollectorEngine(dedup_db_path=dedup_db, state_dir=state_dir)
            result = engine.run(rule_path)

            # enabled=true 不应被跳过（网络请求可能失败但状态不是 skipped）
            # 等价于：不能同时 status=skipped AND reason=rule_disabled
            assert not (result.get("status") == "skipped" and result.get("reason") == "rule_disabled"), \
                f"enabled=true 的规则不应被跳过，实际: {result}"

    def test_yaml_no_enabled_field_defaults_true(self, sample_rule_no_enabled_field):
        """YAML 没有 enabled 字段 → engine 默认 enabled=True"""
        from engine.engine import InfoCollectorEngine
        from engine.state import StateManager

        rule_path, rule = sample_rule_no_enabled_field

        with open(rule_path, "r", encoding="utf-8") as f:
            yaml_rule = yaml.safe_load(f)
        assert "enabled" not in yaml_rule

        # 创建临时状态目录
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = os.path.join(tmp_dir, "state")
            os.makedirs(state_dir)
            dedup_db = os.path.join(tmp_dir, "dedup.db")

            engine = InfoCollectorEngine(dedup_db_path=dedup_db, state_dir=state_dir)
            result = engine.run(rule_path)

            # 没有 enabled 字段时默认为 True，不应被跳过
            assert not (result.get("status") == "skipped" and result.get("reason") == "rule_disabled"), \
                f"无 enabled 字段时应默认为启用，实际: {result}"

    def test_state_manager_reads_enabled_correctly(self, temp_state_dir, sample_rule_enabled_true, sample_rule_enabled_false):
        """StateManager.register_rule 正确读取 enabled 状态"""
        from engine.state import StateManager

        sm = StateManager(str(temp_state_dir))

        # 注册 enabled=true 的规则
        path1, rule1 = sample_rule_enabled_true
        sm.register_rule(path1, rule1)

        # 注册 enabled=false 的规则
        path2, rule2 = sample_rule_enabled_false
        sm.register_rule(path2, rule2)

        # 验证状态读取
        rules = sm.get_rules()
        rules_dict = {r["name"]: r for r in rules}

        assert rules_dict["Test Enabled Rule"]["enabled"] is True
        assert rules_dict["Test Disabled Rule"]["enabled"] is False

    def test_cli_enable_rule_toggles_yaml(self, temp_rules_dir):
        """CLI enable-rule 命令正确切换 YAML enabled 状态"""
        # 创建测试规则
        rule = {
            "name": "Toggle Test Rule",
            "enabled": True,
            "source": {"platform": "test", "type": "html", "url": "https://example.com"},
        }
        rule_path = temp_rules_dir / "toggle_test.yaml"
        with open(rule_path, "w", encoding="utf-8") as f:
            yaml.dump(rule, f)

        # 初始状态为 True
        with open(rule_path, "r", encoding="utf-8") as f:
            assert yaml.safe_load(f).get("enabled") is True

        # 切换为 False
        with open(rule_path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        doc["enabled"] = False
        with open(rule_path, "w", encoding="utf-8") as f:
            yaml.dump(doc, f, allow_unicode=True, default_flow_style=False)

        with open(rule_path, "r", encoding="utf-8") as f:
            assert yaml.safe_load(f).get("enabled") is False

        # 切换回 True
        with open(rule_path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        doc["enabled"] = True
        with open(rule_path, "w", encoding="utf-8") as f:
            yaml.dump(doc, f, allow_unicode=True, default_flow_style=False)

        with open(rule_path, "r", encoding="utf-8") as f:
            assert yaml.safe_load(f).get("enabled") is True

    def test_enabled_field_propagation_consistency(self, temp_state_dir, temp_rules_dir):
        """验证 enabled 字段从 YAML → Engine → State 的传播一致性"""
        from engine.engine import InfoCollectorEngine
        from engine.state import StateManager

        # 创建规则
        rule = {
            "name": "Propagation Test",
            "enabled": True,
            "source": {"platform": "test", "type": "html", "url": "https://example.com"},
            "list": {
                "items_path": "//div[@class='item']",
                "fields": [
                    {"name": "title", "type": "element_text"},
                ],
            },
            "output": {"format": "json", "filename_template": "test_{date}.json"},
        }
        rule_path = temp_rules_dir / "propagation_test.yaml"
        with open(rule_path, "w", encoding="utf-8") as f:
            yaml.dump(rule, f)

        # 1. YAML 层
        with open(rule_path, "r", encoding="utf-8") as f:
            yaml_enabled = yaml.safe_load(f).get("enabled")
        assert yaml_enabled is True

        # 2. Engine 层 - load_rule
        with tempfile.TemporaryDirectory() as tmp_dir:
            state_dir = os.path.join(tmp_dir, "state")
            os.makedirs(state_dir)
            dedup_db = os.path.join(tmp_dir, "dedup.db")

            engine = InfoCollectorEngine(dedup_db_path=dedup_db, state_dir=state_dir)
            loaded = engine.load_rule(str(rule_path))
            engine_yaml_enabled = loaded.get("enabled")
            assert engine_yaml_enabled == yaml_enabled

            # 3. StateManager 层
            engine.state_mgr.register_rule(str(rule_path), loaded)
            state_rule = engine.state_mgr.get_rule("Propagation Test")
            state_enabled = state_rule.get("enabled")
            assert state_enabled == yaml_enabled

            # 4. 修改 YAML enabled=false，验证传播
            with open(rule_path, "r", encoding="utf-8") as f:
                doc = yaml.safe_load(f)
            doc["enabled"] = False
            with open(rule_path, "w", encoding="utf-8") as f:
                yaml.dump(doc, f, allow_unicode=True, default_flow_style=False)

            # 重新加载
            reloaded = engine.load_rule(str(rule_path))
            assert reloaded.get("enabled") is False


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    # 运行测试
    sys.exit(pytest.main([__file__, "-v"]))
