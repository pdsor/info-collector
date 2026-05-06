"""Crawl4AI-based crawler"""
import asyncio
from typing import Optional

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, DefaultMarkdownGenerator
from lxml import html as lxml_html


class Crawl4AICrawler:
    """Crawler using Crawl4AI (AsyncWebCrawler) for JavaScript-rendered pages."""

    def __init__(self):
        self._crawler: Optional[AsyncWebCrawler] = None

    def _get_crawler(self) -> AsyncWebCrawler:
        """Lazy init of AsyncWebCrawler"""
        if self._crawler is None:
            self._crawler = AsyncWebCrawler()
        return self._crawler

    def _build_browser_config(self, config: dict) -> BrowserConfig:
        """Build BrowserConfig from render_config dict."""
        return BrowserConfig(
            headless=config.get("headless", True),
            enable_stealth=config.get("stealth", False) or config.get("anti_bot", False),
            viewport_width=config.get("viewport_width", 1920),
            viewport_height=config.get("viewport_height", 1080),
            user_agent=config.get("user_agent"),
        )

    def _build_crawler_config(self, config: dict) -> CrawlerRunConfig:
        """Build CrawlerRunConfig from render_config dict."""
        want_markdown = config.get("markdown", True)
        return CrawlerRunConfig(
            wait_for=config.get("wait_for_selector"),
            wait_for_timeout=config.get("wait_for_timeout"),
            remove_forms=config.get("remove_forms", False),
            markdown_generator=DefaultMarkdownGenerator() if want_markdown else None,
        )

    async def _async_fetch(self, url: str, render_config: dict) -> str:
        """Async fetch implementation."""
        config = render_config or {}
        browser_cfg = self._build_browser_config(config)
        crawler_cfg = self._build_crawler_config(config)

        crawler = self._get_crawler()
        result = await crawler.arun(url=url, config=crawler_cfg, browser_config=browser_cfg)

        # Return markdown if available and requested, otherwise html
        want_markdown = config.get("markdown", True)
        if want_markdown:
            # result.markdown can be a MarkdownGenerationResult or string
            if hasattr(result, 'markdown') and result.markdown:
                if isinstance(result.markdown, str):
                    return result.markdown
                # It's a MarkdownGenerationResult object with .raw_markdown or similar
                return str(result.markdown)
        return result.html

    def fetch(self, url: str, render_config: dict = None) -> str:
        """Fetch page using Crawl4AI browser, return markdown or html.

        render_config keys:
            headless: bool (default True)
            stealth: bool (default False) — BrowserConfig.enable_stealth
            anti_bot: bool (default False) — alias for enable_stealth
            viewport_width: int (default 1920)
            viewport_height: int (default 1080)
            wait_for_selector: str — CSS selector to wait for
            wait_for_timeout: int — timeout for wait_for
            markdown: bool (default True) — return markdown instead of raw html
            remove_forms: bool (default False) — remove form elements
        """
        return asyncio.get_event_loop().run_until_complete(self._async_fetch(url, render_config))

    async def _async_extract_with_llm(
        self, url: str, prompt: str, schema: dict, strategy, render_config: dict
    ) -> str:
        """Async LLM extraction implementation."""
        from crawl4ai import LLMExtractionStrategy

        config = render_config or {}
        browser_cfg = self._build_browser_config(config)

        # Build extraction strategy
        if strategy == "llm":
            extraction_strategy = LLMExtractionStrategy(
                instruction=prompt,
                schema=schema,
            )
        elif strategy == "cosine":
            from crawl4ai import CosineStrategy
            extraction_strategy = CosineStrategy(
                semantic_filter=prompt,
                **schema,  # model_name, sim_threshold, top_k
            )
        else:
            extraction_strategy = None

        crawler_cfg = CrawlerRunConfig(
            extraction_strategy=extraction_strategy,
            wait_for=config.get("wait_for_selector"),
            wait_for_timeout=config.get("wait_for_timeout"),
        )

        crawler = self._get_crawler()
        result = await crawler.arun(url=url, config=crawler_cfg, browser_config=browser_cfg)

        # Return extracted content or markdown
        if hasattr(result, 'extracted_content') and result.extracted_content:
            return result.extracted_content
        if hasattr(result, 'markdown') and result.markdown:
            if isinstance(result.markdown, str):
                return result.markdown
            return str(result.markdown)
        return result.html

    def extract_with_llm(
        self, url: str, prompt: str, schema: dict = None, strategy: str = "llm", render_config: dict = None
    ) -> str:
        """Extract structured content from page using LLM.

        Args:
            url: URL to crawl
            prompt: Instruction for LLM extraction
            schema: Schema dict for structured extraction (optional)
            strategy: "llm" (default) or "cosine" semantic filtering
            render_config: Browser rendering config (same keys as fetch())
        """
        return asyncio.get_event_loop().run_until_complete(
            self._async_extract_with_llm(url, prompt, schema, strategy, render_config)
        )

    def parse_items(self, html_content: str, items_path: str) -> list:
        """Parse items from HTML using CSS/XPath extraction.

        Args:
            html_content: HTML string to parse
            items_path: CSS selector or XPath expression

        Returns:
            List of matched element strings
        """
        tree = lxml_html.fromstring(html_content)
        # Detect XPath (starts with // or /) vs CSS selector
        if items_path.startswith("//") or items_path.startswith("/"):
            items = tree.xpath(items_path)
        else:
            items = tree.cssselect(items_path)
        return [lxml_html.tostring(el, encoding="unicode") for el in items]

    def extract_attr(self, html_content: str, xpath: str, attr: str) -> str:
        """Extract attribute value from HTML using XPath.

        Args:
            html_content: HTML string to parse
            xpath: XPath expression to locate element
            attr: Attribute name to extract

        Returns:
            Attribute value or empty string if not found
        """
        tree = lxml_html.fromstring(html_content)
        elements = tree.xpath(xpath)
        if elements:
            return elements[0].get(attr, "")
        return ""

    def extract_text(self, html_content: str, xpath: str) -> str:
        """Extract text content from HTML using XPath.

        Args:
            html_content: HTML string to parse
            xpath: XPath expression to locate element

        Returns:
            Text content (stripped) or empty string if not found
        """
        tree = lxml_html.fromstring(html_content)
        elements = tree.xpath(xpath)
        if elements:
            return elements[0].text_content().strip()
        return ""

    def extract_fields(self, html_content: str, field_defs: list) -> dict:
        """Extract multiple fields from HTML using field definitions.

        Args:
            html_content: HTML string to parse
            field_defs: List of dicts with keys: name, xpath, attr (optional)
                       If attr is provided, extract attribute; otherwise extract text.

        Returns:
            Dict mapping field names to extracted values
        """
        tree = lxml_html.fromstring(html_content)
        result = {}
        for field in field_defs:
            name = field.get("name")
            xpath = field.get("xpath")
            attr = field.get("attr")
            elements = tree.xpath(xpath)
            if not elements:
                result[name] = ""
                continue
            if attr:
                result[name] = elements[0].get(attr, "")
            else:
                result[name] = elements[0].text_content().strip()
        return result

    def close(self):
        """Cleanup Crawl4AI resources."""
        if self._crawler is not None:
            try:
                asyncio.get_event_loop().run_until_complete(self._crawler.close())
            except Exception:
                pass
            self._crawler = None
