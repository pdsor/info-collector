"""Info Collector Engine - Main Engine Class"""
import mimetypes
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse
import base64
import time
from hashlib import sha256
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
from .archive import _build_content_hash
from .archive_store import ArchiveStore
from .collection_store import CollectionStore
from .ocr_plugins import get_ocr_plugin
from .structuring import run_structuring


def _resolve_max_details(value) -> int | None:
    """解析详情页数量上限；空值、0、all 表示不限制。"""
    if value in (None, "", 0, "0", "all", "ALL", "unlimited", "Unlimited"):
        return None
    limit = int(value)
    return limit if limit > 0 else None


def _download_image_for_archive(url: str, image_ocr_cfg: dict) -> str:
    """复用 ImageExtractionRunner 的下载实现，避免重复实现重试/大小限制。"""
    runner = ImageExtractionRunner(
        {"image_extraction": {"download": image_ocr_cfg.get("download") or {}}}
    )
    return runner.download_image(url)


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
        self._last_list_html = ""
        self._last_list_htmls: list[str] = []

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

        # client: browser/cloakbrowser 强制走浏览器渲染，无视 source.type
        if client_mode in {"browser", "cloakbrowser", "cloak", "playwright"}:
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
        pagination_cfg = (rule.get("list") or {}).get("pagination") or {}
        if pagination_cfg.get("type") == "url_template":
            return self._crawl_html_url_template(rule, url, pagination_cfg)

        html_content = self._fetch_one_html_page(rule, url)
        self._last_list_html = html_content
        self._last_list_htmls = [html_content] if html_content else []

        items_path = (rule.get("list") or {}).get("items_path", "")
        elements = self.html_crawler.parse_items(html_content, items_path)

        if "extract" in rule:
            items = self._extract_rule_v2_items(elements, rule)
        else:
            items = self._parse_legacy_items(elements, rule)

        self._apply_dedup_raw_ids(items, rule)
        return self._append_image_extraction_items(html_content, items, rule, url)

    def _apply_dedup_raw_ids(self, items: list, rule: dict) -> None:
        """从 item.url 按 url_to_id_pattern 填充 raw_id（就地修改）。"""
        import re as _re
        pattern = (rule.get("dedup") or {}).get("url_to_id_pattern")
        if not pattern:
            return
        for item in items:
            if item.get("raw_id"):
                continue
            m = _re.search(pattern, item.get("url", ""))
            if m:
                item["raw_id"] = m.group(1)

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
                if field_type in ("attribute", "attr"):
                    attr = field_def.get("attribute") or field_def.get("attr", "")
                    raw = selected.attrib.get(attr, "") if selected else ""
                    base = field_def.get("base_url", "")
                    item[field_name] = urljoin(base, raw) if base and raw else raw
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

    def _fetch_one_html_page(self, rule: dict, url: str) -> str:
        """按规则 UA 策略抓单页 HTML。"""
        source = rule.get("source", {})
        request_headers = rule.get("request", {}).get("headers", {})
        client_mode = source.get("client", "desktop")
        user_agent = request_headers.get("User-Agent")
        if not user_agent:
            if client_mode == "mobile":
                user_agent = UA.MOBILE
            elif client_mode == "desktop":
                user_agent = UA.DESKTOP
        fetch_kwargs: dict = {}
        if user_agent:
            fetch_kwargs["headers"] = {**request_headers, "User-Agent": user_agent}
        elif request_headers:
            fetch_kwargs["headers"] = request_headers
        MIN_RESPONSE_SIZE = 5000
        if client_mode == "auto":
            desktop_kw = {**fetch_kwargs, "headers": {**(fetch_kwargs.get("headers", {})), "User-Agent": UA.DESKTOP}}
            html = self.html_crawler.fetch(url, **desktop_kw)
            if len(html) < MIN_RESPONSE_SIZE:
                mobile_kw = {**fetch_kwargs, "headers": {**(fetch_kwargs.get("headers", {})), "User-Agent": UA.MOBILE}}
                html = self.html_crawler.fetch(url, **mobile_kw)
            return html
        return self.html_crawler.fetch(url, **fetch_kwargs)

    def _crawl_html_url_template(self, rule: dict, base_url: str, pagination_cfg: dict) -> list:
        """URL 模板翻页：循环替换 {page} 直至无结果或达到 max_pages。"""
        url_template = pagination_cfg.get("url_template") or base_url
        start_page = int(pagination_cfg.get("start_page") or 1)
        max_pages = int(pagination_cfg.get("max_pages") or 10)
        items_path = (rule.get("list") or {}).get("items_path", "")
        all_items: list = []
        first_html = ""
        page_htmls: list[str] = []
        for page_num in range(start_page, start_page + max_pages):
            page_url = url_template.replace("{page}", str(page_num))
            try:
                html = self._fetch_one_html_page(rule, page_url)
            except Exception:
                break
            if not first_html:
                first_html = html
                self._last_list_html = html
            page_htmls.append(html)
            elements = self.html_crawler.parse_items(html, items_path)
            if not elements:
                break
            if "extract" in rule:
                page_items = self._extract_rule_v2_items(elements, rule)
            else:
                page_items = self._parse_legacy_items(elements, rule)
            if not page_items:
                break
            all_items.extend(page_items)
        self._last_list_htmls = page_htmls
        self._apply_dedup_raw_ids(all_items, rule)
        return self._append_image_extraction_items(first_html, all_items, rule, base_url)

    def _parse_legacy_items(self, elements: list, rule: dict) -> list:
        """旧版 list.fields 提取逻辑（不含图片提取）。"""
        import re as _re
        field_defs = (rule.get("list") or {}).get("fields", [])
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
                elif field_type == "xpath":
                    item[field_name] = self.html_crawler.extract_text(
                        element.get("html", ""), field_def.get("path", "")
                    )
            if "url_to_id_pattern" in rule.get("dedup", {}):
                pattern = rule["dedup"]["url_to_id_pattern"]
                m = _re.search(pattern, item.get("url", ""))
                if m:
                    item["raw_id"] = m.group(1)
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
        self._last_list_html = html_content

        # Parse items
        items_path = rule.get("list", {}).get("items_path", "")
        elements = self.browser_crawler.parse_items(html_content, items_path)

        # Extract fields
        if "extract" in rule:
            items = self._extract_rule_v2_items(elements, rule)
            self._apply_dedup_raw_ids(items, rule)
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

    def deduplicate_detailed(self, items: list, rule: dict) -> tuple[list, int, list]:
        """增量去重并返回保留项、过滤数量和过滤明细。"""
        if not rule.get("dedup", {}).get("incremental", False):
            return items, 0, []

        requirement = rule.get("name", "default")
        platform = rule.get("source", {}).get("platform", "unknown")
        kept_items = []
        filtered_items = []

        for item in items:
            raw_id = item.get("raw_id", "")
            dedup_id = f"{platform}_{raw_id}"
            if self.dedup.check(requirement, platform, raw_id):
                filtered = dict(item)
                filtered["_filter_reason"] = "dedup_incremental_existing_raw_id"
                filtered["_matched_existing_id"] = dedup_id
                filtered_items.append(filtered)
                continue
            kept_items.append(item)

        for item in kept_items:
            raw_id = item.get("raw_id", "")
            url = item.get("url", "")
            self.dedup.add(requirement, platform, raw_id, url)

        return kept_items, len(filtered_items), filtered_items
    
    def save_output(self, items: list, rule: dict, dedup_filtered: int = 0,
                    governance_summary: dict | None = None) -> str:
        """Save items to JSON output"""
        return self.output_mgr.save(items, rule, dedup_filtered, governance_summary)

    def _absolutize(self, rule: dict, url: str) -> str:
        if not url:
            return url
        base = (rule.get("source") or {}).get("url", "")
        if not base:
            return url
        return urljoin(base, url)

    def _collect_list_htmls(self, rule: dict, initial_html: str) -> list[str]:
        """返回初始页及按 next-page 链接抓取的后续页 HTML 列表。"""
        list_pagination = (rule.get("list") or {}).get("pagination") or {}
        if list_pagination.get("type") == "url_template" and self._last_list_htmls:
            return self._last_list_htmls
        discovery_cfg = rule.get("discovery") or {}
        pagination = discovery_cfg.get("pagination") or {}
        if not pagination.get("enabled"):
            return [initial_html] if initial_html else []
        max_pages = int(pagination.get("max_pages") or 1)
        next_cfg = pagination.get("next_page") or {}
        selector = next_cfg.get("selector") or ""
        attribute = next_cfg.get("attribute") or "href"
        if not selector:
            return [initial_html] if initial_html else []

        pages = [initial_html]
        current_html = initial_html
        base_url = (rule.get("source") or {}).get("url") or ""
        for _ in range(max_pages - 1):
            sel = parsel.Selector(text=current_html)
            nodes = sel.css(selector)
            if not nodes:
                break
            next_url = nodes[0].attrib.get(attribute, "")
            if not next_url:
                break
            next_url = urljoin(base_url, next_url)
            try:
                current_html = self._fetch_detail_html(rule, next_url)
            except Exception:
                break
            pages.append(current_html)
        return pages

    def _discover_candidates(self, rule: dict, list_html: str) -> list[dict]:
        cfg = rule.get("discovery") or {}
        list_cfg = cfg.get("list") or {}
        items_path = list_cfg.get("items_path", "")
        if not items_path or not list_html:
            return []
        title_def = list_cfg.get("title") or {}
        detail_def = list_cfg.get("detail_url") or {}
        keywords = (cfg.get("filters") or {}).get("title_keywords") or []
        max_details = _resolve_max_details(cfg.get("max_details"))

        selector = parsel.Selector(text=list_html)
        if items_path.startswith("xpath:"):
            items_iter = selector.xpath(items_path[6:])
        else:
            items_iter = selector.css(items_path.removeprefix("css:") if items_path.startswith("css:") else items_path)
        candidates: list[dict] = []
        seen_urls: set[str] = set()
        for item in items_iter:
            title_selector = title_def.get("selector", "")
            if title_selector:
                title = "".join(item.css(title_selector).xpath("string()").getall()).strip()
            else:
                title = "".join(item.xpath("string()").getall()).strip()
            detail_selector = detail_def.get("selector", "")
            url_sel = item.css(detail_selector) if detail_selector else item
            attribute = detail_def.get("attribute", "href")
            detail_url = ""
            if url_sel:
                first = url_sel[0] if hasattr(url_sel, "__getitem__") and len(url_sel) else None
                if first is not None:
                    detail_url = first.attrib.get(attribute, "")
            if not detail_url:
                continue
            if keywords and not any(k in title for k in keywords):
                continue
            absolute = self._absolutize(rule, detail_url)
            if absolute in seen_urls:
                continue
            seen_urls.add(absolute)
            candidates.append({"title": title, "detail_url": absolute})
            if max_details is not None and len(candidates) >= max_details:
                break
        return candidates

    def _discover_first_detail(self, rule: dict, list_html: str) -> dict | None:
        candidates = self._discover_candidates(rule, list_html)
        return candidates[0] if candidates else None

    def _fetch_detail_html(self, rule: dict, detail_url: str) -> str:
        client = (rule.get("source") or {}).get("client", "desktop")
        if client in {"browser", "cloakbrowser", "cloak", "playwright"}:
            return self.browser_crawler.fetch(detail_url, rule.get("render", {}) or {})
        return self.html_crawler.fetch(detail_url)

    def _extract_detail_blocks(self, rule: dict, detail_html: str) -> tuple[str, list[dict]]:
        archive_cfg = rule.get("archive") or {}
        metadata = (archive_cfg.get("detail") or {}).get("metadata") or {}
        title_selector = (metadata.get("title") or {}).get("selector") or "h1"
        content_selector = (metadata.get("content") or {}).get("selector") or "body"

        selector = parsel.Selector(text=detail_html or "")
        title = "".join(selector.css(title_selector).xpath("string()").getall()).strip()

        blocks: list[dict] = []
        if title:
            blocks.append({"block_id": "b1", "type": "heading", "order": 1, "text": title, "level": 1})

        # 优先提取 <p>，若为空则回退到直接子 <div>（部分政府网站正文用 div 而非 p）
        paras = selector.css(f"{content_selector} p")
        if not paras:
            paras = selector.css(f"{content_selector} > div")
        for index, para in enumerate(paras, start=2):
            text = "".join(para.xpath("string()").getall()).strip()
            if text:
                blocks.append({"block_id": f"b{index}", "type": "paragraph", "order": index, "text": text})
        return title, blocks

    def _extract_detail_assets_and_ocr(
        self,
        rule: dict,
        detail_html: str,
        detail_url: str,
        next_index: int,
        progress=None,
    ) -> tuple[list[dict], list[dict]]:
        cfg = (rule.get("archive") or {}).get("image_ocr") or {}
        if not cfg.get("enabled"):
            return [], []
        images_cfg = cfg.get("images") or {}
        selector_text = images_cfg.get("selector") or "img"
        src_attr = images_cfg.get("src_attribute") or "src"
        max_images = int(images_cfg.get("max_images") or 10)
        ocr_cfg = cfg.get("ocr") or {}
        plugin_name = ocr_cfg.get("plugin") or "tesseract"

        selector = parsel.Selector(text=detail_html or "")
        blocks: list[dict] = []
        assets: list[dict] = []
        image_nodes = selector.css(selector_text)[:max_images]
        image_total = len(image_nodes)

        for image_index, node in enumerate(image_nodes, start=1):
            src = node.attrib.get(src_attr, "").strip()
            if not src:
                continue
            absolute = urljoin(detail_url, src)
            if progress:
                progress(f"OCR 图片 {image_index}/{image_total} 开始下载: {absolute}")
            try:
                local_path = _download_image_for_archive(absolute, cfg)
            except Exception as exc:
                if progress:
                    progress(f"OCR 图片 {image_index}/{image_total} 下载失败: {exc}")
                continue
            image_block_id = f"b{next_index}"
            ocr_block_id = f"b{next_index + 1}"
            try:
                if progress:
                    size_bytes = os.path.getsize(local_path) if os.path.exists(local_path) else 0
                    progress(f"OCR 图片 {image_index}/{image_total} 开始识别: {local_path} ({size_bytes} bytes)")
                ocr_started = time.time()
                ocr_result = get_ocr_plugin(plugin_name).recognize(local_path, ocr_cfg)
                ocr_text = ocr_result.text or ""
                manual = ocr_result.manual_review_required
                ocr_structured_data = ocr_result.structured_data or {}
                ocr_status = ocr_result.status
                ocr_error = ocr_result.error
                ocr_elapsed_seconds = ocr_result.elapsed_seconds
                if progress:
                    progress(
                        f"OCR 图片 {image_index}/{image_total} 识别完成: "
                        f"status={ocr_result.status}, 耗时 {time.time() - ocr_started:.2f}s, "
                        f"文本 {len(ocr_text)} 字"
                    )
            except Exception as exc:
                ocr_text = ""
                manual = True
                ocr_structured_data = {}
                ocr_status = "unavailable"
                ocr_error = str(exc)
                ocr_elapsed_seconds = 0
                if progress:
                    progress(f"OCR 图片 {image_index}/{image_total} 识别异常: {exc}")

            blocks.append({
                "block_id": image_block_id,
                "type": "image",
                "order": next_index,
                "source_url": absolute,
                "storage_uri": local_path,
            })
            blocks.append({
                "block_id": ocr_block_id,
                "type": "ocr",
                "order": next_index + 1,
                "parent_block_id": image_block_id,
                "ocr_text": ocr_text,
                "engine": plugin_name,
                "status": ocr_status,
                "structured_data": ocr_structured_data,
                "elapsed_seconds": ocr_elapsed_seconds,
                "error": ocr_error,
                "manual_review_required": manual,
            })
            assets.append({
                "id": image_block_id,
                "block_id": image_block_id,
                "asset_type": "image",
                "source_url": absolute,
                "storage_uri": local_path,
                "file_name": os.path.basename(local_path),
                "extension": Path(local_path).suffix.lstrip("."),
                "mime_type": mimetypes.guess_type(local_path)[0],
                "size_bytes": os.path.getsize(local_path) if os.path.exists(local_path) else 0,
                "content_hash": self._file_sha256(local_path),
                "downloaded": True,
            })
            next_index += 2
        return blocks, assets

    def _file_sha256(self, path: str) -> str:
        """计算本地文件哈希，用于归档资产去重和审计。"""
        digest = sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _archive_after_pipeline(self, rule: dict, items: list, progress=None) -> dict:
        archive_cfg = rule.get("archive") or {}
        if not archive_cfg.get("enabled"):
            return {}
        discovery_cfg = rule.get("discovery") or {}
        if discovery_cfg.get("enabled"):
            if progress:
                progress("归档阶段开始：发现详情页候选")
            list_htmls = self._collect_list_htmls(rule, self._last_list_html or "")
            # Aggregate candidates across pages, deduplicating URLs
            discovery_cfg_local = rule.get("discovery") or {}
            max_details = _resolve_max_details(discovery_cfg_local.get("max_details"))
            seen_urls: set[str] = set()
            candidates: list[dict] = []
            for html in list_htmls:
                for c in self._discover_candidates(rule, html):
                    if c["detail_url"] not in seen_urls:
                        seen_urls.add(c["detail_url"])
                        candidates.append(c)
                    if max_details is not None and len(candidates) >= max_details:
                        break
                if max_details is not None and len(candidates) >= max_details:
                    break
            if not candidates:
                if progress:
                    progress("归档阶段结束：未发现详情页候选")
                return {}
            if progress:
                progress(f"归档阶段：发现 {len(candidates)} 个详情页候选")
            seen_hashes: set[str] = set()
            archive_pages: list[dict] = []
            for index, candidate in enumerate(candidates, start=1):
                try:
                    if progress:
                        progress(f"归档详情 {index}/{len(candidates)} 开始抓取: {candidate['detail_url']}")
                    detail_html = self._fetch_detail_html(rule, candidate["detail_url"])
                    if progress:
                        progress(f"归档详情 {index}/{len(candidates)} 抓取完成: HTML {len(detail_html)} 字符")
                    detail_hash = _build_content_hash(
                        candidate["detail_url"],
                        candidate["detail_url"],
                        detail_html,
                        "",
                    )
                    store = ArchiveStore.from_rule(rule)
                    ocr_plugin_name = (((rule.get("archive") or {}).get("image_ocr") or {}).get("ocr") or {}).get("plugin") or "tesseract"
                    hash_satisfies_ocr = getattr(store, "content_hash_satisfies_ocr_engine", None)
                    hash_exists = getattr(store, "content_hash_exists", None)
                    if hash_satisfies_ocr:
                        should_skip = hash_satisfies_ocr(detail_hash, ocr_plugin_name)
                    else:
                        should_skip = bool(hash_exists and hash_exists(detail_hash))
                    if should_skip:
                        if progress:
                            progress(
                                f"归档详情 {index}/{len(candidates)} 已存在且满足当前 OCR 引擎，"
                                f"跳过 OCR 和写入: content_hash={detail_hash}, ocr_engine={ocr_plugin_name}"
                            )
                        continue
                    title, blocks = self._extract_detail_blocks(rule, detail_html)
                    if progress:
                        progress(f"归档详情 {index}/{len(candidates)} 正文解析完成: {len(blocks)} 个文本块")
                    extra_blocks, assets = self._extract_detail_assets_and_ocr(
                        rule,
                        detail_html,
                        candidate["detail_url"],
                        next_index=len(blocks) + 1,
                        progress=progress,
                    )
                    blocks.extend(extra_blocks)
                    if progress:
                        progress(
                            f"归档详情 {index}/{len(candidates)} OCR 处理完成: "
                            f"新增 {len(extra_blocks)} 个块, {len(assets)} 个资产"
                        )
                    info = self._maybe_archive_page(
                        rule,
                        items,
                        html=None,
                        detail_url=candidate["detail_url"],
                        detail_html=detail_html,
                        detail_title=title or candidate["title"],
                        detail_blocks=blocks,
                        detail_assets=assets,
                        seen_hashes=seen_hashes,
                    )
                    if progress and info:
                        progress(f"归档详情 {index}/{len(candidates)} 写入完成: page_id={info.get('page_id')}")
                except Exception as exc:
                    if progress:
                        progress(f"归档详情 {index}/{len(candidates)} 失败: {type(exc).__name__}: {exc}")
                    continue
                if info:
                    archive_pages.append(info)
            if not archive_pages:
                if progress:
                    progress("归档阶段结束：没有成功写入的详情页")
                return {}
            head = archive_pages[0]
            if progress:
                progress(f"归档阶段完成：成功写入 {len(archive_pages)} 个详情页")
            return {
                "archive_page_id": head["page_id"],
                "archive_package_path": head["package_path"],
                "archive_pages": archive_pages,
            }
        info = self._maybe_archive_single_page(rule, items, progress=progress)
        if not info:
            return {}
        return {
            "archive_page_id": info["page_id"],
            "archive_package_path": info["package_path"],
            "archive_pages": [info],
        }

    def _maybe_archive_single_page(self, rule: dict, items: list, progress=None) -> dict:
        """archive.enabled 且无 discovery 时，把 rule.source.url 作为单页详情归档。

        会重新抓一次详情 HTML（与 crawl 主流程相对独立），然后走
        _extract_detail_blocks + _extract_detail_assets_and_ocr，让归档包含完整 blocks
        与图像 OCR 内容。失败时安静返回空字典。
        """
        source_url = (rule.get("source") or {}).get("url") or ""
        if not source_url:
            return {}
        try:
            detail_html = self._fetch_detail_html(rule, source_url)
        except Exception:
            return {}
        if not detail_html:
            return {}
        try:
            title, blocks = self._extract_detail_blocks(rule, detail_html)
            extra_blocks, assets = self._extract_detail_assets_and_ocr(
                rule, detail_html, source_url, next_index=len(blocks) + 1, progress=progress
            )
            blocks.extend(extra_blocks)
        except Exception:
            return {}
        if not title and items and isinstance(items[0], dict):
            title = items[0].get("title") or ""
        info = self._maybe_archive_page(
            rule,
            items,
            html=None,
            detail_url=source_url,
            detail_html=detail_html,
            detail_title=title,
            detail_blocks=blocks,
            detail_assets=assets,
            seen_hashes=set(),
        )
        return info or {}

    def _maybe_archive_page(
        self,
        rule: dict,
        items: list,
        html: str | None,
        *,
        detail_url: str | None = None,
        detail_html: str | None = None,
        detail_title: str | None = None,
        detail_blocks: list[dict] | None = None,
        detail_assets: list[dict] | None = None,
        seen_hashes: set[str] | None = None,
    ) -> dict:
        """如果规则配置了 archive.enabled=true，组装并写出归档包与主库记录。"""
        archive_cfg = rule.get("archive") or {}
        if not archive_cfg.get("enabled"):
            return {}

        source = rule.get("source", {}) or {}
        entry_url = source.get("url", "")
        if detail_url:
            source_url = detail_url
            final_url = detail_url
            title = detail_title or ""
            html_for_archive = detail_html or ""
            blocks = detail_blocks or []
            assets = detail_assets or []
        else:
            source_url = entry_url
            final_url = entry_url
            title = ""
            if items and isinstance(items[0], dict):
                title = items[0].get("title") or ""
            html_for_archive = html or ""
            blocks = []
            assets = []

        domain = urlparse(source_url).netloc or source.get("platform", "")

        archive_page = build_archive_page(
            source_url=source_url,
            entry_url=entry_url,
            final_url=final_url,
            domain=domain,
            platform=source.get("platform"),
            subject=rule.get("subject") or source.get("subject"),
            title=title,
            source_name=source.get("source_name"),
            publish_time=None,
            fetched_at=datetime.now(timezone.utc).isoformat(),
            html=html_for_archive,
            markdown="",
            blocks=blocks,
            assets=assets,
        )

        ocr_engine = (((rule.get("archive") or {}).get("image_ocr") or {}).get("ocr") or {}).get("plugin") or ""
        if archive_page.get("ocr_results") and ocr_engine:
            meta = archive_page.setdefault("meta", {})
            metadata = meta.setdefault("metadata", {})
            original_content_hash = meta.get("content_hash") or ""
            metadata["original_content_hash"] = original_content_hash
            metadata["ocr_engine"] = ocr_engine
            meta["content_hash"] = ArchiveStore.build_archive_variant_hash(original_content_hash, ocr_engine)

        content_hash = (archive_page.get("meta") or {}).get("content_hash") or ""
        body_payload = (html_for_archive or "") + "\n" + ((archive_page.get("content") or {}).get("markdown") or "")
        body_hash = sha256(body_payload.encode("utf-8")).hexdigest()
        if seen_hashes is not None and body_hash in seen_hashes:
            return {}
        if seen_hashes is not None:
            seen_hashes.add(body_hash)

        package_path = self.output_mgr.save_archive_package(archive_page, rule)

        structured_records = run_structuring(
            archive_page.get("blocks") or [],
            rule.get("structuring") or {},
        )
        if structured_records:
            archive_page["structured_records"] = structured_records

        store = ArchiveStore.from_rule(rule)
        write_result = store.save_archive_page(archive_page)
        return {
            "page_id": write_result.get("page_id"),
            "package_path": package_path,
            "source_url": source_url,
            "content_hash": content_hash,
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
            items, dedup_filtered, filtered_items = self.deduplicate_detailed(items, rule)
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

            finished_for_store = datetime.now(timezone.utc)
            collection_write = CollectionStore.from_project_config().save_run_items(
                rule=rule,
                rule_path=rule_path,
                items=items,
                governance_summary=governance_result.summary,
                total_collected=total_collected,
                dedup_filtered=dedup_filtered,
                output_path=output_path,
                status="partial_success" if governance_result.status == "PARTIAL_SUCCESS" else "success",
                started_at=datetime.fromtimestamp(start, tz=timezone.utc),
                finished_at=finished_for_store,
                duration_seconds=time.time() - start,
                raw_items=raw_items,
                filtered_items=filtered_items,
                deduped_items=items,
            )

            archive_info = self._archive_after_pipeline(
                rule,
                items,
                progress=lambda msg: event_handler(event_status(rule_path, "running", msg)),
            )

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
                "collection_run_id": collection_write["run_id"],
                "collection_item_count": len(collection_write["item_ids"]),
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
