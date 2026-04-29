"""Test API crawler functionality"""
import pytest
from unittest.mock import Mock, patch


class TestAPICrawler:
    """Test API source crawling"""

    def test_build_request_params(self):
        """Test building request parameters from rule"""
        from engine.crawl_api import APICrawler
        
        crawler = APICrawler()
        rule = {
            "source": {
                "base_url": "https://api.example.com/search",
                "type": "api"
            },
            "request": {
                "method": "POST",
                "headers": {"Content-Type": "application/json"},
                "body_template": '{"keyword": "{keyword}"}',
                "params": {"keyword": "数据要素"}
            }
        }
        
        params = crawler.build_request_params(rule)
        
        assert params["method"] == "POST"
        assert "headers" in params
        assert "data" in params

    def test_execute_api_request(self):
        """Test executing API request"""
        from engine.crawl_api import APICrawler
        
        crawler = APICrawler()
        
        # Mock the requests call
        with patch('engine.crawl_api.requests.request') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "announcements": [
                    {"announcementId": "123", "announcementTitle": "Test"}
                ]
            }
            mock_request.return_value = mock_response
            
            result = crawler.fetch("https://api.example.com", "POST", data="{}")
            
            assert "announcements" in result

    def test_parse_api_response(self):
        """Test parsing API response using JSONPath"""
        from engine.crawl_api import APICrawler
        
        crawler = APICrawler()
        response_data = {
            "announcements": [
                {"announcementId": "123", "title": "Test 1"},
                {"announcementId": "456", "title": "Test 2"},
            ]
        }
        
        items = crawler.parse_items(response_data, "$.announcements[*]")
        
        assert len(items) == 2
        assert items[0]["announcementId"] == "123"

    def test_extract_fields_from_item(self):
        """Test extracting fields from parsed item"""
        from engine.crawl_api import APICrawler
        
        crawler = APICrawler()
        rule = {
            "list": {
                "fields": [
                    {"name": "title", "type": "field", "path": "$.announcementTitle"},
                    {"name": "platform", "type": "constant", "value": "cninfo"},
                ]
            }
        }
        
        item = {"announcementTitle": "Test Announcement", "announcementId": "123"}
        extracted = crawler.extract_fields(item, rule["list"]["fields"])
        
        assert extracted["title"] == "Test Announcement"
        assert extracted["platform"] == "cninfo"

    def test_transform_timestamp_to_iso(self):
        """Test timestamp to ISO format transformation"""
        from engine.crawl_api import APICrawler
        
        crawler = APICrawler()
        
        # Milliseconds timestamp
        result = crawler.transform_value(1704067200000, "timestamp_ms_to_iso")
        
        assert "2024" in result

    def test_transform_strip_html(self):
        """Test HTML stripping transformation"""
        from engine.crawl_api import APICrawler
        
        crawler = APICrawler()
        
        result = crawler.transform_value("<em>Test</em> <b>HTML</b>", "strip_html")
        
        assert "<em>" not in result
        assert "Test" in result
