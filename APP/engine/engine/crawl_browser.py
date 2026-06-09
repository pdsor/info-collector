"""Browser Crawler - handles JavaScript-rendered pages and anti-bot protection."""
from typing import Optional
from .crawlers import PlaywrightCrawler, CloakBrowserCrawler, USER_AGENTS


# client 别名 → 实现类。新增 cloakbrowser 用于绕过瑞数/Cloudflare 等 JS WAF
_CLIENT_REGISTRY = {
    "browser": PlaywrightCrawler,
    "playwright": PlaywrightCrawler,
    "cloakbrowser": CloakBrowserCrawler,
    "cloak": CloakBrowserCrawler,
}


class BrowserCrawler:
    """确定性浏览器渲染器，按 client 委托给具体实现。

    Args:
        client: "browser" / "playwright" (默认) | "cloakbrowser" / "cloak"
    """

    def __init__(self, client: str = None):
        """client: 选择具体浏览器实现。"""
        self._client = client or "browser"
        self._impl: Optional[object] = None
        self._impl_type: Optional[str] = None
        self._ensure_impl()

    def _ensure_impl(self):
        """Lazy init based on current _client"""
        if self._impl_type == self._client:
            return
        if self._client == "crawl4ai":
            raise ValueError("Crawl4AI 已从 v2.2 架构移除，请使用 Playwright 或 CloakBrowser 渲染")
        impl_cls = _CLIENT_REGISTRY.get(self._client)
        if impl_cls is None:
            raise ValueError(f"Unknown client: {self._client}")
        self._impl = impl_cls()
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
    
    def close(self):
        """Cleanup crawler resources"""
        if self._impl is not None:
            self._impl.close()
