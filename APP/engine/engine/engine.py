"""Info Collector Engine - Main Engine Class"""
from pathlib import Path
from .rule_parser import RuleParser
from .dedup import Deduplicator
from .output import OutputManager
from .crawl_api import APICrawler
from .crawl_html import HTMLCrawler


class InfoCollectorEngine:
    """Main engine for info collection"""
    
    def __init__(self, dedup_db_path: str = "./dedup.db"):
        """Initialize the engine"""
        self.parser = RuleParser()
        self.dedup = Deduplicator(dedup_db_path)
        self.output_mgr = OutputManager()
        self.api_crawler = APICrawler()
        self.html_crawler = HTMLCrawler()
    
    def load_rule(self, rule_path: str) -> dict:
        """Load rule from YAML file"""
        rule = self.parser.load_rule(rule_path)
        self.parser.validate(rule)
        return rule
    
    def crawl(self, rule: dict) -> list:
        """Execute crawling based on rule"""
        source_type = rule.get("source", {}).get("type", "html")
        
        if source_type == "api":
            return self._crawl_api(rule)
        else:
            return self._crawl_html(rule)
    
    def _crawl_api(self, rule: dict) -> list:
        """Crawl API source"""
        # Build request parameters
        params = self.api_crawler.build_request_params(rule)
        
        # Execute request
        response_data = self.api_crawler.fetch(
            params["url"],
            method=params["method"],
            headers=params.get("headers", {}),
            data=params.get("data", {})
        )
        
        # Parse items
        items_path = rule.get("list", {}).get("items_path", "")
        raw_items = self.api_crawler.parse_items(response_data, items_path)
        
        # Extract fields
        field_defs = rule.get("list", {}).get("fields", [])
        items = []
        for raw_item in raw_items:
            item = self.api_crawler.extract_fields(raw_item, field_defs)
            items.append(item)
        
        return items
    
    def _crawl_html(self, rule: dict) -> list:
        """Crawl HTML source"""
        url = rule.get("source", {}).get("url", "")
        
        # Fetch HTML
        html_content = self.html_crawler.fetch(url)
        
        # Parse items
        items_path = rule.get("list", {}).get("items_path", "")
        elements = self.html_crawler.parse_items(html_content, items_path)
        
        # Extract fields
        field_defs = rule.get("list", {}).get("fields", [])
        items = []
        
        for element in elements:
            # For HTML elements, we need to handle extraction differently
            item = {}
            for field_def in field_defs:
                field_name = field_def["name"]
                field_type = field_def["type"]
                
                if field_type == "constant":
                    item[field_name] = field_def["value"]
                elif field_type == "attr":
                    item[field_name] = element.get(field_def.get("attr", "href"), "")
                elif field_type == "computed":
                    item[field_name] = field_def.get("value")
            
            items.append(item)
        
        return items
    
    def deduplicate(self, items: list, rule: dict) -> tuple:
        """Deduplicate items, returns (filtered_items, count_filtered)"""
        if not rule.get("dedup", {}).get("incremental", False):
            return items, 0
        
        requirement = rule.get("name", "default")
        platform = rule.get("source", {}).get("platform", "unknown")
        
        # Get total count before dedup
        total_count = len(items)
        
        # Filter items
        filtered_items = self.dedup.filter_items(requirement, platform, items)
        
        # Add new items to dedup
        for item in filtered_items:
            raw_id = item.get("raw_id", "")
            url = item.get("url", "")
            self.dedup.add(requirement, platform, raw_id, url)
        
        filtered_count = total_count - len(filtered_items)
        return filtered_items, filtered_count
    
    def save_output(self, items: list, rule: dict, dedup_filtered: int = 0) -> str:
        """Save items to JSON output"""
        return self.output_mgr.save(items, rule, dedup_filtered)
    
    def run(self, rule_path: str) -> dict:
        """Run full collection pipeline"""
        # Load rule
        rule = self.load_rule(rule_path)
        
        # Crawl
        items = self.crawl(rule)
        
        # Deduplicate
        items, dedup_filtered = self.deduplicate(items, rule)
        
        # Save output
        output_path = self.save_output(items, rule, dedup_filtered)
        
        return {
            "status": "success",
            "rule": rule.get("name"),
            "collected": len(items),
            "dedup_filtered": dedup_filtered,
            "output_path": output_path
        }
