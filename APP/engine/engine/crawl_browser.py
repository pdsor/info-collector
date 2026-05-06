"""Browser Crawler - handles JavaScript-rendered pages and anti-bot protection

This module provides a dual-routing BrowserCrawler that delegates to:
  - PlaywrightCrawler (for Playwright-based rendering)
  - Crawl4AICrawler (for Crawl4AI-based rendering, future)
"""
from .crawlers import PlaywrightCrawler, Crawl4AICrawler


class BrowserCrawler:
    """Dual-routing crawler that delegates to PlaywrightCrawler or Crawl4AICrawler.
    
    Args:
        crawler_type: "playwright" (default) or "crawl4ai" (future)
    """
    
    def __init__(self, crawler_type: str = "playwright"):
        self._crawler_type = crawler_type
        if crawler_type == "playwright":
            self._impl = PlaywrightCrawler()
        elif crawler_type == "crawl4ai":
            self._impl = Crawl4AICrawler()
        else:
            raise ValueError(f"Unknown crawler type: {crawler_type}")
    
    @property
    def crawler_type(self) -> str:
        return self._crawler_type
    
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
        return self._impl.fetch(url, render_config)
    
    def fetch_with_screenshot(self, url: str, render_config: dict = None) -> tuple:
        """Fetch page and return (html, screenshot_path). For debugging."""
        return self._impl.fetch_with_screenshot(url, render_config)
    
    def parse_items(self, html_content: str, items_path: str) -> list:
        """Parse items from browser-rendered HTML using CSS/XPath/regex extraction."""
        return self._impl.parse_items(html_content, items_path)
    
    def extract_attr(self, html_content: str, xpath: str, attr: str) -> str:
        """Extract attribute from HTML element."""
        return self._impl.extract_attr(html_content, xpath, attr)
    
    def extract_text(self, html_content: str, xpath: str) -> str:
        """Extract text content from HTML element."""
        return self._impl.extract_text(html_content, xpath)
    
    def extract_fields(self, html_content: str, field_defs: list) -> dict:
        """Extract fields from HTML based on field definitions"""
        return self._impl.extract_fields(html_content, field_defs)
    
    def close(self):
        """Cleanup crawler resources"""
        self._impl.close()
