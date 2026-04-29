"""Deduplicator - SQLite-based global deduplication"""
import sqlite3
from datetime import datetime


class Deduplicator:
    """SQLite-based global deduplication"""
    
    def __init__(self, db_path: str = "./dedup.db"):
        """Initialize deduplicator with database path"""
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self._init_db()
    
    def _init_db(self):
        """Create dedup table if not exists"""
        # PSEUDOCODE: Create table
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dedup (
                id TEXT PRIMARY KEY,
                requirement TEXT NOT NULL,
                platform TEXT NOT NULL,
                url TEXT,
                collected_at TEXT NOT NULL,
                raw_id TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_requirement ON dedup(requirement)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_platform ON dedup(platform)")
        self.conn.commit()
    
    def check(self, requirement: str, platform: str, raw_id: str) -> bool:
        """Check if item already exists in dedup"""
        # PSEUDOCODE: Query dedup table
        cursor = self.conn.cursor()
        dedup_id = f"{platform}_{raw_id}"
        cursor.execute("SELECT 1 FROM dedup WHERE id = ?", (dedup_id,))
        return cursor.fetchone() is not None
    
    def add(self, requirement: str, platform: str, raw_id: str, url: str = None):
        """Add item to dedup"""
        # PSEUDOCODE: Insert into dedup
        cursor = self.conn.cursor()
        dedup_id = f"{platform}_{raw_id}"
        collected_at = datetime.now().isoformat()
        cursor.execute(
            "INSERT OR IGNORE INTO dedup (id, requirement, platform, url, collected_at, raw_id) VALUES (?, ?, ?, ?, ?, ?)",
            (dedup_id, requirement, platform, url, collected_at, raw_id)
        )
        self.conn.commit()
    
    def filter_items(self, requirement: str, platform: str, items: list) -> list:
        """Filter out items that already exist"""
        # PSEUDOCODE: Check each item and return only new ones
        new_items = []
        for item in items:
            raw_id = item.get("raw_id", "")
            if not self.check(requirement, platform, raw_id):
                new_items.append(item)
        return new_items
    
    def get_stats(self, requirement: str = None) -> dict:
        """Get deduplication statistics"""
        cursor = self.conn.cursor()
        if requirement:
            cursor.execute("SELECT COUNT(*), platform FROM dedup WHERE requirement = ? GROUP BY platform", (requirement,))
        else:
            cursor.execute("SELECT COUNT(*), platform FROM dedup GROUP BY platform")
        
        rows = cursor.fetchall()
        total = sum(row[0] for row in rows)
        platforms = [row[1] for row in rows]
        
        return {"total": total, "platforms": platforms}
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()
