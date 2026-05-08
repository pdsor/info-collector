"""Test BrowserCrawler routing to Crawl4AI and resolve_url behavior"""
import pytest
from unittest.mock import patch, MagicMock

from engine.crawl_browser import BrowserCrawler
from engine.crawlers import PlaywrightCrawler, Crawl4AICrawler


class TestCrawl4AIRouting:
    """Test that 'browser' client routes to Crawl4AICrawler"""

    def test_browser_client_routes_to_crawl4ai(self):
        """client='browser' should use Crawl4AICrawler internally"""
        crawler = BrowserCrawler(client="browser")
        assert isinstance(crawler._impl, Crawl4AICrawler)

    def test_browser_and_crawl4ai_route_same_impl_type(self):
        """client='browser' and client='crawl4ai' should route to same impl type"""
        browser_crawler = BrowserCrawler(client="browser")
        crawl4ai_crawler = BrowserCrawler(client="crawl4ai")

        # Both should be Crawl4AICrawler instances
        assert type(browser_crawler._impl) == type(crawl4ai_crawler._impl)
        assert isinstance(browser_crawler._impl, Crawl4AICrawler)
        assert isinstance(crawl4ai_crawler._impl, Crawl4AICrawler)

    def test_playwright_client_still_works(self):
        """client='playwright' should still use PlaywrightCrawler"""
        crawler = BrowserCrawler(client="playwright")
        assert isinstance(crawler._impl, PlaywrightCrawler)

    def test_default_client_is_browser(self):
        """Default client should be 'browser' which routes to Crawl4AI"""
        crawler = BrowserCrawler()
        assert crawler._client == "browser"
        assert isinstance(crawler._impl, Crawl4AICrawler)

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