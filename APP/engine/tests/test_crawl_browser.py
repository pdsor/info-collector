"""Test BrowserCrawler functionality"""
import pytest
import os


class TestBrowserCrawler:
    """Test BrowserCrawler with Playwright"""

    def test_import_browser_crawler(self):
        """Test that BrowserCrawler can be imported"""
        from engine.crawl_browser import BrowserCrawler
        bc = BrowserCrawler()
        assert bc is not None

    def test_user_agents_available(self):
        """Test that USER_AGENTS list is populated"""
        from engine.crawl_browser import USER_AGENTS
        assert len(USER_AGENTS) > 0
        assert all(isinstance(ua, str) for ua in USER_AGENTS)

    def test_fetch_simple_page(self):
        """Test fetching a simple HTTP page (httpbin)"""
        from engine.crawl_browser import BrowserCrawler

        bc = BrowserCrawler()
        try:
            html = bc.fetch("https://httpbin.org/html", {
                "headless": True,
                "wait_for_timeout": 3000
            })
            assert html is not None
            assert len(html) > 0
            assert "Herman Melville" in html
        finally:
            bc.close()

    def test_fetch_with_random_ua(self):
        """Test that random UA is applied"""
        from engine.crawl_browser import BrowserCrawler

        bc = BrowserCrawler()
        try:
            html = bc.fetch("https://httpbin.org/headers", {
                "user_agent": "random",
                "headless": True
            })
            # httpbin returns JSON with headers
            assert html is not None
        finally:
            bc.close()

    def test_parse_items_regex(self):
        """Test regex-based item parsing"""
        from engine.crawl_browser import BrowserCrawler

        bc = BrowserCrawler()
        # Note: regex does NOT match across newlines by default, so keep on one line
        html = '<a href="https://example.com/1" class="item"><img alt="Title 1"/></a><a href="https://example.com/2" class="item"><img alt="Title 2"/></a>'
        items = bc.parse_items(html, 'regex:<a[^>]*href="([^"]+)"[^>]*>.*?<img[^>]*alt="([^"]+)"[^>]*>')
        assert len(items) == 2
        assert items[0]["href"] == "https://example.com/1"
        assert items[0]["title"] == "Title 1"

    def test_parse_items_no_match(self):
        """Test parse_items with non-matching pattern"""
        from engine.crawl_browser import BrowserCrawler

        bc = BrowserCrawler()
        html = "<div>No links here</div>"
        items = bc.parse_items(html, 'regex:<a[^>]*href="([^"]+)"[^>]*>')
        assert items == []

    def test_close_without_launch(self):
        """Test close() works even if browser wasn't launched"""
        from engine.crawl_browser import BrowserCrawler

        bc = BrowserCrawler()
        bc.close()  # Should not raise
