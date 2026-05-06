"""Tests for Crawl4AI integration and browser routing."""
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import sys

sys.path.insert(0, "/root/info-collector/.worktrees/crawl4ai-integration/APP/engine")

from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler
from engine.crawl_browser import BrowserCrawler
from engine.engine import InfoCollectorEngine


class TestCrawl4AICrawler(unittest.TestCase):
    """Tests for Crawl4AICrawler core functionality."""

    @patch("engine.crawlers.crawl4ai_crawler.AsyncWebCrawler")
    @patch("engine.crawlers.crawl4ai_crawler.BrowserConfig")
    def test_fetch_returns_markdown(self, MockBrowserConfig, MockAsyncWebCrawler):
        """verify fetch() returns markdown when markdown=True."""
        mock_crawler_instance = MagicMock()
        mock_result = MagicMock(markdown="# Test", html="<h1>Test</h1>")
        mock_crawler_instance.arun = AsyncMock(return_value=mock_result)
        MockAsyncWebCrawler.return_value = mock_crawler_instance

        crawler = Crawl4AICrawler()
        result = crawler.fetch("https://example.com", {"markdown": True})

        self.assertEqual(result, "# Test")
        mock_crawler_instance.arun.assert_called_once()

    @patch("engine.crawlers.crawl4ai_crawler.AsyncWebCrawler")
    @patch("engine.crawlers.crawl4ai_crawler.BrowserConfig")
    def test_fetch_returns_html_when_markdown_false(self, MockBrowserConfig, MockAsyncWebCrawler):
        """verify fetch() returns html when markdown=False."""
        mock_crawler_instance = MagicMock()
        mock_result = MagicMock(markdown="# Test", html="<h1>Test</h1>")
        mock_crawler_instance.arun = AsyncMock(return_value=mock_result)
        MockAsyncWebCrawler.return_value = mock_crawler_instance

        crawler = Crawl4AICrawler()
        result = crawler.fetch("https://example.com", {"markdown": False})

        self.assertEqual(result, "<h1>Test</h1>")
        mock_crawler_instance.arun.assert_called_once()

    @patch("engine.crawlers.crawl4ai_crawler.AsyncWebCrawler")
    @patch("engine.crawlers.crawl4ai_crawler.BrowserConfig")
    def test_fetch_with_render_config(self, MockBrowserConfig, MockAsyncWebCrawler):
        """verify BrowserConfig is correctly constructed with headless, enable_stealth, viewport_width."""
        mock_crawler_instance = MagicMock()
        mock_result = MagicMock(markdown="# Test", html="<h1>Test</h1>")
        mock_crawler_instance.arun = AsyncMock(return_value=mock_result)
        MockAsyncWebCrawler.return_value = mock_crawler_instance

        crawler = Crawl4AICrawler()
        render_config = {
            "headless": False,
            "stealth": True,
            "viewport_width": 1280,
        }
        crawler.fetch("https://example.com", render_config)

        MockBrowserConfig.assert_called_once_with(
            headless=False,
            enable_stealth=True,
            viewport_width=1280,
            viewport_height=1080,
            user_agent=None,
        )

    @patch.object(Crawl4AICrawler, "_async_extract_with_llm")
    def test_extract_with_llm(self, mock_async_extract):
        """verify LLMExtractionStrategy is passed via _async_extract_with_llm."""
        mock_async_extract.return_value = '{"key": "value"}'

        crawler = Crawl4AICrawler()
        result = crawler.extract_with_llm(
            "https://example.com",
            prompt="Extract data",
            schema={"type": "object"},
            strategy="llm",
            render_config={},
        )

        mock_async_extract.assert_called_once()
        call_args = mock_async_extract.call_args
        self.assertEqual(call_args[0][0], "https://example.com")
        self.assertEqual(call_args[0][1], "Extract data")
        self.assertEqual(call_args[0][2], {"type": "object"})
        self.assertEqual(call_args[0][3], "llm")
        self.assertEqual(result, '{"key": "value"}')

    @patch("engine.crawlers.crawl4ai_crawler.AsyncWebCrawler")
    @patch("engine.crawlers.crawl4ai_crawler.BrowserConfig")
    def test_close(self, MockBrowserConfig, MockAsyncWebCrawler):
        """verify crawler.close() is called."""
        mock_crawler_instance = MagicMock()
        mock_crawler_instance.arun = AsyncMock(return_value=MagicMock(markdown="# Test", html="<h1>Test</h1>"))
        mock_crawler_instance.close = AsyncMock()
        MockAsyncWebCrawler.return_value = mock_crawler_instance

        crawler = Crawl4AICrawler()
        crawler.fetch("https://example.com", {})
        crawler.close()

        mock_crawler_instance.close.assert_called_once()


class TestBrowserCrawlerDualRouting(unittest.TestCase):
    """Tests for BrowserCrawler dual-routing between playwright and crawl4ai."""

    def test_default_client_is_playwright(self):
        """BrowserCrawler() default client should be 'playwright'."""
        crawler = BrowserCrawler()
        self.assertEqual(crawler.client, "playwright")

    def test_switch_to_crawl4ai(self):
        """switch_client('crawl4ai') should change client to 'crawl4ai'."""
        crawler = BrowserCrawler()
        crawler.switch_client("crawl4ai")
        self.assertEqual(crawler.client, "crawl4ai")

    def test_switch_closes_old_impl(self):
        """switch_client should call close() on old impl."""
        with patch("engine.crawl_browser.PlaywrightCrawler") as MockPlaywrightCrawler:
            mock_impl = MagicMock()
            MockPlaywrightCrawler.return_value = mock_impl

            crawler = BrowserCrawler()
            mock_impl.close.reset_mock()

            crawler.switch_client("crawl4ai")

            mock_impl.close.assert_called_once()

    def test_extract_with_llm_delegates(self):
        """BrowserCrawler.extract_with_llm should delegate to Crawl4AICrawler.extract_with_llm."""
        with patch("engine.crawl_browser.Crawl4AICrawler") as MockCrawl4AI:
            mock_crawl4ai_impl = MagicMock()
            mock_crawl4ai_impl.extract_with_llm = MagicMock(return_value='{"key": "value"}')
            mock_crawl4ai_impl.close = MagicMock()
            MockCrawl4AI.return_value = mock_crawl4ai_impl

            with patch("engine.crawl_browser.PlaywrightCrawler") as MockPlaywright:
                mock_pw_impl = MagicMock()
                mock_pw_impl.close = MagicMock()
                MockPlaywright.return_value = mock_pw_impl

                crawler = BrowserCrawler(client="crawl4ai")
                result = crawler.extract_with_llm(
                    "https://example.com",
                    prompt="Extract",
                    schema={},
                    strategy="llm",
                    render_config={},
                )

                mock_crawl4ai_impl.extract_with_llm.assert_called_once()
                self.assertEqual(result, '{"key": "value"}')

    def test_extract_with_llm_not_implemented_on_playwright(self):
        """BrowserCrawler.extract_with_llm should raise NotImplementedError for playwright."""
        crawler = BrowserCrawler(client="playwright")

        with self.assertRaises(NotImplementedError) as ctx:
            crawler.extract_with_llm(
                "https://example.com",
                prompt="Extract",
                schema={},
                strategy="llm",
                render_config={},
            )

        self.assertIn("crawl4ai", str(ctx.exception))


class TestEngineBrowserRouting(unittest.TestCase):
    """Tests for engine browser client routing logic."""

    def test_get_browser_client_top_level(self):
        """rule['client'] = 'crawl4ai' should return 'crawl4ai'."""
        engine = InfoCollectorEngine()
        rule = {"client": "crawl4ai", "source": {"type": "browser", "url": "https://example.com"}}
        self.assertEqual(engine._get_browser_client(rule), "crawl4ai")
        engine.close()

    def test_get_browser_client_source_level(self):
        """rule['source']['client'] = 'crawl4ai' should return 'crawl4ai'."""
        engine = InfoCollectorEngine()
        rule = {"source": {"type": "browser", "client": "crawl4ai", "url": "https://example.com"}}
        self.assertEqual(engine._get_browser_client(rule), "crawl4ai")
        engine.close()

    def test_get_browser_client_default(self):
        """No client specified should default to 'playwright'."""
        engine = InfoCollectorEngine()
        rule = {"source": {"type": "browser", "url": "https://example.com"}}
        self.assertEqual(engine._get_browser_client(rule), "playwright")
        engine.close()

    @patch("engine.crawl_browser.BrowserCrawler.switch_client")
    def test_crawl_browser_switches_client(self, mock_switch):
        """_crawl_browser should call browser_crawler.switch_client when client differs."""
        engine = InfoCollectorEngine()
        engine.browser_crawler = MagicMock()

        rule = {
            "client": "crawl4ai",
            "source": {"type": "browser", "url": "https://example.com"},
            "render": {},
            "list": {"items_path": "//div", "fields": []},
        }

        engine._crawl_browser(rule)

        engine.browser_crawler.switch_client.assert_called_once_with("crawl4ai")

    @patch.object(InfoCollectorEngine, "_crawl_with_extraction")
    def test_crawl_with_extraction_enabled(self, mock_extract):
        """When source.extraction.enabled is True, _crawl_with_extraction should be called."""
        engine = InfoCollectorEngine()

        rule = {
            "source": {
                "type": "browser",
                "url": "https://example.com",
                "extraction": {"enabled": True, "prompt": "Extract"},
            },
            "render": {},
        }

        engine._crawl_browser(rule)

        mock_extract.assert_called_once_with(rule)


if __name__ == "__main__":
    unittest.main()
