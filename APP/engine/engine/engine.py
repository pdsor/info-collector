"""Info Collector Engine - Main Engine Class"""
import os
from pathlib import Path
from .rule_parser import RuleParser
from .dedup import Deduplicator
from .output import OutputManager
from .crawl_api import APICrawler
from .crawl_html import HTMLCrawler
from .crawl_browser import BrowserCrawler
from .state import StateManager
from .parsers import UA


class InfoCollectorEngine:
    """Main engine for info collection"""

    def __init__(self, dedup_db_path: str = "./dedup.db", state_dir: str = "engine/data"):
        """Initialize the engine

        Args:
            dedup_db_path: Path to SQLite deduplication database
            state_dir: Directory for state.json and output files
        """
        self.parser = RuleParser()
        self.dedup = Deduplicator(dedup_db_path)
        self.output_mgr = OutputManager(base_path=state_dir)
        self.state_mgr = StateManager(state_dir)
        self.api_crawler = APICrawler()
        self.html_crawler = HTMLCrawler()
        self.browser_crawler = BrowserCrawler()
    
    def load_rule(self, rule_path: str) -> dict:
        """Load rule from YAML file"""
        rule = self.parser.load_rule(rule_path)
        self.parser.validate(rule)
        return rule
    
    def crawl(self, rule: dict) -> list:
        """Execute crawling based on rule"""
        source_type = rule.get("source", {}).get("type", "html")
        client_mode = rule.get("source", {}).get("client", "desktop")

        # client: browser forces browser crawler regardless of source type
        if client_mode == "browser":
            return self._crawl_browser(rule)

        if source_type == "api":
            return self._crawl_api(rule)
        elif source_type == "browser":
            return self._crawl_browser(rule)
        else:
            return self._crawl_html(rule)
    
    def _crawl_api(self, rule: dict) -> list:
        """Crawl API source"""
        # Fetch all pages with pagination support
        raw_items = self.api_crawler.fetch_with_pagination(rule)

        # Extract fields
        field_defs = rule.get("list", {}).get("fields", [])
        items = []
        for raw_item in raw_items:
            item = self.api_crawler.extract_fields(raw_item, field_defs)
            items.append(item)

        return items
    
    def _crawl_html(self, rule: dict) -> list:
        """Crawl HTML source with client UA strategy support."""
        source = rule.get("source", {})
        url = source.get("url", "")
        request_headers = rule.get("request", {}).get("headers", {})
        client_mode = source.get("client", "desktop")  # auto, mobile, desktop, browser

        # Determine User-Agent based on client strategy
        user_agent = request_headers.get("User-Agent")  # YAML override takes precedence
        if not user_agent:
            if client_mode == "mobile":
                user_agent = UA.MOBILE
            elif client_mode == "desktop":
                user_agent = UA.DESKTOP
            # browser mode: HTMLCrawler handles its own UA (random from USER_AGENTS list)
            # auto mode: start with desktop, fallback below if needed

        # Build kwargs for fetch
        fetch_kwargs = {}
        if user_agent:
            fetch_kwargs["headers"] = {**request_headers, "User-Agent": user_agent}
        elif request_headers:
            fetch_kwargs["headers"] = request_headers

        # Fetch HTML — auto mode: try desktop first, fallback to mobile if too small
        MIN_RESPONSE_SIZE = 5000
        if client_mode == "auto":
            # Try desktop first
            desktop_kwargs = {**fetch_kwargs, "headers": {**(fetch_kwargs.get("headers", {})), "User-Agent": UA.DESKTOP}}
            html_content = self.html_crawler.fetch(url, **desktop_kwargs)
            if len(html_content) < MIN_RESPONSE_SIZE:
                # Fallback to mobile
                mobile_kwargs = {**fetch_kwargs, "headers": {**(fetch_kwargs.get("headers", {})), "User-Agent": UA.MOBILE}}
                html_content = self.html_crawler.fetch(url, **mobile_kwargs)
        else:
            html_content = self.html_crawler.fetch(url, **fetch_kwargs)
        
        # Parse items
        items_path = rule.get("list", {}).get("items_path", "")
        elements = self.html_crawler.parse_items(html_content, items_path)
        
        # Extract fields
        field_defs = rule.get("list", {}).get("fields", [])
        items = []
        
        for element in elements:
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
                elif field_type == "element_text":
                    item[field_name] = element.get("title", "") or element.get("text", "")
                elif field_type == "element_href":
                    item[field_name] = element.get("href", "")
                elif field_type == "xpath":
                    item[field_name] = self.html_crawler.extract_text(
                        element.get("html", ""), field_def.get("path", "")
                    )

            # Extract raw_id from URL for dedup if url_to_id_pattern is set
            if "url_to_id_pattern" in rule.get("dedup", {}):
                import re
                pattern = rule["dedup"]["url_to_id_pattern"]
                url = item.get("url", "")
                m = re.search(pattern, url)
                if m:
                    item["raw_id"] = m.group(1)

            items.append(item)

        return items

    def _crawl_browser(self, rule: dict) -> list:
        """Crawl browser-rendered page (JS-heavy sites)"""
        url = rule.get("source", {}).get("url", "")
        render_config = rule.get("render", {})

        # Fetch with browser
        html_content = self.browser_crawler.fetch(url, render_config)

        # Parse items
        items_path = rule.get("list", {}).get("items_path", "")
        elements = self.browser_crawler.parse_items(html_content, items_path)

        # Extract fields
        field_defs = rule.get("list", {}).get("fields", [])
        items = []

        for element in elements:
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
                elif field_type == "element_text":
                    item[field_name] = element.get("title", "") or element.get("text", "")
                elif field_type == "element_href":
                    item[field_name] = element.get("href", "")
                elif field_type == "xpath":
                    item[field_name] = self.browser_crawler.extract_text(
                        element.get("html", ""), field_def.get("path", "")
                    )

            # Extract raw_id from URL for dedup if url_to_id_pattern is set
            if "url_to_id_pattern" in rule.get("dedup", {}):
                import re
                pattern = rule["dedup"]["url_to_id_pattern"]
                url_val = item.get("url", "")
                m = re.search(pattern, url_val)
                if m:
                    item["raw_id"] = m.group(1)

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
    
    def run(self, rule_path: str, event_handler=None) -> dict:
        """Run full collection pipeline, record state, return result dict"""
        import time
        import traceback

        from engine.events import (
            event_start, event_status, event_error,
            event_complete, event_skip
        )

        if event_handler is None:
            event_handler = lambda line: print(line)

        rule_name = None
        execution_id = None
        start = time.time()

        try:
            # Load rule
            rule = self.load_rule(rule_path)
            rule_name = rule.get("name", rule_path)

            # Register rule in state (auto-update if already exists)
            self.state_mgr.register_rule(rule_path, rule)

            # Emit start event
            event_handler(event_start(rule_path))

            # Skip if disabled (check both top-level and source-level enabled flag)
            top_enabled = rule.get("enabled", True)
            source_enabled = rule.get("source", {}).get("enabled", True)
            if not top_enabled or not source_enabled:
                event_handler(event_skip(rule_path, "rule_disabled"))
                return {
                    "status": "skipped",
                    "reason": "rule_disabled",
                    "rule": rule_name,
                }

            # Record start
            execution_id = self.state_mgr.record_start(rule_name)

            # Emit running status
            event_handler(event_status(rule_path, "running", "开始采集..."))

            # Crawl
            items = self.crawl(rule)
            event_handler(event_status(rule_path, "running", f"采集完成，共 {len(items)} 条"))

            # Deduplicate
            items, dedup_filtered = self.deduplicate(items, rule)
            event_handler(event_status(rule_path, "running", f"去重后 {len(items)} 条新数据"))

            # Save output
            output_path = self.save_output(items, rule, dedup_filtered)

            # Record success
            self.state_mgr.record_finish(
                execution_id=execution_id,
                rule_name=rule_name,
                collected=len(items),
                dedup_filtered=dedup_filtered,
                output_path=output_path,
            )

            duration = time.time() - start
            event_handler(event_complete(rule_path, new_count=len(items), skip_count=dedup_filtered, duration=duration))

            return {
                "status": "success",
                "rule": rule_name,
                "collected": len(items),
                "dedup_filtered": dedup_filtered,
                "output_path": output_path,
                "duration": duration,
            }

        except Exception as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            duration = time.time() - start
            tb_detail = traceback.format_exc()

            # Record failure
            if execution_id and rule_name:
                self.state_mgr.record_finish(
                    execution_id=execution_id,
                    rule_name=rule_name,
                    collected=0,
                    dedup_filtered=0,
                    output_path="",
                    error=error_msg,
                )

            event_handler(event_error(rule_path, message=str(e), detail=tb_detail[-200:]))
            event_handler(event_complete(rule_path, new_count=0, skip_count=0, duration=duration))

            return {
                "status": "failed",
                "rule": rule_name,
                "error": error_msg,
                "duration": duration,
            }

    def run_all(self, rules_dir: str = "./rules", event_handler=None) -> list:
        """Run all enabled rules in the rules directory (recursively including
        subject sub-directories), return list of results.
        """
        import time

        if event_handler is None:
            event_handler = lambda line: print(line)

        from engine.events import event_start, event_skip, event_summary

        results = []
        if not os.path.isdir(rules_dir):
            return results

        start = time.time()
        total_new = 0
        total_skip = 0
        total_error = 0

        def scan(r_dir):
            """Recursively collect all YAML file paths."""
            paths = []
            for entry in sorted(os.listdir(r_dir)):
                full = os.path.join(r_dir, entry)
                if os.path.isdir(full):
                    paths.extend(scan(full))
                elif entry.endswith(".yaml") or entry.endswith(".yml"):
                    paths.append(full)
            return paths

        for fpath in scan(rules_dir):
            result = self.run(fpath, event_handler=event_handler)
            results.append(result)
            if result.get("status") == "success":
                total_new += result.get("collected", 0)
            elif result.get("status") == "skipped":
                total_skip += 1
            else:
                total_error += 1

        duration = time.time() - start
        event_handler(event_summary(
            total_rules=len(results),
            total_new=total_new,
            total_skip=total_skip,
            total_error=total_error,
            duration=duration,
        ))

        return results
