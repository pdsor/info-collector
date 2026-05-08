"""Tests for Crawl4AI routing in BrowserCrawler"""
import pytest
from unittest.mock import patch, MagicMock


class TestBrowserCrawlerRouting:
    """Verify client routing: 'browser'/'playwright' -> PlaywrightCrawler, 'crawl4ai' -> Crawl4AICrawler"""

    def test_browser_routes_to_playwright(self):
        """client='browser' should route to PlaywrightCrawler"""
        from engine.crawl_browser import BrowserCrawler
        bc = BrowserCrawler(client='browser')
        assert bc._impl_type == 'browser'
        assert bc.client == 'browser'
        assert type(bc._impl).__name__ == 'PlaywrightCrawler'

    def test_playwright_routes_to_playwright_crawler(self):
        """client='playwright' should route to PlaywrightCrawler"""
        from engine.crawl_browser import BrowserCrawler
        bc = BrowserCrawler(client='playwright')
        assert type(bc._impl).__name__ == 'PlaywrightCrawler'

    def test_browser_and_playwright_same_impl_type(self):
        """client='browser' and 'playwright' should route to same impl type"""
        from engine.crawl_browser import BrowserCrawler
        bc1 = BrowserCrawler(client='browser')
        bc2 = BrowserCrawler(client='playwright')
        assert type(bc1._impl).__name__ == type(bc2._impl).__name__ == 'PlaywrightCrawler'

    def test_default_client_is_browser(self):
        """Default client (None) should be 'browser' -> PlaywrightCrawler"""
        from engine.crawl_browser import BrowserCrawler
        bc = BrowserCrawler()
        assert bc.client == 'browser'
        assert type(bc._impl).__name__ == 'PlaywrightCrawler'

    def test_crawl4ai_routes_to_crawl4ai_crawler(self):
        """client='crawl4ai' should route to Crawl4AICrawler"""
        with patch('engine.crawlers.crawl4ai_crawler.AsyncWebCrawler') as mock_c4a:
            mock_instance = MagicMock()
            mock_c4a.return_value = mock_instance
            mock_result = MagicMock()
            mock_result.html = '<html>test</html>'
            mock_result.markdown = None
            mock_instance.arun.return_value = mock_result

            from engine.crawl_browser import BrowserCrawler
            bc = BrowserCrawler(client='crawl4ai')
            assert type(bc._impl).__name__ == 'Crawl4AICrawler'

    def test_resolve_url_uses_playwright_directly(self):
        """resolve_url() should use PlaywrightCrawler directly, not the current impl"""
        with patch('engine.crawl_browser.PlaywrightCrawler') as mock_pw_cls:
            mock_pw = MagicMock()
            mock_pw.resolve_url.return_value = 'https://mp.weixin.qq.com/s/xxx'
            mock_pw_cls.return_value = mock_pw

            from engine.crawl_browser import BrowserCrawler
            bc = BrowserCrawler(client='crawl4ai')  # impl is Crawl4AI
            result = bc.resolve_url('https://weixin.sogou.com/link?url=...')

            mock_pw.resolve_url.assert_called_once()
            assert result == 'https://mp.weixin.qq.com/s/xxx'
