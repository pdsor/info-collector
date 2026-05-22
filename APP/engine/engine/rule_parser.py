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
    
    VALID_CLIENT_VALUES = {"auto", "mobile", "desktop", "browser", "playwright"}
    VALID_RULE_STATUSES = {"DRAFT", "TESTING", "PRODUCTION", "DEPRECATED"}
    BLOCKED_AI_CONFIG_KEYS = {"agent", "llm", "vision_model", "cloud_ocr", "api_key", "crawl4ai"}

    def _is_rule_v2(self, rule: dict) -> bool:
        """判断是否为 NG v2 规则。"""
        return "rule_id" in rule or "source_id" in rule or "extract" in rule

    def _validate_client(self, client: str | None):
        """校验客户端策略，拒绝 AI 相关客户端。"""
        if client is None:
            return
        if client == "crawl4ai":
            raise ValueError("Crawl4AI 已从 v2.2 架构移除，禁止使用 client=crawl4ai")
        if client not in self.VALID_CLIENT_VALUES:
            raise ValueError(
                f"Invalid client strategy: '{client}'. "
                f"Must be one of: {', '.join(sorted(self.VALID_CLIENT_VALUES))}"
            )

    def _validate_no_ai_extraction(self, rule: dict):
        """拒绝所有系统内 AI/LLM 提取配置。"""
        extraction = rule.get("source", {}).get("extraction")
        if extraction:
            raise ValueError("source.extraction 属于 AI/LLM 提取配置，v2.2 禁止系统内 AI 调用")

    def _validate_image_extraction(self, rule: dict):
        """校验图片 OCR 配置只能使用本地已注册插件。"""
        config = rule.get("image_extraction")
        if not config:
            return
        self._validate_local_ocr_config(config, "image_extraction")

    def _validate_local_ocr_config(self, config: dict, path: str):
        """校验 OCR 配置只能使用本地已注册插件。"""
        if not isinstance(config, dict):
            raise ValueError(f"{path} must be an object")
        output_mode = config.get("output_mode", "append")
        if output_mode not in {"append", "ocr_rows_only"}:
            raise ValueError(f"{path}.output_mode must be append or ocr_rows_only")
        ocr = config.get("ocr") or {}
        found = self.BLOCKED_AI_CONFIG_KEYS.intersection(set(ocr.keys()) | set(config.keys()))
        if found:
            raise ValueError(f"{path} 禁止 AI、Agent 或云 OCR 配置: {', '.join(sorted(found))}")

        from .ocr_plugins import list_ocr_plugins, resolve_ocr_plugin_name

        plugin_name = resolve_ocr_plugin_name(ocr)
        if plugin_name not in list_ocr_plugins():
            raise ValueError(f"{path}.ocr.plugin 未注册: {plugin_name}")

    def _validate_no_forbidden_runtime_config(self, config, path: str):
        """递归拒绝 AI、Agent、云 OCR 和 crawl4ai 配置。"""
        if isinstance(config, dict):
            for key, value in config.items():
                current_path = f"{path}.{key}"
                if key in self.BLOCKED_AI_CONFIG_KEYS:
                    raise ValueError(f"{current_path} 禁止 AI、Agent、云 OCR 或 crawl4ai 配置")
                if isinstance(value, str) and value == "crawl4ai":
                    raise ValueError(f"{current_path} 禁止 crawl4ai 配置")
                self._validate_no_forbidden_runtime_config(value, current_path)
        elif isinstance(config, list):
            for index, item in enumerate(config):
                self._validate_no_forbidden_runtime_config(item, f"{path}[{index}]")

    def _validate_optional_object_block(self, rule: dict, block_name: str) -> dict | None:
        """校验可选配置块必须是对象。"""
        config = rule.get(block_name)
        if config is None:
            return None
        if not isinstance(config, dict):
            raise ValueError(f"{block_name} must be an object")
        return config

    def _validate_archive_blocks(self, rule: dict):
        """校验页面归档相关 DSL 配置块。"""
        discovery = self._validate_optional_object_block(rule, "discovery")
        if discovery is not None:
            self._validate_no_forbidden_runtime_config(discovery, "discovery")

        archive = self._validate_optional_object_block(rule, "archive")
        if archive is not None:
            image_ocr = archive.get("image_ocr")
            archive_without_ocr = {key: value for key, value in archive.items() if key != "image_ocr"}
            self._validate_no_forbidden_runtime_config(archive_without_ocr, "archive")
            if image_ocr is not None:
                self._validate_local_ocr_config(image_ocr, "archive.image_ocr")

        structuring = self._validate_optional_object_block(rule, "structuring")
        if structuring is not None:
            self._validate_no_forbidden_runtime_config(structuring, "structuring")

    def _validate_rule_v2(self, rule: dict) -> bool:
        """校验 NG v2 规则最小结构。"""
        for field in ["rule_id", "source_id", "version", "extract"]:
            if field not in rule:
                raise ValueError(f"Missing required field: {field}")

        if not isinstance(rule.get("extract"), dict) or not rule["extract"]:
            raise ValueError("Rule v2 requires non-empty extract field definitions")

        status = rule.get("status")
        if status is not None and status not in self.VALID_RULE_STATUSES:
            raise ValueError(
                f"Invalid rule status: '{status}'. "
                f"Must be one of: {', '.join(sorted(self.VALID_RULE_STATUSES))}"
            )

        self._validate_client(rule.get("client"))
        self._validate_client(rule.get("source", {}).get("client"))
        self._validate_no_ai_extraction(rule)
        self._validate_image_extraction(rule)
        self._validate_archive_blocks(rule)

        for field_name, field_def in rule["extract"].items():
            if not isinstance(field_def, dict):
                raise ValueError(f"extract.{field_name} must be an object")
            if "selector" not in field_def:
                raise ValueError(f"extract.{field_name} missing selector")

        return True

    def validate(self, rule: dict) -> bool:
        """Validate required fields and client strategy in rule"""
        if self._is_rule_v2(rule):
            return self._validate_rule_v2(rule)

        # Check required fields
        for field in self.REQUIRED_FIELDS:
            if field not in rule:
                raise ValueError(f"Missing required field: {field}")

        # Validate top-level client field (engine layer support)
        self._validate_client(rule.get("client"))

        # Validate client strategy value in source
        self._validate_client(rule.get("source", {}).get("client"))
        self._validate_no_ai_extraction(rule)
        self._validate_image_extraction(rule)

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
