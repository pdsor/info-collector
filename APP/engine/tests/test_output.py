"""Test JSON output functionality"""
import pytest
import json
import tempfile
import os
from pathlib import Path


class TestOutputManager:
    """Test output management functionality"""

    def setup_method(self):
        """Setup test environment"""
        from engine.output import OutputManager
        
        self.temp_dir = tempfile.mkdtemp()
        self.output_mgr = OutputManager(base_path=self.temp_dir)

    def teardown_method(self):
        """Cleanup test files"""
        import shutil
        if hasattr(self, 'temp_dir'):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_json_output(self):
        """Test saving data as JSON"""
        items = [
            {"title": "Test 1", "url": "https://example.com/1"},
            {"title": "Test 2", "url": "https://example.com/2"},
        ]
        
        rule = {
            "name": "Test Rule",
            "output": {
                "format": "json",
                "filename_template": "test_{date}.json"
            }
        }
        
        output_path = self.output_mgr.save(items, rule)
        
        assert os.path.exists(output_path)
        
        with open(output_path, 'r') as f:
            data = json.load(f)
        
        assert "meta" in data
        assert "data" in data
        assert len(data["data"]) == 2

    def test_output_includes_meta(self):
        """Test that output includes metadata"""
        items = [{"title": "Test"}]
        
        rule = {
            "name": "Test Rule",
            "output": {
                "format": "json",
                "filename_template": "test_{date}.json"
            }
        }
        
        output_path = self.output_mgr.save(items, rule)
        
        with open(output_path, 'r') as f:
            data = json.load(f)
        
        assert "platform" in data["meta"]
        assert "collected_at" in data["meta"]
        assert "count" in data["meta"]

    def test_output_with_dedup_info(self):
        """Test output includes deduplication info"""
        items = [{"title": "Test"}]
        
        rule = {
            "name": "Test Rule",
            "output": {
                "format": "json",
                "filename_template": "test_{date}.json"
            }
        }
        
        output_path = self.output_mgr.save(items, rule, dedup_filtered=5)
        
        with open(output_path, 'r') as f:
            data = json.load(f)
        
        assert data["meta"]["dedup_filtered"] == 5

    def test_create_output_directory(self):
        """Test that output directory is created if not exists"""
        custom_path = os.path.join(self.temp_dir, "subdir", "output")
        
        items = [{"title": "Test"}]
        rule = {
            "name": "Test",
            "output": {
                "format": "json",
                "path": custom_path,
                "filename_template": "test_{date}.json"
            }
        }
        
        output_path = self.output_mgr.save(items, rule)
        
        assert os.path.exists(custom_path)
        assert os.path.exists(output_path)
