"""Rule parser - loads and validates YAML rule files"""
import yaml
from pathlib import Path


class RuleParser:
    """Parse and validate YAML rule files"""
    
    REQUIRED_FIELDS = ["name", "source", "list"]
    
    def load_rule(self, rule_path: str) -> dict:
        """Load a YAML rule file"""
        # PSEUDOCODE: Read YAML file
        path = Path(rule_path)
        if not path.exists():
            raise FileNotFoundError(f"Rule file not found: {rule_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            rule = yaml.safe_load(f)
        
        return rule
    
    def validate(self, rule: dict) -> bool:
        """Validate required fields in rule"""
        # PSEUDOCODE: Check all required fields exist
        for field in self.REQUIRED_FIELDS:
            if field not in rule:
                raise ValueError(f"Missing required field: {field}")
        
        return True
    
    def get_source_type(self, rule: dict) -> str:
        """Get source type (api or html)"""
        return rule.get("source", {}).get("type", "html")
    
    def get_items_path(self, rule: dict) -> str:
        """Get items extraction path"""
        return rule.get("list", {}).get("items_path", "")
    
    def get_field_definitions(self, rule: dict) -> list:
        """Get field definitions from rule"""
        return rule.get("list", {}).get("fields", [])
