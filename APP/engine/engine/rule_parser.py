"""Rule parser - loads and validates YAML rule files"""
import yaml
from pathlib import Path


class RuleParser:
    """Parse and validate YAML rule files"""
    
    REQUIRED_FIELDS = ["name", "source", "list"]
    
    def load_rule(self, rule_path: str) -> dict:
        """Load a YAML rule file"""
        path = Path(rule_path)
        if not path.exists():
            raise FileNotFoundError(f"Rule file not found: {rule_path}")
        
        with open(path, 'r', encoding='utf-8') as f:
            rule = yaml.safe_load(f)
        
        return rule
    
    VALID_CLIENT_VALUES = {"auto", "mobile", "desktop", "browser", "crawl4ai"}
    VALID_EXTRACTION_STRATEGIES = {"llm", "cosine"}

    def validate(self, rule: dict) -> bool:
        """Validate required fields and client strategy in rule"""
        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in rule:
                raise ValueError(f"Missing required field: {field}")

        # Validate top-level client field (engine layer support)
        client = rule.get("client")
        if client is not None and client not in self.VALID_CLIENT_VALUES:
            raise ValueError(
                f"Invalid client strategy: '{client}'. "
                f"Must be one of: {', '.join(sorted(self.VALID_CLIENT_VALUES))}"
            )

        # Validate client strategy value in source
        source_client = rule.get("source", {}).get("client")
        if source_client is not None and source_client not in self.VALID_CLIENT_VALUES:
            raise ValueError(
                f"Invalid client strategy: '{source_client}'. "
                f"Must be one of: {', '.join(sorted(self.VALID_CLIENT_VALUES))}"
            )

        # Validate source.extraction if enabled
        extraction = rule.get("source", {}).get("extraction", {})
        if extraction.get("enabled"):
            if "prompt" not in extraction:
                raise ValueError("source.extraction.enabled is True but prompt is missing")
            strategy = extraction.get("strategy")
            if strategy is not None and strategy not in self.VALID_EXTRACTION_STRATEGIES:
                raise ValueError(
                    f"Invalid extraction strategy: '{strategy}'. "
                    f"Must be one of: {', '.join(sorted(self.VALID_EXTRACTION_STRATEGIES))}"
                )

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

    def get_extraction_config(self, rule: dict) -> dict | None:
        """Get extraction config from rule"""
        return rule.get("source", {}).get("extraction")
