"""Browser Crawler - handles JavaScript-rendered pages and anti-bot protection

This module provides a dual-routing BrowserCrawler that delegates to:
  - PlaywrightCrawler (for Playwright-based rendering)
  - Crawl4AICrawler (for Crawl4AI-based rendering, default when using "browser" alias)
"""
from typing import Optional
from .crawlers import PlaywrightCrawler, Crawl4AICrawler, USER_AGENTS


class BrowserCrawler:
    """Dual-routing crawler that delegates to PlaywrightCrawler or Crawl4AICrawler.
    
    Args:
        client: "browser" (default, aliases to crawl4ai) or "playwright" or "crawl4ai"
    """
    
    def __init__(self, client: str = None):
        """client: "browser" (default, aliases to crawl4ai) or "playwright" or "crawl4ai" """
        self._client = client or "browser"
        self._impl: Optional[object] = None
        self._impl_type: Optional[str] = None
        self._ensure_impl()
    
    def _ensure_impl(self):
        """Lazy init based on current _client"""
        if self._impl_type != self._client:
            # "browser" is an alias for "crawl4ai" (JS rendering + stealth, default)
            if self._client == "browser":
                effective_client = "crawl4ai"
            else:
                effective_client = self._client
            if effective_client == "playwright":
                self._impl = PlaywrightCrawler()
            elif effective_client == "crawl4ai":
                self._impl = Crawl4AICrawler()
            else:
                raise ValueError(f"Unknown client: {self._client}")
            self._impl_type = self._client
    
    def switch_client(self, client: str):
        """Switch crawler implementation (closes old one first)"""
        if self._client == client:
            return
        if self._impl is not None:
            self._impl.close()
        self._client = client
        self._impl = None
        self._impl_type = None
        self._ensure_impl()
    
    @property
    def crawler_type(self) -> str:
        """Backward compatible alias for _client."""
        return self._client
    
    @property
    def client(self) -> str:
        """Current client type."""
        return self._client
    
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
    
    def resolve_url(self, url: str, render_config: dict = None, timeout: int = 15000) -> str:
        """Resolve a URL through browser redirects, returning the final URL.
        
        URL navigation doesn't need stealth — always uses PlaywrightCrawler directly.
        """
        pw = PlaywrightCrawler()
        return pw.resolve_url(url, render_config, timeout)
    
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
    
    def extract_with_llm(self, url: str, prompt: str, schema: dict = None, strategy: str = "llm", render_config: dict = None):
        """Extract structured content using LLM (only supported by crawl4ai client).
        
        Args:
            url: URL to crawl
            prompt: Instruction for LLM extraction
            schema: Schema dict for structured extraction (optional)
            strategy: "llm" (default) or "cosine" semantic filtering
            render_config: Browser rendering config (same keys as fetch())
        
        Returns:
            LLM extracted content
            
        Raises:
            NotImplementedError: If called on playwright client
        """
        if not hasattr(self._impl, 'extract_with_llm'):
            raise NotImplementedError(
                f"extract_with_llm is not supported by {self._client} client. "
                "Use 'browser' or 'crawl4ai' client to enable LLM extraction."
            )
        return self._impl.extract_with_llm(url, prompt, schema, strategy, render_config)
    
    def close(self):
        """Cleanup crawler resources"""
        if self._impl is not None:
            self._impl.close()
