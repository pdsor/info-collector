"""Test YAML rule parsing"""
import pytest
import yaml
from pathlib import Path


class TestRuleParser:
    """Test rule parser functionality"""

    def test_load_valid_rule(self):
        """Test loading a valid rule file"""
        from engine.rule_parser import RuleParser
        
        parser = RuleParser()
        rule = parser.load_rule("rules/cninfo_data_value_search.yaml")
        
        assert rule is not None
        assert "name" in rule
        assert "source" in rule
        assert rule["source"]["platform"] == "cninfo"

    def test_load_html_rule(self):
        """Test loading HTML type rule"""
        from engine.rule_parser import RuleParser
        
        parser = RuleParser()
        rule = parser.load_rule("rules/tmtpost_data_articles.yaml")
        
        assert rule is not None
        assert rule["source"]["type"] == "html"

    def test_validate_required_fields(self):
        """Test rule validation for required fields"""
        from engine.rule_parser import RuleParser
        
        parser = RuleParser()
        
        # Missing required fields should raise error
        invalid_rule = {"name": "test"}  # missing source, list
        with pytest.raises(ValueError):
            parser.validate(invalid_rule)

    def test_parse_items_path_api(self):
        """Test JSONPath parsing for API sources"""
        from engine.rule_parser import RuleParser
        
        parser = RuleParser()
        rule = parser.load_rule("rules/cninfo_data_value_search.yaml")
        
        items_path = rule["list"]["items_path"]
        assert items_path == "$.announcements[*]"

    def test_parse_items_path_html(self):
        """Test XPath parsing for HTML sources"""
        from engine.rule_parser import RuleParser
        
        parser = RuleParser()
        rule = parser.load_rule("rules/tmtpost_data_articles.yaml")
        
        items_path = rule["list"]["items_path"]
        assert "//a" in items_path

    def test_parse_field_definitions(self):
        """Test parsing field definitions"""
        from engine.rule_parser import RuleParser
        
        parser = RuleParser()
        rule = parser.load_rule("rules/cninfo_data_value_search.yaml")
        
        fields = rule["list"]["fields"]
        assert len(fields) > 0
        
        # Check first field structure
        title_field = next(f for f in fields if f["name"] == "title")
        assert title_field["type"] == "field"
        assert "path" in title_field
