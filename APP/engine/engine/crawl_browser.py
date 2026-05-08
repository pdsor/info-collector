"""Browser Crawler - handles JavaScript-rendered pages and anti-bot protection

Dual-routing BrowserCrawler that delegates to:
  - PlaywrightCrawler (for JS rendering — current default, stable)
  - Crawl4AICrawler (for JS rendering + stealth — target default, blocked by runtime hang)
"""
from typing import Optional
from .crawlers import PlaywrightCrawler, Crawl4AICrawler


class BrowserCrawler:
    """Dual-routing crawler: Playwright for JS rendering, Crawl4AI for stealth mode.

    Routing:
      - "browser"     → PlaywrightCrawler (JS rendering, stable — current default)
      - "playwright"  → PlaywrightCrawler (same as browser)
      - "crawl4ai"    → Crawl4AICrawler (stealth/anti-bot, async runtime hang — TODO)

    TODO: Switch "browser" → Crawl4AICrawler once async runtime hang is resolved.
    """

    def __init__(self, client: str = None):
        """client: "browser" (default=PlaywrightCrawler) or "crawl4ai" or "playwright" """
        self._client = client or "browser"
        self._impl: Optional[object] = None
        self._impl_type: Optional[str] = None
        self._ensure_impl()

    def _ensure_impl(self):
        """Lazy init based on current _client."""
        if self._impl_type != self._client:
            # "browser" and "playwright" both use PlaywrightCrawler (stable)
            if self._client == "browser" or self._client == "playwright":
                self._impl = PlaywrightCrawler()
            elif self._client == "crawl4ai":
                # TODO: Crawl4AICrawler blocked by async runtime hang in 0.8.6
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
        """Navigate to URL and return the final URL after any redirects.

        Uses Playwright directly with wait_until='commit' — fast, no content waiting.
        Does not use stealth since URL resolution doesn't need it.
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
                "Use 'crawl4ai' client to enable LLM extraction."
            )
        return self._impl.extract_with_llm(url, prompt, schema, strategy, render_config)

    def close(self):
        """Cleanup crawler resources"""
        if self._impl is not None:
            self._impl.close()
