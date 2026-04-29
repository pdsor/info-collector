"""Test global deduplication with SQLite"""
import pytest
import tempfile
import os
from pathlib import Path


class TestDeduplicator:
    """Test deduplication functionality"""

    def setup_method(self):
        """Setup test database"""
        from engine.dedup import Deduplicator
        
        # Use temp file for isolation
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.dedup = Deduplicator(self.temp_db.name)

    def teardown_method(self):
        """Cleanup test database"""
        import os
        if hasattr(self, 'dedup'):
            self.dedup.close()
        if hasattr(self, 'temp_db'):
            os.unlink(self.temp_db.name)

    def test_init_creates_table(self):
        """Test that initialization creates dedup table"""
        import sqlite3
        
        conn = sqlite3.connect(self.temp_db.name)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='dedup'")
        result = cursor.fetchone()
        conn.close()
        
        assert result is not None, "dedup table should be created"

    def test_check_new_item_not_seen(self):
        """Test checking an item not in database"""
        result = self.dedup.check("test_rule", "cninfo", "item_123")
        assert result is False  # Not seen before

    def test_check_item_already_seen(self):
        """Test checking an item already in database"""
        # First add an item
        self.dedup.add("test_rule", "cninfo", "item_123", "https://example.com/123")
        
        # Check should return True (already seen)
        result = self.dedup.check("test_rule", "cninfo", "item_123")
        assert result is True

    def test_filter_duplicates(self):
        """Test filtering duplicate items from a list"""
        items = [
            {"raw_id": "item_1", "url": "https://example.com/1"},
            {"raw_id": "item_2", "url": "https://example.com/2"},
            {"raw_id": "item_3", "url": "https://example.com/3"},
        ]
        
        # Add first two to dedup
        self.dedup.add("test_rule", "cninfo", "item_1", "https://example.com/1")
        self.dedup.add("test_rule", "cninfo", "item_2", "https://example.com/2")
        
        # Filter
        filtered = self.dedup.filter_items("test_rule", "cninfo", items)
        
        assert len(filtered) == 1
        assert filtered[0]["raw_id"] == "item_3"

    def test_incremental_mode(self):
        """Test incremental deduplication"""
        rule = {
            "dedup": {
                "incremental": True,
                "id_template": "cninfo_{raw_id}"
            }
        }
        
        items = [
            {"raw_id": "item_1"},
            {"raw_id": "item_2"},
        ]
        
        # Add first item
        self.dedup.add("test_rule", "cninfo", "item_1", "https://example.com/1")
        
        # In incremental mode, only new items should pass
        filtered = self.dedup.filter_items("test_rule", "cninfo", items)
        assert len(filtered) == 1
        assert filtered[0]["raw_id"] == "item_2"

    def test_get_dedup_stats(self):
        """Test getting deduplication statistics"""
        self.dedup.add("test_rule", "cninfo", "item_1", "https://example.com/1")
        self.dedup.add("test_rule", "cninfo", "item_2", "https://example.com/2")
        
        stats = self.dedup.get_stats("test_rule")
        
        assert stats["total"] == 2
        assert stats["platforms"] == ["cninfo"]
