"""YAML 规则解析测试。"""
import pytest
import yaml
from pathlib import Path


NDA_RULE_PATH = "rules/数据要素/nda_gov_data_element_cases.yaml"


class TestRuleParser:
    """测试规则解析功能。"""

    def test_load_valid_rule(self):
        """应能加载当前唯一 NDA 规则文件。"""
        from engine.rule_parser import RuleParser
        
        parser = RuleParser()
        rule = parser.load_rule(NDA_RULE_PATH)
        
        assert rule is not None
        assert "name" in rule
        assert "source" in rule
        assert rule["source"]["platform"] == "nda_gov"

    def test_load_html_rule(self):
        """NDA 规则应声明 HTML 源。"""
        from engine.rule_parser import RuleParser
        
        parser = RuleParser()
        rule = parser.load_rule(NDA_RULE_PATH)
        
        assert rule is not None
        assert rule["source"]["type"] == "html"

    def test_validate_required_fields(self):
        """缺失必填字段时应校验失败。"""
        from engine.rule_parser import RuleParser
        
        parser = RuleParser()
        
        invalid_rule = {"name": "test"}
        with pytest.raises(ValueError):
            parser.validate(invalid_rule)

    def test_parse_items_path(self):
        """应解析当前 NDA 规则的列表路径。"""
        from engine.rule_parser import RuleParser
        
        parser = RuleParser()
        rule = parser.load_rule(NDA_RULE_PATH)
        
        items_path = rule["list"]["items_path"]
        assert items_path == "xpath://ul/li[.//span]"

    def test_parse_discovery_items_path(self):
        """归档发现配置应复用 NDA 列表路径。"""
        from engine.rule_parser import RuleParser

        parser = RuleParser()
        rule = parser.load_rule(NDA_RULE_PATH)

        items_path = rule["discovery"]["list"]["items_path"]
        assert items_path == "xpath://ul/li[.//span]"

    def test_parse_field_definitions(self):
        """应解析当前规则的 v2 提取字段。"""
        from engine.rule_parser import RuleParser
        
        parser = RuleParser()
        rule = parser.load_rule(NDA_RULE_PATH)
        
        fields = rule["extract"]
        assert {"title", "url", "publish_time"} <= set(fields)
        
        title_field = fields["title"]
        assert title_field["selector"] == "a"
        assert title_field["type"] == "text"
        assert rule["dedup"]["id_template"] == "nda_gov_{article_id}"
        assert "url_to_id_pattern" in rule["dedup"]
