"""Tests for Crawl4AI field extraction methods."""
import pytest

from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler

SAMPLE_HTML = """
<html>
<body>
<article class="item">
    <h2 class="title">Product Name</h2>
    <a href="/product/1" class="link">View Details</a>
    <span class="price">$99.00</span>
</article>
</body>
</html>
"""


class TestCrawl4AIParsing:
    """Test cases for Crawl4AI parsing and field extraction methods."""

    def setup_method(self):
        """Set up crawler instance before each test."""
        self.crawler = Crawl4AICrawler()

    def test_parse_items_css_selector(self):
        """Test parse_items with CSS selector."""
        result = self.crawler.parse_items(SAMPLE_HTML, "article.item")
        assert len(result) == 1
        assert "<article class=\"item\">" in result[0]

    def test_parse_items_xpath(self):
        """Test parse_items with XPath expression."""
        result = self.crawler.parse_items(SAMPLE_HTML, "//article[@class='item']")
        assert len(result) == 1
        assert "<article class=\"item\">" in result[0]

    def test_extract_attr(self):
        """Test extract_attr for href attribute."""
        result = self.crawler.extract_attr(SAMPLE_HTML, "//a[@class='link']", "href")
        assert result == "/product/1"

    def test_extract_text(self):
        """Test extract_text for price span."""
        result = self.crawler.extract_text(SAMPLE_HTML, "//span[@class='price']")
        assert result == "$99.00"

    def test_extract_fields批量提取(self):
        """Test extract_fields with multiple field definitions."""
        field_defs = [
            {"name": "title", "xpath": "//h2[@class='title']"},
            {"name": "price", "xpath": "//span[@class='price']", "attr": None},
            {"name": "link", "xpath": "//a[@class='link']", "attr": "href"},
        ]
        result = self.crawler.extract_fields(SAMPLE_HTML, field_defs)
        assert result == {"title": "Product Name", "price": "$99.00", "link": "/product/1"}

    def test_extract_fields_empty_result(self):
        """Test extract_fields with non-existent XPath."""
        field_defs = [
            {"name": "nonexistent", "xpath": "//div[@class='notfound']"},
        ]
        result = self.crawler.extract_fields(SAMPLE_HTML, field_defs)
        assert result == {"nonexistent": ""}

    def test_extract_fields_missing_attr(self):
        """Test extract_fields when attr does not exist on element."""
        field_defs = [
            {"name": "title", "xpath": "//h2[@class='title']", "attr": "href"},
        ]
        result = self.crawler.extract_fields(SAMPLE_HTML, field_defs)
        assert result == {"title": ""}
