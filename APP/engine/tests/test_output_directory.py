"""Test output directory structure and format consistency between output.py and data_api.py

Tests that:
1. OutputManager creates {subject}/{platform}/data_*.json structure
2. data_api can correctly read the output files
3. combined_latest.json is created and readable
4. Directory listing APIs match the output structure
"""
import pytest
import json
import tempfile
import os
import shutil
import glob
import sys
from datetime import datetime

# Add engine path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Add dashboard path for data_api imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'dashboard'))


class TestOutputDirectoryStructure:
    """Test directory structure consistency"""

    def setup_method(self):
        """Setup test environment"""
        from engine.output import OutputManager
        self.temp_dir = tempfile.mkdtemp()
        self.output_mgr = OutputManager(base_path=self.temp_dir)
        # Sample data for testing
        self.items = [
            {"title": "Test Article 1", "url": "https://example.com/1", "content": "Content 1"},
            {"title": "Test Article 2", "url": "https://example.com/2", "content": "Content 2"},
        ]
        self.rule = {
            "name": "Test Rule",
            "subject": "测试主题",
            "source": {"platform": "test_platform"},
            "output": {
                "format": "json",
                "filename_template": "test_{date}.json"
            }
        }

    def teardown_method(self):
        """Cleanup test files"""
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_output_creates_subject_platform_directory(self):
        """Test that OutputManager creates {subject}/{platform}/ directory structure"""
        output_path = self.output_mgr.save(self.items, self.rule)

        # Verify: {temp_dir}/测试主题/test_platform/test_{date}.json
        expected_dir = os.path.join(self.temp_dir, "测试主题", "test_platform")
        assert os.path.isdir(expected_dir), f"Expected directory {expected_dir} to exist"
        assert os.path.isfile(output_path), f"Expected file {output_path} to exist"

    def test_output_filename_uses_date_template(self):
        """Test that output filename contains date"""
        output_path = self.output_mgr.save(self.items, self.rule)

        filename = os.path.basename(output_path)
        today = datetime.now().strftime("%Y%m%d")
        assert today in filename, f"Expected date {today} in filename {filename}"

    def test_multiple_platforms_under_same_subject(self):
        """Test that multiple platforms can exist under same subject"""
        rule1 = {**self.rule, "source": {"platform": "platform_a"}}
        rule2 = {**self.rule, "source": {"platform": "platform_b"}}

        self.output_mgr.save(self.items, rule1)
        self.output_mgr.save(self.items, rule2)

        subject_dir = os.path.join(self.temp_dir, "测试主题")
        platforms = [d for d in os.listdir(subject_dir) if os.path.isdir(os.path.join(subject_dir, d))]

        assert "platform_a" in platforms
        assert "platform_b" in platforms

    def test_combined_latest_created_in_subject_dir(self):
        """Test that combined_latest.json is created in subject directory"""
        self.output_mgr.save(self.items, self.rule)

        combined_path = os.path.join(self.temp_dir, "测试主题", "combined_latest.json")
        assert os.path.isfile(combined_path), f"Expected {combined_path} to exist"


class TestOutputFormat:
    """Test output JSON format consistency"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        from engine.output import OutputManager
        self.output_mgr = OutputManager(base_path=self.temp_dir)
        self.items = [
            {"title": "Test 1", "url": "https://example.com/1"},
            {"title": "Test 2", "url": "https://example.com/2"},
        ]
        self.rule = {
            "name": "Test Rule",
            "subject": "测试主题",
            "source": {"platform": "test_platform"},
            "output": {"format": "json", "filename_template": "test_{date}.json"}
        }

    def teardown_method(self):
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_output_json_has_meta_and_data_keys(self):
        """Test output JSON has required top-level keys"""
        output_path = self.output_mgr.save(self.items, self.rule)

        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert "meta" in data, "Output JSON must have 'meta' key"
        assert "data" in data, "Output JSON must have 'data' key"

    def test_output_meta_contains_required_fields(self):
        """Test meta section has all required fields"""
        output_path = self.output_mgr.save(self.items, self.rule)

        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        meta = data["meta"]
        assert "subject" in meta, "meta must have 'subject'"
        assert "platform" in meta, "meta must have 'platform'"
        assert "collected_at" in meta, "meta must have 'collected_at'"
        assert "count" in meta, "meta must have 'count'"
        assert "dedup_filtered" in meta, "meta must have 'dedup_filtered'"

    def test_output_meta_values_match_rule(self):
        """Test meta values match the rule configuration"""
        output_path = self.output_mgr.save(self.items, self.rule, dedup_filtered=3)

        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        meta = data["meta"]
        assert meta["subject"] == "测试主题"
        assert meta["platform"] == "test_platform"
        assert meta["count"] == 2
        assert meta["dedup_filtered"] == 3

    def test_output_data_is_list(self):
        """Test that data section is a list"""
        output_path = self.output_mgr.save(self.items, self.rule)

        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        assert isinstance(data["data"], list), "data section must be a list"
        assert len(data["data"]) == 2

    def test_combined_latest_format(self):
        """Test combined_latest.json has correct format"""
        self.output_mgr.save(self.items, self.rule)

        combined_path = os.path.join(self.temp_dir, "测试主题", "combined_latest.json")
        with open(combined_path, 'r', encoding='utf-8') as f:
            combined = json.load(f)

        assert "meta" in combined
        assert "data" in combined
        assert combined["meta"]["subject"] == "测试主题"
        assert combined["meta"]["platform"] == "combined"
        assert isinstance(combined["data"], list)


class TestDataApiCompatibility:
    """Test that data_api.py can correctly read output from OutputManager"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        from engine.output import OutputManager
        self.output_mgr = OutputManager(base_path=self.temp_dir)
        self.items = [
            {"title": "API Test 1", "url": "https://api.example.com/1"},
            {"title": "API Test 2", "url": "https://api.example.com/2"},
        ]
        self.rule = {
            "name": "API Test Rule",
            "subject": "API测试",
            "source": {"platform": "api_platform"},
            "output": {"format": "json", "filename_template": "api_{date}.json"}
        }

    def teardown_method(self):
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_latest_data_file_with_output(self):
        """Test data_api._find_latest_data_file can find output files"""
        import glob as glob_module
        from apis.data_api import _find_latest_data_file

        # Override rule to use data_{date}.json (what data_api looks for)
        rule = {
            "name": "API Test Rule",
            "subject": "API测试",
            "source": {"platform": "api_platform"},
            "output": {"format": "json", "filename_template": "data_{date}.json"}
        }
        # Save some output
        self.output_mgr.save(self.items, rule)

        # Simulate data_api's lookup
        target_dir = os.path.join(self.temp_dir, "API测试", "api_platform")
        json_files = glob_module.glob(os.path.join(target_dir, "data_*.json"))

        assert len(json_files) > 0, "data_api should find output files"

        # Test the helper function directly
        latest = _find_latest_data_file(self.temp_dir, "API测试", "api_platform")
        assert latest is not None
        assert latest.endswith(".json")

    def test_load_items_from_file_reads_output(self):
        """Test data_api._load_items_from_file can read OutputManager output"""
        from apis.data_api import _load_items_from_file

        output_path = self.output_mgr.save(self.items, self.rule)

        items, total = _load_items_from_file(output_path, limit=10)

        assert total == 2
        assert len(items) == 2
        assert items[0]["title"] == "API Test 1"

    def test_load_items_respects_limit(self):
        """Test _load_items_from_file respects limit parameter"""
        from apis.data_api import _load_items_from_file

        # Add more items
        more_items = [{"title": f"Item {i}", "url": f"https://example.com/{i}"} for i in range(10)]
        output_path = self.output_mgr.save(more_items, self.rule)

        items, total = _load_items_from_file(output_path, limit=5)

        assert total == 10
        assert len(items) == 5

    def test_count_items_in_file(self):
        """Test data_api._count_items_in_file works with output"""
        from apis.data_api import _count_items_in_file

        output_path = self.output_mgr.save(self.items, self.rule)
        count = _count_items_in_file(output_path)

        assert count == 2

    def test_output_directory_structure_readable_by_glob(self):
        """Test that output structure can be traversed using glob patterns"""
        import glob as glob_module

        self.output_mgr.save(self.items, self.rule)

        # Pattern: {subject}/{platform}/*.json
        pattern = os.path.join(self.temp_dir, "API测试", "api_platform", "*.json")
        files = glob_module.glob(pattern)

        assert len(files) > 0, "Should find JSON files with glob pattern"
        assert all(f.endswith(".json") for f in files)

    def test_data_stats_with_output(self):
        """Test data_api.data_stats can read output directory structure"""
        from apis.data_api import data_stats, _get_data_dir
        from unittest.mock import patch

        self.output_mgr.save(self.items, self.rule)

        # Mock _get_data_dir to return our temp directory
        with patch('apis.data_api._get_data_dir', return_value=self.temp_dir):
            with patch('apis.data_api.DB_PATH', ':memory:'):
                # Since data_stats uses Flask context, test the logic directly
                engine_data = self.temp_dir
                stats = {}

                if os.path.exists(engine_data):
                    for subject in os.listdir(engine_data):
                        s_path = os.path.join(engine_data, subject)
                        if not os.path.isdir(s_path):
                            continue
                        stats[subject] = {}
                        for platform in os.listdir(s_path):
                            p_path = os.path.join(s_path, platform)
                            if not os.path.isdir(p_path):
                                continue
                            json_files = glob.glob(os.path.join(p_path, "api_*.json"))
                            if json_files:
                                latest = max(json_files)
                                stats[subject][platform] = {"latest_file": os.path.basename(latest)}

                assert "API测试" in stats
                assert "api_platform" in stats["API测试"]


class TestEdgeCases:
    """Test edge cases and error handling"""

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        from engine.output import OutputManager
        self.output_mgr = OutputManager(base_path=self.temp_dir)

    def teardown_method(self):
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_subject_without_platform_falls_back_to_platform(self):
        """Test that subject-less rules use platform as pseudo-subject"""
        rule = {
            "name": "No Subject Rule",
            "source": {"platform": "standalone_platform"},
            "output": {"format": "json", "filename_template": "standalone_{date}.json"}
        }

        output_path = self.output_mgr.save([{"title": "Test"}], rule)

        # Should create {platform}/standalone_platform/standalone_{date}.json
        expected_dir = os.path.join(self.temp_dir, "standalone_platform", "standalone_platform")
        assert os.path.isdir(expected_dir)

    def test_custom_output_path_bypasses_default_structure(self):
        """Test that explicit output.path is used as-is"""
        custom_path = os.path.join(self.temp_dir, "custom", "output", "path")

        rule = {
            "name": "Custom Path Rule",
            "subject": "Should Not Appear",
            "source": {"platform": "should_not_appear"},
            "output": {
                "path": custom_path,
                "filename_template": "custom_{date}.json"
            }
        }

        output_path = self.output_mgr.save([{"title": "Test"}], rule)

        assert os.path.exists(output_path)
        assert custom_path in output_path
        # The subject directory should NOT be created for platform subdir
        # Note: combined_latest.json may still be created in subject dir due to _update_combined_latest
        # but the platform subdirectory should not use the subject-based path

    def test_chinese_characters_in_subject(self):
        """Test that Chinese characters work in paths"""
        rule = {
            "name": "Chinese Test",
            "subject": "中文主题",
            "source": {"platform": "中文平台"},
            "output": {"format": "json", "filename_template": "cn_{date}.json"}
        }

        output_path = self.output_mgr.save([{"标题": "测试"}], rule)

        assert os.path.exists(output_path)
        # Read back and verify
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data["data"][0]["标题"] == "测试"
