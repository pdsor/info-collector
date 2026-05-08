"""Tests for Crawl4AI stealth and enhanced configuration."""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestStealthDefault:
    """Test 1: stealth defaults to True when not passed."""

    def test_stealth_default_true(self):
        """When stealth is not passed, enable_stealth should be True."""
        from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler

        crawler = Crawl4AICrawler()
        config = {}
        browser_cfg = crawler._build_browser_config(config)

        assert browser_cfg.enable_stealth is True

    def test_stealth_explicit_false(self):
        """When stealth=False is passed, enable_stealth should be False."""
        from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler

        crawler = Crawl4AICrawler()
        config = {"stealth": False}
        browser_cfg = crawler._build_browser_config(config)

        assert browser_cfg.enable_stealth is False

    def test_stealth_explicit_true(self):
        """When stealth=True is passed, enable_stealth should be True."""
        from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler

        crawler = Crawl4AICrawler()
        config = {"stealth": True}
        browser_cfg = crawler._build_browser_config(config)

        assert browser_cfg.enable_stealth is True


class TestUndetectedMode:
    """Test 2: undetected=True triggers UndetectedAdapter in strategy."""

    @pytest.mark.asyncio
    async def test_undetected_mode_creates_undetected_adapter(self):
        """When undetected=True, UndetectedAdapter should be instantiated and passed to strategy."""
        from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler

        crawler = Crawl4AICrawler()

        with patch("engine.crawlers.crawl4ai_crawler.UndetectedAdapter") as mock_adapter_cls, \
             patch("engine.crawlers.crawl4ai_crawler.AsyncPlaywrightCrawlerStrategy") as mock_strategy_cls, \
             patch("engine.crawlers.crawl4ai_crawler.AsyncWebCrawler") as mock_crawler_cls, \
             patch("engine.crawlers.crawl4ai_crawler.asyncio.get_event_loop") as mock_loop:

            mock_adapter = MagicMock()
            mock_adapter_cls.return_value = mock_adapter

            mock_strategy = MagicMock()
            mock_strategy_cls.return_value = mock_strategy

            mock_crawler = AsyncMock()
            mock_crawler.arun = AsyncMock()
            mock_crawler_cls.return_value = mock_crawler

            result_mock = MagicMock()
            result_mock.markdown = "test content"
            result_mock.html = "<html>test</html>"
            mock_crawler.arun.return_value = result_mock

            with patch.object(crawler, "_build_browser_config") as mock_browser_cfg, \
                 patch.object(crawler, "_build_crawler_config") as mock_crawler_cfg:

                mock_browser_cfg.return_value = MagicMock()
                mock_crawler_cfg.return_value = MagicMock()

                await crawler._async_fetch("https://example.com", {"undetected": True})

                mock_adapter_cls.assert_called_once()
                mock_strategy_cls.assert_called_once()
                call_kwargs = mock_strategy_cls.call_args[1]
                assert call_kwargs["browser_adapter"] is mock_adapter


class TestMaxRetries:
    """Test 3: max_retries is passed to CrawlerRunConfig."""

    def test_max_retries_default(self):
        """When max_retries is not passed, default should be 0."""
        from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler

        crawler = Crawl4AICrawler()
        config = {}
        crawler_cfg = crawler._build_crawler_config(config)

        assert crawler_cfg.max_retries == 0

    def test_max_retries_custom(self):
        """When max_retries=3 is passed, it should be forwarded to CrawlerRunConfig."""
        from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler

        crawler = Crawl4AICrawler()
        config = {"max_retries": 3}
        crawler_cfg = crawler._build_crawler_config(config)

        assert crawler_cfg.max_retries == 3


class TestProxyConfig:
    """Test proxy_config support."""

    def test_proxy_config_none_when_not_provided(self):
        """When proxy is not provided, proxy_config should be None."""
        from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler

        crawler = Crawl4AICrawler()
        config = {}
        proxy_cfg = crawler._build_proxy_config(config)

        assert proxy_cfg is None

    def test_proxy_config_parsed(self):
        """When proxy is provided, ProxyConfig should be built."""
        from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler

        crawler = Crawl4AICrawler()
        config = {
            "proxy": {
                "server": "http://proxy.example.com:8080",
                "username": "user",
                "password": "pass",
            }
        }
        proxy_cfg = crawler._build_proxy_config(config)

        assert proxy_cfg is not None
        assert proxy_cfg.server == "http://proxy.example.com:8080"
        assert proxy_cfg.username == "user"
        assert proxy_cfg.password == "pass"

    def test_proxy_config_passed_to_crawler_config(self):
        """proxy_config should be passed to CrawlerRunConfig."""
        from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler

        crawler = Crawl4AICrawler()
        config = {
            "proxy": {
                "server": "http://proxy.example.com:8080",
                "username": "user",
                "password": "pass",
            }
        }
        crawler_cfg = crawler._build_crawler_config(config)

        assert crawler_cfg.proxy_config is not None
        assert crawler_cfg.proxy_config.server == "http://proxy.example.com:8080"