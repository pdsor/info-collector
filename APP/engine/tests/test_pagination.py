"""Tests for pagination logic in APICrawler"""
import pytest
import yaml
from unittest.mock import patch


class TestPagination:
    """Test pagination functionality"""

    def test_api_crawler_fetches_multiple_pages(self):
        """分页配置应触发多次请求并合并结果"""
        from engine.crawl_api import APICrawler

        rule = yaml.safe_load("""
name: Test Pagination
source:
  base_url: https://httpbin.org/post
request:
  method: POST
  body_template: page={page}
pagination:
  enabled: true
  page_param: page
  max_pages: 3
list:
  items_path: $.data
  fields:
    - name: value
      type: field
      path: $.value
""")

        crawler = APICrawler()

        call_count = [0]

        def fake_fetch(url, method, **kwargs):
            call_count[0] += 1
            data_str = kwargs.get("data", "")
            page_num = data_str.split("=")[-1] if "=" in data_str else "1"
            return {"data": [f"item_p{page_num}_1", f"item_p{page_num}_2"]}

        with patch.object(crawler, 'fetch', side_effect=fake_fetch):
            results = crawler.fetch_with_pagination(rule)
            assert call_count[0] == 3, f"应请求3页，实际请求了 {call_count[0]} 次"
            assert len(results) == 6, f"应有6条结果，实际 {len(results)} 条"

    def test_pagination_disabled_returns_single_page(self):
        """分页禁用时应只请求一次"""
        from engine.crawl_api import APICrawler

        rule = yaml.safe_load("""
name: Test Single Page
source:
  base_url: https://httpbin.org/get
request:
  method: GET
pagination:
  enabled: false
list:
  items_path: $.data
  fields:
    - name: value
      type: field
      path: $.value
""")

        crawler = APICrawler()
        fake_response = {"data": [{"value": "item1"}, {"value": "item2"}]}

        with patch.object(crawler, 'fetch', return_value=fake_response):
            results = crawler.fetch_with_pagination(rule)
            assert len(results) == 2

    def test_pagination_stops_on_empty_page(self):
        """当页面返回空时应停止分页"""
        from engine.crawl_api import APICrawler

        rule = yaml.safe_load("""
name: Test Early Stop
source:
  base_url: https://httpbin.org/post
request:
  method: POST
  body_template: page={page}
pagination:
  enabled: true
  page_param: page
  max_pages: 5
list:
  items_path: $.data
  fields:
    - name: value
      type: field
      path: $.value
""")

        crawler = APICrawler()
        call_count = [0]

        def fake_fetch(url, method, **kwargs):
            call_count[0] += 1
            data_str = kwargs.get("data", "")
            page_num = int(data_str.split("=")[-1]) if "=" in data_str else 1
            if page_num >= 3:
                return {"data": []}  # Empty page - should stop
            return {"data": [f"item_p{page_num}_1"]}

        with patch.object(crawler, 'fetch', side_effect=fake_fetch):
            results = crawler.fetch_with_pagination(rule)
            assert call_count[0] == 3, f"应在第3页（空页）停止，实际请求了 {call_count[0]} 次"
            assert len(results) == 2

    def test_pagination_with_page_param_replacement(self):
        """测试分页参数正确替换"""
        from engine.crawl_api import APICrawler

        rule = yaml.safe_load("""
name: Test Page Param
source:
  base_url: https://httpbin.org/post
request:
  method: POST
  body_template: category=tech&page={page}&size=10
pagination:
  enabled: true
  page_param: page
  max_pages: 2
list:
  items_path: $.data
  fields:
    - name: value
      type: field
      path: $.value
""")

        crawler = APICrawler()
        captured_bodies = []

        def fake_fetch(url, method, **kwargs):
            captured_bodies.append(kwargs.get("data", ""))
            return {"data": [{"value": "item"}]}

        with patch.object(crawler, 'fetch', side_effect=fake_fetch):
            results = crawler.fetch_with_pagination(rule)

        assert "page=1" in captured_bodies[0]
        assert "page=2" in captured_bodies[1]
        assert "category=tech" in captured_bodies[0]
        assert "size=10" in captured_bodies[0]
