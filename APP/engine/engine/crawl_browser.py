"""Browser Crawler - handles JavaScript-rendered pages and anti-bot protection"""
import re
import json
import random
from datetime import datetime
from typing import Optional

from .parsers import HTMLParser


# Common desktop User-Agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/115.0.1901.203",
]


class BrowserCrawler:
    """Crawler for JavaScript-rendered pages using Playwright (undetected Chrome)"""

    def __init__(self):
        self._playwright = None
        self._browser = None

    def _get_playwright(self):
        """Lazy init of Playwright (import is expensive)"""
        if self._playwright is None:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
        return self._playwright

    def _get_browser(self, headless: bool = True, stealth: bool = True):
        """Get or launch browser instance"""
        pw = self._get_playwright()

        if self._browser is None or not self._browser.is_connected():
            # Use undetected-chromedriver pattern via Playwright's chromium
            args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]

            if stealth:
                # Additional stealth arguments
                args.extend([
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                ])

            self._browser = pw.chromium.launch(
                headless=headless,
                args=args,
            )

        return self._browser

    def fetch(self, url: str, render_config: dict = None) -> str:
        """Fetch page using browser, return HTML after JS rendering.

        render_config keys:
            headless: bool (default True)
            stealth: bool (default True) — try to avoid bot detection
            user_agent: str or "random" (default "random")
            wait_for_selector: str (optional) — CSS selector to wait for
            wait_for_timeout: int (ms, default 3000)
            viewport_width: int (default 1920)
            viewport_height: int (default 1080)
            extra_headers: dict (optional)
        """
        config = render_config or {}
        headless = config.get("headless", True)
        stealth = config.get("stealth", True)
        ua = config.get("user_agent", "random")
        wait_selector = config.get("wait_for_selector")
        wait_timeout = config.get("wait_for_timeout", 3000)
        viewport_w = config.get("viewport_width", 1920)
        viewport_h = config.get("viewport_height", 1080)
        extra_headers = config.get("extra_headers", {})

        if ua == "random":
            ua = random.choice(USER_AGENTS)

        browser = self._get_browser(headless=headless, stealth=stealth)
        context = browser.new_context(
            user_agent=ua,
            viewport={"width": viewport_w, "height": viewport_h},
            ignore_https_errors=True,
            extra_http_headers=extra_headers,
        )
        page = context.new_page()

        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Wait for dynamic content if needed
            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=wait_timeout)
                except Exception:
                    pass  # Fallback: just use current content

            # Additional wait for JS to execute
            page.wait_for_timeout(1500)

            return page.content()

        finally:
            page.close()
            context.close()

    def fetch_with_screenshot(self, url: str, render_config: dict = None) -> tuple:
        """Fetch page and return (html, screenshot_path). For debugging."""
        config = render_config or {}
        headless = config.get("headless", True)
        stealth = config.get("stealth", True)
        ua = config.get("user_agent", "random")
        wait_selector = config.get("wait_for_selector")
        wait_timeout = config.get("wait_for_timeout", 3000)

        if ua == "random":
            ua = random.choice(USER_AGENTS)

        browser = self._get_browser(headless=headless, stealth=stealth)
        context = browser.new_context(
            user_agent=ua,
            viewport={"width": 1920, "height": 1080},
            ignore_https_errors=True,
        )
        page = context.new_page()

        import tempfile
        import os

        screenshot_path = tempfile.mktemp(suffix=".png")

        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=15000)

            if wait_selector:
                try:
                    page.wait_for_selector(wait_selector, timeout=wait_timeout)
                except Exception:
                    pass

            page.wait_for_timeout(1500)
            page.screenshot(path=screenshot_path, full_page=True)

            return page.content(), screenshot_path

        except Exception as e:
            return "", screenshot_path

        finally:
            page.close()
            context.close()

    def parse_items(self, html_content: str, items_path: str) -> list:
        """Parse items from browser-rendered HTML using CSS/XPath/regex extraction.

        Supports multiple formats:
          - css:<selector>        — CSS selector (new), e.g. "css:.item a"
          - xpath:<expr>          — XPath expression (new), e.g. "xpath://div[@class='item']//a"
          - regex:<pattern>       — regex with groups (legacy)
          - //tag[@class='name']  — legacy XPath-style simple class matching
        """
        # New format: css:<selector>
        if items_path.startswith("css:"):
            selector = items_path[4:]
            return HTMLParser.extract_links(selector, html_content)

        # New format: xpath:<expr>
        if items_path.startswith("xpath:"):
            expr = items_path[6:]
            parser = HTMLParser(html_content)
            results = []
            for el in parser.xpath(expr):
                href = el.attrib.get("href", "")
                text = "".join(el.xpath("string()").getall()).strip()
                results.append({"href": href, "title": text})
            return results

        # Legacy format: regex:<pattern> (with re.DOTALL to match newlines)
        if items_path.startswith("regex:"):
            pattern = items_path[6:]
            results = []
            for m in re.finditer(pattern, html_content, re.DOTALL):
                groups = m.groups()
                if len(groups) >= 2:
                    results.append({"href": groups[0], "title": groups[1]})
                elif len(groups) == 1:
                    results.append({"href": groups[0]})
            return results

        # Legacy XPath-style: only handles simple class-based matching
        if "contains(@class" in items_path:
            match = re.search(r"//(\w+)\[contains\(@class,\s*'([^']+)'\)\]", items_path)
            if match:
                tag, class_name = match.groups()
                pattern = rf"<{tag}[^>]*class=['\"]?[^\"']*{re.escape(class_name)}[^\"']*['\"]?[^>]*href=['\"]([^\"']+)['\"][^>]*>"
                matches = re.findall(pattern, html_content, re.DOTALL)
                return [{"href": m} for m in matches]
        elif "@class=" in items_path:
            match = re.search(r"//(\w+)\[@class=['\"]([^'\"]+)['\"]\]", items_path)
            if match:
                tag, class_name = match.groups()
                pattern = rf"<{tag}[^>]*class=['\"]?{re.escape(class_name)}['\"]?[^>]*>"
                matches = re.findall(pattern, html_content, re.DOTALL)
                return [{"html": m} for m in matches]
        return []

    def extract_attr(self, html_content: str, xpath: str, attr: str) -> str:
        """Extract attribute from HTML element.

        Supports:
          - xpath:<expr>         — XPath expression (new)
          - //tag[@class='name'] — legacy XPath-style
        """
        # New format: xpath:<expr>
        if xpath.startswith("xpath:"):
            expr = xpath[6:]
            parser = HTMLParser(html_content)
            selected = parser.xpath(expr)
            if selected:
                return selected[0].attrib.get(attr, "")
            return ""

        # Legacy XPath-style (with re.DOTALL)
        if "@class=" in xpath:
            match = re.search(r"//(\w+)\[@class=['\"]([^'\"]+)['\"]\]", xpath)
            if match:
                tag, class_name = match.groups()
                pattern = rf"<{tag}[^>]*class=['\"]{re.escape(class_name)}['\"][^>]*>"
                match = re.search(pattern, html_content, re.DOTALL)
                if match:
                    element = match.group(0)
                    attr_match = re.search(rf"{attr}=['\"]([^'\"]+)['\"]", element)
                    if attr_match:
                        return attr_match.group(1)
        return ""

    def extract_text(self, html_content: str, xpath: str) -> str:
        """Extract text content from HTML element.

        Supports:
          - xpath:<expr>                    — XPath expression (new)
          - //tag[@class='name']//text()   — legacy XPath-style
          - //tag[@class='name']           — legacy XPath-style (auto-handles text)
        """
        # New format: xpath:<expr>
        if xpath.startswith("xpath:"):
            expr = xpath[6:]
            parser = HTMLParser(html_content)
            selected = parser.xpath(expr)
            if selected:
                return "".join(selected[0].xpath("string()").getall()).strip()
            return ""

        # Legacy XPath-style (with re.DOTALL)
        if "@class=" in xpath:
            # Handle //tag[@class='name']//text() pattern
            match = re.search(r"//(\w+)\[@class=['\"]([^'\"]+)['\"]\]//text\(\)", xpath)
            if match:
                tag, class_name = match.groups()
                pattern = rf"<{tag}[^>]*class=['\"]{re.escape(class_name)}['\"][^>]*>([^<]+)</{tag}>"
                text_match = re.search(pattern, html_content, re.DOTALL)
                if text_match:
                    return text_match.group(1).strip()

            # Handle simple //tag[@class='name'] pattern
            simple_match = re.search(r"//(\w+)\[@class=['\"]([^'\"]+)['\"]\]", xpath)
            if simple_match:
                tag, class_name = simple_match.groups()
                pattern = rf"<{tag}[^>]*class=['\"]{re.escape(class_name)}['\"][^>]*>([^<]+)</{tag}>"
                text_match = re.search(pattern, html_content, re.DOTALL)
                if text_match:
                    return text_match.group(1).strip()
        return ""

    def extract_fields(self, html_content: str, field_defs: list) -> dict:
        """Extract fields from HTML based on field definitions"""
        result = {}

        for field_def in field_defs:
            field_name = field_def["name"]
            field_type = field_def["type"]

            if field_type == "constant":
                result[field_name] = field_def["value"]
            elif field_type == "attr":
                path = field_def.get("path", "")
                attr = field_def.get("attr", "href")
                result[field_name] = self.extract_attr(html_content, path, attr)
            elif field_type == "xpath":
                result[field_name] = self.extract_text(html_content, field_def.get("path", ""))

        return result

    def close(self):
        """Cleanup browser and playwright"""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
