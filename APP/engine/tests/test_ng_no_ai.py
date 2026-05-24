"""NG v2.2 去 AI 化约束测试。"""

import pytest


def test_browser_client_defaults_to_playwright():
    """browser 客户端必须使用确定性的 Playwright 渲染器。"""
    from engine.crawl_browser import BrowserCrawler
    from engine.crawlers import PlaywrightCrawler

    crawler = BrowserCrawler(client="browser")

    assert crawler.client == "browser"
    assert isinstance(crawler._impl, PlaywrightCrawler)


def test_crawl4ai_client_is_rejected():
    """v2.2 不允许通过规则或客户端启用 Crawl4AI。"""
    from engine.crawl_browser import BrowserCrawler

    with pytest.raises(ValueError, match="Crawl4AI"):
        BrowserCrawler(client="crawl4ai")


def test_rule_parser_rejects_ai_extraction_config():
    """规则不得声明 LLM/语义提取配置。"""
    from engine.rule_parser import RuleParser

    parser = RuleParser()
    rule = {
        "name": "AI 提取规则",
        "source": {
            "type": "browser",
            "client": "browser",
            "extraction": {
                "enabled": True,
                "prompt": "Extract articles",
                "strategy": "llm",
            },
        },
        "list": {"items_path": "css:a", "fields": []},
    }

    with pytest.raises(ValueError, match="AI|LLM|source.extraction"):
        parser.validate(rule)


def test_rule_parser_rejects_crawl4ai_client_value():
    """规则 client 字段不能再选择 crawl4ai。"""
    from engine.rule_parser import RuleParser

    parser = RuleParser()
    rule = {
        "name": "Crawl4AI 规则",
        "source": {
            "type": "browser",
            "client": "crawl4ai",
        },
        "list": {"items_path": "css:a", "fields": []},
    }

    with pytest.raises(ValueError, match="crawl4ai|Crawl4AI"):
        parser.validate(rule)
