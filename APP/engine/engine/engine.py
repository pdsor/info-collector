"""Info Collector Engine - Main Engine Class"""
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse
import base64
import parsel
from .rule_parser import RuleParser


def _transform_url(url: str, transform: str) -> str:
    """Transform extracted URLs based on rule-specific patterns."""
    if transform == "sogou_link":
        # sogou weixin intermediate link: /link?url=<base64_url>&type=2&query=...&token=...
        # Extract the 'url' param, URL-decode, then base64-decode to get real article URL
        import html
        try:
            # Unescape HTML entities (&amp; -> &, etc.)
            url = html.unescape(url)
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if "url" in params:
                encoded_url = params["url"][0]
                # URL decode first (the outer encoding)
                decoded = unquote(encoded_url)
                # Sogou uses '.' as extra padding character, strip it
                decoded = decoded.rstrip('.')
                # Add proper base64 padding if needed
                padding_needed = 4 - (len(decoded) % 4)
                if padding_needed != 4:
                    decoded = decoded + "=" * padding_needed
                # Base64 decode to get the real URL
                real_url_bytes = base64.b64decode(decoded)
                real_url = real_url_bytes.decode("utf-8")
                return real_url
        except Exception:
            pass
        return url  # fallback: return original
    return url


from .dedup import Deduplicator
from .output import OutputManager
from .crawl_api import APICrawler
from .crawl_html import HTMLCrawler
from .crawl_browser import BrowserCrawler
from .governance import GovernancePipeline
from .image_extraction import ImageExtractionRunner
from .state import StateManager
from .parsers import UA
from .archive import build_archive_page
from .archive_store import ArchiveStore


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
        self.browser_crawler = BrowserCrawler(client="playwright")
        self.last_ocr_summary = {}

    def close(self):
        """Close all engine resources to prevent leaks"""
        if self.dedup:
            self.dedup.close()
        if self.browser_crawler:
            self.browser_crawler.close()

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
        if "extract" in rule:
            items = self._extract_rule_v2_items(elements, rule)
            return self._append_image_extraction_items(html_content, items, rule, url)

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
                    href = element.get("href", "")
                    transform = field_def.get("transform")
                    if transform:
                        href = _transform_url(href, transform)
                    item[field_name] = href
                    # resolve_url requires Playwright — only valid in _crawl_browser path
                    # In _crawl_html, keep original URL (will be resolved if rule uses browser client)
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

        return self._append_image_extraction_items(html_content, items, rule, url)

    def _append_image_extraction_items(self, html_content: str, items: list, rule: dict, page_url: str) -> list:
        """在标准网页采集结果后按配置处理图片 OCR 记录。"""
        runner = ImageExtractionRunner(rule)
        ocr_items = runner.extract(html_content, items, page_url=page_url)
        self.last_ocr_summary = runner.summary if runner.summary.get("enabled") else {}
        output_mode = (rule.get("image_extraction") or {}).get("output_mode", "append")
        if output_mode == "ocr_rows_only":
            return ocr_items
        if ocr_items:
            return items + ocr_items
        return items

    def _extract_rule_v2_items(self, elements: list, rule: dict) -> list:
        """按 NG v2 extract 字段从元素片段中提取结构化数据。"""
        extract_defs = rule.get("extract") or {}
        items = []
        for element in elements:
            html = element.get("html", "") if isinstance(element, dict) else str(element)
            selector = parsel.Selector(text=html)
            item = {}
            for field_name, field_def in extract_defs.items():
                field_type = field_def.get("type", "text")
                css = field_def.get("selector", "")
                selected = selector.css(css) if css else selector
                if field_type == "attribute":
                    attr = field_def.get("attribute", "")
                    item[field_name] = selected.attrib.get(attr, "") if selected else ""
                elif field_type == "html":
                    item[field_name] = selected.get(default="") if selected else ""
                elif field_type == "list":
                    item[field_name] = [
                        "".join(match.xpath("string()").getall()).strip()
                        for match in selected
                    ]
                else:
                    item[field_name] = (
                        "".join(selected.xpath("string()").getall()).strip()
                        if selected else ""
                    )
            items.append(item)
        return items

    def _get_browser_client(self, rule: dict) -> str:
        """Determine which browser client to use for a rule.
        
            1. rule["client"]
            2. rule["source"]["client"]
            3. Default: "browser" (Playwright)

        Returns:
            "playwright" or "browser"
        """
        return rule.get("client") or rule.get("source", {}).get("client") or "browser"
    
    def _crawl_browser(self, rule: dict) -> list:
        """Crawl browser-rendered page (JS-heavy sites)"""
        url = rule.get("source", {}).get("url", "")
        render_config = rule.get("render", {})
        
        # Switch client if needed (dual routing)
        client = self._get_browser_client(rule)
        if self.browser_crawler.client != client:
            self.browser_crawler.switch_client(client)
        
        # Fetch with browser
        html_content = self.browser_crawler.fetch(url, render_config)

        # Parse items
        items_path = rule.get("list", {}).get("items_path", "")
        elements = self.browser_crawler.parse_items(html_content, items_path)

        # Extract fields
        if "extract" in rule:
            items = self._extract_rule_v2_items(elements, rule)
            return self._append_image_extraction_items(html_content, items, rule, url)

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
                    href = element.get("href", "")
                    transform = field_def.get("transform")
                    if transform:
                        href = _transform_url(href, transform)
                    item[field_name] = href
                    # Resolve URL through browser if resolve_url is set (graceful fallback)
                    if field_def.get("resolve_url") and item[field_name]:
                        try:
                            if self.browser_crawler is None:
                                from .crawl_browser import BrowserCrawler
                                self.browser_crawler = BrowserCrawler()
                            resolved = self.browser_crawler.resolve_url(item[field_name])
                            item[field_name] = resolved
                        except Exception:
                            pass  # Keep original URL on any error (e.g. Playwright not installed)
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

        return self._append_image_extraction_items(html_content, items, rule, url)
    
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
    
    def save_output(self, items: list, rule: dict, dedup_filtered: int = 0,
                    governance_summary: dict | None = None) -> str:
        """Save items to JSON output"""
        return self.output_mgr.save(items, rule, dedup_filtered, governance_summary)

    def _maybe_archive_page(self, rule: dict, items: list, html: str | None) -> dict:
        """如果规则配置了 archive.enabled=true，组装并写出归档包与主库记录。"""
        archive_cfg = rule.get("archive") or {}
        if not archive_cfg.get("enabled"):
            return {}

        source = rule.get("source", {}) or {}
        source_url = source.get("url", "")
        domain = urlparse(source_url).netloc or source.get("platform", "")
        title = ""
        if items and isinstance(items[0], dict):
            title = items[0].get("title") or ""

        archive_page = build_archive_page(
            source_url=source_url,
            entry_url=source_url,
            final_url=source_url,
            domain=domain,
            platform=source.get("platform"),
            subject=rule.get("subject") or source.get("subject"),
            title=title,
            source_name=source.get("source_name"),
            publish_time=None,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            html=html or "",
            markdown="",
            blocks=[],
            assets=[],
        )

        package_path = self.output_mgr.save_archive_package(archive_page, rule)
        store = ArchiveStore.from_rule(rule)
        write_result = store.save_archive_page(archive_page)
        return {
            "archive_page_id": write_result.get("page_id"),
            "archive_package_path": package_path,
        }

    def preview_rule(self, rule_path: str, limit: int = 5) -> dict:
        """沙箱试采规则，不写状态、去重库或正式输出文件。"""
        rule = self.load_rule(rule_path)
        top_enabled = rule.get("enabled", True)
        source_enabled = rule.get("source", {}).get("enabled", True)
        if not top_enabled or not source_enabled:
            return {
                "success": True,
                "status": "skipped",
                "reason": "rule_disabled",
                "total_collected": 0,
                "preview_count": 0,
                "items": [],
                "governance": {},
                "ocr_summary": {},
            }

        safe_limit = max(1, min(int(limit or 5), 20))
        items = self.crawl(rule)
        governance_result = GovernancePipeline(rule).process(items)
        governed_items = governance_result.items
        preview_items = governed_items[:safe_limit]
        return {
            "success": True,
            "status": "partial_success" if governance_result.status == "PARTIAL_SUCCESS" else "success",
            "total_collected": len(governed_items),
            "preview_count": len(preview_items),
            "items": preview_items,
            "governance": governance_result.summary,
            "ocr_summary": self.last_ocr_summary,
        }
    
    def run(self, rule_path: str, event_handler=None, include_data: bool = False) -> dict:
        """Run full collection pipeline, record state, return result dict"""
        import copy
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
            raw_items = copy.deepcopy(items)
            total_collected = len(items)
            event_handler(event_status(rule_path, "running", f"采集完成，共 {total_collected} 条"))

            # Deduplicate
            items, dedup_filtered = self.deduplicate(items, rule)
            event_handler(event_status(rule_path, "running", f"去重后 {len(items)} 条新数据"))

            # Save output
            governance_result = GovernancePipeline(rule).process(items)
            items = governance_result.items
            output_path = self.save_output(
                items,
                rule,
                dedup_filtered,
                governance_summary=governance_result.summary,
            )

            archive_info = self._maybe_archive_page(rule, items, html=None)

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

            result = {
                "status": "partial_success" if governance_result.status == "PARTIAL_SUCCESS" else "success",
                "rule": rule_name,
                "collected": len(items),
                "total_collected": total_collected,
                "dedup_filtered": dedup_filtered,
                "output_path": output_path if output_path != "" else None,
                "duration": duration,
                "governance": governance_result.summary,
            }
            if include_data:
                result["raw_data"] = raw_items
                result["deduped_data"] = items
            if archive_info:
                result.update(archive_info)
            return result

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
                "collected": 0,
                "total_collected": 0,
                "dedup_filtered": 0,
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
