"""Test Engine deduplicate method"""
import pytest
import tempfile
import os


class TestEngineDeduplicate:
    """Test engine deduplicate functionality directly"""

    def setup_method(self):
        """Setup test engine"""
        from engine.engine import InfoCollectorEngine

        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.temp_db.close()
        self.engine = InfoCollectorEngine(dedup_db_path=self.temp_db.name)

    def teardown_method(self):
        """Cleanup"""
        if hasattr(self, 'engine'):
            self.engine.dedup.close()
        if hasattr(self, 'temp_db'):
            os.unlink(self.temp_db.name)

    def test_deduplicate_returns_filtered_items(self):
        """Test deduplicate returns correct filtered count"""
        items = [
            {"raw_id": "id1", "url": "https://example.com/1"},
            {"raw_id": "id2", "url": "https://example.com/2"},
        ]

        rule = {
            "name": "test_rule",
            "dedup": {"incremental": True},
            "source": {"platform": "test_platform"}
        }

        # First call - nothing filtered
        filtered, count = self.engine.deduplicate(items, rule)
        assert count == 0
        assert len(filtered) == 2

    def test_deduplicate_filters_seen_items(self):
        """Test deduplicate filters already-seen items"""
        items = [
            {"raw_id": "id1", "url": "https://example.com/1"},
            {"raw_id": "id2", "url": "https://example.com/2"},
        ]

        rule = {
            "name": "test_rule",
            "dedup": {"incremental": True},
            "source": {"platform": "test_platform"}
        }

        # Add first item to dedup manually
        self.engine.dedup.add("test_rule", "test_platform", "id1", "https://example.com/1")

        # Now deduplicate - should filter out id1
        filtered, count = self.engine.deduplicate(items, rule)
        assert count == 1  # id1 was filtered
        assert len(filtered) == 1
        assert filtered[0]["raw_id"] == "id2"

    def test_deduplicate_disabled_returns_all(self):
        """Test deduplicate off returns all items"""
        items = [
            {"raw_id": "id1", "url": "https://example.com/1"},
            {"raw_id": "id2", "url": "https://example.com/2"},
        ]

        rule = {
            "name": "test_rule",
            "dedup": {"incremental": False},  # disabled
            "source": {"platform": "test_platform"}
        }

        filtered, count = self.engine.deduplicate(items, rule)
        assert count == 0
        assert len(filtered) == 2

    def test_deduplicate_empty_raw_id_not_filtered(self):
        """Test items with empty raw_id are NOT filtered (edge case)"""
        items = [
            {"raw_id": "", "url": "https://example.com/1"},  # empty raw_id
            {"raw_id": "id2", "url": "https://example.com/2"},
        ]

        rule = {
            "name": "test_rule",
            "dedup": {"incremental": True},
            "source": {"platform": "test_platform"}
        }

        # Empty raw_id check() always returns False (not in dedup)
        # So empty raw_id items always pass through
        filtered, count = self.engine.deduplicate(items, rule)
        assert count == 0  # Both pass because raw_id="" never matches
        assert len(filtered) == 2
