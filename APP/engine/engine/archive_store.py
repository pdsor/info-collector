"""页面归档存储接口。"""

import os
from copy import deepcopy
from uuid import uuid4


class ArchiveStore:
    """页面归档存储的最小契约实现。"""

    def __init__(self, dsn):
        if not dsn:
            raise ValueError("archive store dsn is required")

        self.dsn = dsn
        self.pages = []
        self.blocks = []
        self.assets = []

    @classmethod
    def from_env(cls):
        """优先从环境变量读取归档主库连接串。"""
        dsn = os.getenv("ARCHIVE_PG_DSN")
        if not dsn:
            raise ValueError("archive store dsn is required")
        return cls(dsn=dsn)

    @classmethod
    def from_rule(cls, rule):
        """从规则中补充归档主库连接串。"""
        rule = rule or {}
        dsn = os.getenv("ARCHIVE_PG_DSN")
        if not dsn:
            dsn = rule.get("archive_store", {}).get("dsn")
        if not dsn:
            raise ValueError("archive store dsn is required")
        return cls(dsn=dsn)

    @staticmethod
    def build_page_payload(page):
        """构建 archive_pages 写入 payload。"""
        record = deepcopy(page)
        metadata = deepcopy(record.pop("metadata", {}) or {})
        payload = {
            "source_url": record.get("source_url"),
            "entry_url": record.get("entry_url"),
            "final_url": record.get("final_url") or record.get("source_url"),
            "domain": record.get("domain"),
            "platform": record.get("platform"),
            "subject": record.get("subject"),
            "title": record.get("title"),
            "source_name": record.get("source_name"),
            "publish_time": record.get("publish_time"),
            "fetched_at": record.get("fetched_at"),
            "content_hash": record.get("content_hash"),
            "html": record.get("html", ""),
            "markdown": record.get("markdown", ""),
            "metadata": metadata,
        }
        if record.get("id"):
            payload["id"] = record["id"]
        return payload

    @staticmethod
    def build_block_payload(page_id, block):
        """构建 archive_blocks 写入 payload。"""
        record = deepcopy(block)
        payload = {
            "page_id": page_id,
            "block_order": record.get("block_order"),
            "block_type": record.get("block_type") or record.get("type"),
            "parent_block_id": record.get("parent_block_id"),
            "text": record.get("text", ""),
            "metadata": deepcopy(record.get("metadata", {}) or {}),
        }
        return payload

    @staticmethod
    def build_asset_payload(page_id, asset):
        """构建 archive_assets 写入 payload。"""
        record = deepcopy(asset)
        payload = {
            "page_id": page_id,
            "block_id": record.get("block_id"),
            "asset_type": record.get("asset_type"),
            "source_url": record.get("source_url"),
            "storage_uri": record.get("storage_uri"),
            "file_name": record.get("file_name"),
            "extension": record.get("extension"),
            "mime_type": record.get("mime_type"),
            "size_bytes": record.get("size_bytes"),
            "content_hash": record.get("content_hash"),
            "downloaded": record.get("downloaded"),
            "metadata": deepcopy(record.get("metadata", {}) or {}),
        }
        if record.get("id"):
            payload["id"] = record["id"]
        return payload

    @staticmethod
    def build_ocr_payload(page_id, ocr_result):
        """构建 ocr_results 写入 payload。"""
        record = deepcopy(ocr_result)
        payload = {
            "page_id": page_id,
            "asset_id": record.get("asset_id"),
            "block_id": record.get("block_id"),
            "ocr_text": record.get("ocr_text") or "",
            "structured_data": deepcopy(record.get("structured_data", {}) or {}),
        }
        if record.get("id"):
            payload["id"] = record["id"]
        return payload

    @staticmethod
    def build_structured_record_payload(page_id, structured_record):
        """构建 structured_records 写入 payload。"""
        record = deepcopy(structured_record)
        payload = {
            "page_id": page_id,
            "source_block_id": record.get("source_block_id"),
            "record_type": record.get("record_type"),
            "data": deepcopy(record.get("data", {}) or {}),
            "raw_columns": deepcopy(record.get("raw_columns", []) or []),
        }
        if record.get("id"):
            payload["id"] = record["id"]
        return payload

    def save_page(self, page):
        """保存页面归档记录并返回页面 ID。"""
        page_id = str(uuid4())
        record = self.build_page_payload(page)
        record["id"] = page_id
        self.pages.append(record)
        return page_id

    def save_block(self, page_id, block):
        """保存页面内容块并返回块 ID。"""
        block_id = str(uuid4())
        record = self.build_block_payload(page_id, block)
        record["id"] = block_id
        self.blocks.append(record)
        return block_id

    def save_asset(self, page_id, asset):
        """保存页面资产元数据并返回资产 ID。"""
        asset_id = str(uuid4())
        record = self.build_asset_payload(page_id, asset)
        record["id"] = asset_id
        self.assets.append(record)
        return asset_id
