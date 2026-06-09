"""完整引擎管线集成测试。"""
import pytest
import tempfile
import os
from unittest.mock import Mock, patch


NDA_RULE_PATH = "rules/数据要素/nda_gov_data_element_cases.yaml"


class TestEngineIntegration:
    """测试完整引擎管线。"""

    def setup_method(self):
        """Setup test engine"""
        from engine.engine import InfoCollectorEngine

        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.temp_output = tempfile.mkdtemp()
        self.engine = InfoCollectorEngine(dedup_db_path=self.temp_db.name)

    def teardown_method(self):
        """Cleanup"""
        if hasattr(self, 'engine'):
            self.engine.dedup.close()
        if hasattr(self, 'temp_db'):
            os.unlink(self.temp_db.name)
        import shutil
        if hasattr(self, 'temp_output'):
            shutil.rmtree(self.temp_output, ignore_errors=True)

    def test_load_rule_from_file(self):
        """应加载当前唯一 NDA 规则文件。"""
        rule = self.engine.load_rule(NDA_RULE_PATH)
        assert rule["name"] == "国家数据局 - 数据要素×典型案例"
        assert rule["source"]["type"] == "html"
        assert rule["source"]["platform"] == "nda_gov"

    def test_load_rule_validates_required_fields(self):
        """load_rule 应校验必填字段。"""
        from pathlib import Path
        import yaml

        temp_dir = tempfile.mkdtemp()
        bad_rule_path = os.path.join(temp_dir, "bad_rule.yaml")
        with open(bad_rule_path, 'w') as f:
            yaml.dump({"name": "Only name"}, f)

        with pytest.raises(ValueError, match="Missing required field"):
            self.engine.load_rule(bad_rule_path)

        os.unlink(bad_rule_path)
        os.rmdir(temp_dir)

    def test_engine_crawl_html_integration(self):
        """应使用当前 NDA 规则跑通 HTML 管线。"""
        rule = self.engine.load_rule(NDA_RULE_PATH)
        rule["list"]["pagination"] = {"type": "url_template", "url_template": rule["source"]["url"], "start_page": 1, "max_pages": 1}

        fake_html = '''
        <html><body>
        <ul>
          <li>
            <a href="/sjj/zhuanti/ztsjysx/sjysal/202601010101010001_pc.html">测试案例标题</a>
            <span>2026-01-01</span>
          </li>
        </ul>
        </body></html>
        '''

        with patch.object(self.engine.html_crawler, 'fetch', return_value=fake_html):
            items = self.engine.crawl(rule)

            assert len(items) == 1
            assert items[0]["title"] == "测试案例标题"
            assert items[0]["url"] == "https://www.nda.gov.cn/sjj/zhuanti/ztsjysx/sjysal/202601010101010001_pc.html"
            assert items[0]["raw_id"] == "202601010101010001"

    def test_engine_crawl_api_integration(self):
        """API 管线使用临时 fixture 验证，不依赖已删除旧规则。"""
        rule = {
            "name": "临时 API 集成测试规则",
            "subject": "测试",
            "source": {"platform": "fixture_api", "type": "api"},
            "request": {"method": "GET"},
            "list": {
                "items_path": "$.announcements[*]",
                "fields": [
                    {"name": "title", "type": "field", "path": "$.announcementTitle"},
                    {"name": "company", "type": "field", "path": "$.secName"},
                    {"name": "raw_id", "type": "field", "path": "$.announcementId"},
                ],
            },
            "dedup": {"incremental": True},
        }

        rule["pagination"] = {"enabled": False}

        fake_response = {
            "announcements": [
                {
                    "announcementId": "test123",
                    "announcementTitle": "测试公告",
                    "announcementTime": 1714567890000,
                    "secName": "测试公司",
                    "orgId": "org001"
                }
            ]
        }

        with patch.object(self.engine.api_crawler, 'fetch', return_value=fake_response):
            items = self.engine.crawl(rule)

            assert len(items) == 1
            assert items[0]["title"] == "测试公告"
            assert items[0]["company"] == "测试公司"

    def test_save_output_creates_json_file(self):
        """Test that save_output actually writes a file"""
        items = [
            {"title": "Test", "url": "https://example.com/1", "raw_id": "id1"},
            {"title": "Test2", "url": "https://example.com/2", "raw_id": "id2"},
        ]

        rule = {
            "name": "Test Rule",
            "subject": "测试事项",
            "source": {"platform": "test_platform", "type": "api"},
            "output": {
                "format": "json",
                "path": self.temp_output,
                "filename_template": "test_output_{date}.json"
            }
        }

        output_path = self.engine.save_output(items, rule)

        assert os.path.exists(output_path)
        assert output_path.endswith(".json")

    def test_full_pipeline_with_mock(self):
        """Test complete run() pipeline with mocked network calls"""
        import yaml
        import json

        # Create a temp rule file
        temp_dir = tempfile.mkdtemp()
        rule_path = os.path.join(temp_dir, "test_rule.yaml")
        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(output_dir)

        rule = {
            "name": "集成测试规则",
            "subject": "测试",
            "source": {
                "platform": "test_platform",
                "type": "api",
            },
            "request": {
                "method": "GET"
            },
            "list": {
                "items_path": "$.data[*]",
                "fields": [
                    {"name": "title", "type": "field", "path": "$.title"},
                    {"name": "url", "type": "field", "path": "$.url"},
                    {"name": "raw_id", "type": "field", "path": "$.id"}
                ]
            },
            "dedup": {"incremental": True},
            "output": {
                "format": "json",
                "path": output_dir,
                "filename_template": "test_{date}.json"
            }
        }

        with open(rule_path, 'w') as f:
            yaml.dump(rule, f)

        fake_data = {
            "data": [
                {"id": "p1", "title": "项目1", "url": "https://example.com/1"},
                {"id": "p2", "title": "项目2", "url": "https://example.com/2"},
            ]
        }

        class _CollectionStore:
            def save_run_items(self, **kwargs):
                return {
                    "run_id": "run-uuid-1",
                    "item_ids": [f"item-{idx}" for idx, _ in enumerate(kwargs.get("items", []), start=1)],
                    "governance_record_id": "gov-uuid-1",
                }

        with patch.object(self.engine.api_crawler, 'fetch', return_value=fake_data), \
             patch("engine.engine.CollectionStore.from_project_config", classmethod(lambda cls: _CollectionStore())):
            result = self.engine.run(rule_path)

            assert result["status"] == "success"
            assert result["collected"] == 2
            assert result["dedup_filtered"] == 0
            assert os.path.exists(result["output_path"])
            assert result["collection_run_id"] == "run-uuid-1"

        os.unlink(rule_path)
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
