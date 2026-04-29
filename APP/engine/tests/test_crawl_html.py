"""Test HTML crawler functionality"""
import pytest
from unittest.mock import Mock, patch


class TestHTMLCrawler:
    """Test HTML source crawling"""

    def test_fetch_html_page(self):
        """Test fetching HTML page"""
        from engine.crawl_html import HTMLCrawler
        
        crawler = HTMLCrawler()
        
        with patch('engine.crawl_html.requests.get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "<html><body><a href='/article/1'>Test</a></body></html>"
            mock_response.encoding = 'utf-8'
            mock_get.return_value = mock_response
            
            html = crawler.fetch("https://example.com")
            
            assert "<html>" in html
            assert mock_get.called

    def test_parse_html_with_xpath(self):
        """Test parsing HTML using XPath"""
        from engine.crawl_html import HTMLCrawler
        
        crawler = HTMLCrawler()
        html = """
        <html>
            <body>
                <a class="type-post" href="/article/1">Test Article 1</a>
                <a class="type-post" href="/article/2">Test Article 2</a>
            </body>
        </html>
        """
        
        items = crawler.parse_items(html, "//a[contains(@class, 'type-post')]")
        
        assert len(items) == 2

    def test_extract_attr_from_element(self):
        """Test extracting attribute from HTML element"""
        from engine.crawl_html import HTMLCrawler
        
        crawler = HTMLCrawler()
        html = '<a href="https://example.com/article/1" class="test">Link</a>'
        
        href = crawler.extract_attr(html, "//a[@class='test']", "href")
        
        assert href == "https://example.com/article/1"

    def test_extract_text_from_element(self):
        """Test extracting text from HTML element"""
        from engine.crawl_html import HTMLCrawler
        
        crawler = HTMLCrawler()
        html = '<h1 class="title">Article Title</h1>'
        
        text = crawler.extract_text(html, "//h1[@class='title']")
        
        assert text == "Article Title"

    def test_extract_fields_from_html(self):
        """Test extracting fields from HTML item"""
        from engine.crawl_html import HTMLCrawler
        
        crawler = HTMLCrawler()
        html = """
        <html>
            <body>
                <h1 class="article-title">Test Title</h1>
                <span class="time">2024-01-01</span>
            </body>
        </html>
        """
        
        rule = {
            "detail": {
                "fields": [
                    {"name": "title", "type": "xpath", "path": "//h1[@class='article-title']//text()"},
                    {"name": "publish_time", "type": "xpath", "path": "//span[@class='time']//text()"},
                ]
            }
        }
        
        fields = crawler.extract_fields(html, rule["detail"]["fields"])
        
        assert fields["title"] == "Test Title"
        assert fields["publish_time"] == "2024-01-01"
