"""Test BrowserCrawler deterministic routing and resolve_url behavior"""
import pytest
from unittest.mock import patch, MagicMock

from engine.crawl_browser import BrowserCrawler
from engine.crawlers import PlaywrightCrawler


class TestCrawl4AIRouting:
    """Test that browser routing is deterministic and AI-free."""

    def test_browser_client_routes_to_playwright(self):
        """client='browser' should use PlaywrightCrawler internally"""
        crawler = BrowserCrawler(client="browser")
        assert isinstance(crawler._impl, PlaywrightCrawler)

    def test_crawl4ai_client_is_rejected(self):
        """client='crawl4ai' should be rejected in v2.2"""
        with pytest.raises(ValueError, match="Crawl4AI"):
            BrowserCrawler(client="crawl4ai")

    def test_playwright_client_still_works(self):
        """client='playwright' should still use PlaywrightCrawler"""
        crawler = BrowserCrawler(client="playwright")
        assert isinstance(crawler._impl, PlaywrightCrawler)

    def test_default_client_is_browser(self):
        """Default client should be 'browser' which routes to Playwright"""
        crawler = BrowserCrawler()
        assert crawler._client == "browser"
        assert isinstance(crawler._impl, PlaywrightCrawler)

    def test_resolve_url_uses_playwright_directly(self):
        """resolve_url() should call PlaywrightCrawler.resolve_url() directly"""
        with patch.object(PlaywrightCrawler, 'resolve_url', return_value="https://final-url.com") as mock_resolve:
            mock_pw_instance = MagicMock()
            mock_pw_instance.resolve_url = mock_resolve
            with patch.object(PlaywrightCrawler, '__init__', return_value=None):
                with patch.object(PlaywrightCrawler, '__new__', return_value=mock_pw_instance):
                    crawler = BrowserCrawler(client="browser")
                    result = crawler.resolve_url("https://initial-url.com", timeout=10000)

            mock_resolve.assert_called_once_with("https://initial-url.com", None, 10000)
            assert result == "https://final-url.com"
