"""页面归档存储接口。"""

import os
from copy import deepcopy
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    create_engine,
    insert,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID


ARCHIVE_METADATA = MetaData()

ARCHIVE_PAGES = Table(
    "archive_pages",
    ARCHIVE_METADATA,
    Column(
        "id",
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sql_text("gen_random_uuid()"),
    ),
    Column("source_url", Text),
    Column("entry_url", Text),
    Column("final_url", Text),
    Column("domain", Text),
    Column("platform", Text),
    Column("subject", Text),
    Column("title", Text),
    Column("source_name", Text),
    Column("publish_time", DateTime(timezone=True)),
    Column("author", Text),
    Column("channel", Text),
    Column("breadcrumb", JSONB),
    Column("html", Text),
    Column("markdown", Text),
    Column("metadata", JSONB),
    Column("content_hash", Text),
    Column("archive_status", Text),
    Column("contains_ocr", Boolean),
    Column("contains_table", Boolean),
    Column("requires_structuring", Boolean),
    Column("manual_review_required", Boolean),
    Column("fetched_at", DateTime(timezone=True)),
)

ARCHIVE_BLOCKS = Table(
    "archive_blocks",
    ARCHIVE_METADATA,
    Column(
        "id",
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sql_text("gen_random_uuid()"),
    ),
    Column("page_id", UUID(as_uuid=False)),
    Column("block_order", Integer),
    Column("block_type", Text),
    Column("parent_block_id", UUID(as_uuid=False)),
    Column("text", Text),
    Column("html", Text),
    Column("metadata", JSONB),
)

ARCHIVE_ASSETS = Table(
    "archive_assets",
    ARCHIVE_METADATA,
    Column(
        "id",
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sql_text("gen_random_uuid()"),
    ),
    Column("page_id", UUID(as_uuid=False)),
    Column("block_id", UUID(as_uuid=False)),
    Column("asset_type", Text),
    Column("source_url", Text),
    Column("storage_uri", Text),
    Column("file_name", Text),
    Column("extension", Text),
    Column("mime_type", Text),
    Column("size_bytes", BigInteger),
    Column("content_hash", Text),
    Column("downloaded", Boolean),
    Column("metadata", JSONB),
)

OCR_RESULTS = Table(
    "ocr_results",
    ARCHIVE_METADATA,
    Column(
        "id",
        UUID(as_uuid=False),
        primary_key=True,
        server_default=sql_text("gen_random_uuid()"),
    ),
    Column("page_id", UUID(as_uuid=False)),
    Column("asset_id", UUID(as_uuid=False)),
    Column("block_id", UUID(as_uuid=False)),
    Column("engine", Text),
    Column("status", Text),
    Column("ocr_text", Text),
    Column("structured_data", JSONB),
    Column("elapsed_seconds", Numeric),
    Column("error", Text),
    Column("manual_review_required", Boolean),
)


class ArchiveStore:
    """页面归档存储的最小契约实现。"""

    def __init__(self, dsn, connection_factory=None):
        if not dsn:
            raise ValueError("archive store dsn is required")

        self.dsn = dsn
        self.connection_factory = connection_factory
        self._engine = None
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

    def _connect(self):
        """获取 PostgreSQL 连接；测试可注入伪连接。"""
        if self.connection_factory:
            return self.connection_factory()
        if self._engine is None:
            self._engine = create_engine(self.dsn)
        return self._engine.connect()

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
            "author": record.get("author"),
            "channel": record.get("channel"),
            "breadcrumb": deepcopy(record.get("breadcrumb", []) or []),
            "fetched_at": record.get("fetched_at"),
            "content_hash": record.get("content_hash"),
            "archive_status": record.get("archive_status") or "success",
            "html": record.get("html", ""),
            "markdown": record.get("markdown", ""),
            "metadata": metadata,
            "manual_review_required": bool(
                record.get("manual_review_required", False)
            ),
        }
        if record.get("id"):
            payload["id"] = record["id"]
        return payload

    @staticmethod
    def build_archive_page_payload(archive_page):
        """从归档对象构建 archive_pages payload。"""
        meta = deepcopy(archive_page.get("meta", {}) or {})
        content = deepcopy(archive_page.get("content", {}) or {})
        payload = ArchiveStore.build_page_payload(
            {
                **meta,
                "html": content.get("html", ""),
                "markdown": content.get("markdown", ""),
                "metadata": meta.get("metadata", {}),
            }
        )
        payload["contains_ocr"] = bool(meta.get("contains_ocr", False))
        payload["contains_table"] = bool(meta.get("contains_table", False))
        payload["requires_structuring"] = bool(
            meta.get("requires_structuring", False)
        )
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
            "engine": record.get("engine"),
            "status": record.get("status") or "success",
            "ocr_text": record.get("ocr_text") or "",
            "structured_data": deepcopy(record.get("structured_data", {}) or {}),
            "elapsed_seconds": record.get("elapsed_seconds"),
            "error": record.get("error"),
            "manual_review_required": bool(
                record.get("manual_review_required", False)
            ),
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

    def _insert_returning_id(self, connection, table, payload):
        """插入记录并返回数据库生成的 ID。"""
        statement = insert(table).values(**payload).returning(table.c.id)
        return connection.execute(statement).scalar_one()

    def save_archive_page(self, archive_page):
        """在一个事务内保存页面、块、资产和 OCR 结果。"""
        connection = self._connect()
        transaction = None
        block_id_map = {}
        asset_id_map = {}
        ocr_result_ids = []
        try:
            transaction = connection.begin()
            page_payload = self.build_archive_page_payload(archive_page)
            page_id = self._insert_returning_id(
                connection, ARCHIVE_PAGES, page_payload
            )

            for block in archive_page.get("blocks", []) or []:
                original_block_id = block.get("id")
                block_payload = self.build_block_payload(page_id, block)
                parent_block_id = block_payload.get("parent_block_id")
                if parent_block_id in block_id_map:
                    block_payload["parent_block_id"] = block_id_map[
                        parent_block_id
                    ]
                block_id = self._insert_returning_id(
                    connection, ARCHIVE_BLOCKS, block_payload
                )
                if original_block_id:
                    block_id_map[original_block_id] = block_id

            for asset in archive_page.get("assets", []) or []:
                original_asset_id = asset.get("id")
                asset_payload = self.build_asset_payload(page_id, asset)
                asset_payload.pop("id", None)
                block_id = asset_payload.get("block_id")
                if block_id in block_id_map:
                    asset_payload["block_id"] = block_id_map[block_id]
                asset_id = self._insert_returning_id(
                    connection, ARCHIVE_ASSETS, asset_payload
                )
                if original_asset_id:
                    asset_id_map[original_asset_id] = asset_id

            for ocr_result in archive_page.get("ocr_results", []) or []:
                ocr_payload = self.build_ocr_payload(page_id, ocr_result)
                ocr_payload.pop("id", None)
                asset_id = ocr_payload.get("asset_id")
                block_id = ocr_payload.get("block_id")
                if asset_id in asset_id_map:
                    ocr_payload["asset_id"] = asset_id_map[asset_id]
                if block_id in block_id_map:
                    ocr_payload["block_id"] = block_id_map[block_id]
                ocr_result_ids.append(
                    self._insert_returning_id(
                        connection, OCR_RESULTS, ocr_payload
                    )
                )

            transaction.commit()
            return {
                "page_id": page_id,
                "block_ids": block_id_map,
                "asset_ids": asset_id_map,
                "ocr_result_ids": ocr_result_ids,
                "counts": {
                    "pages": 1,
                    "blocks": len(block_id_map),
                    "assets": len(asset_id_map),
                    "ocr_results": len(ocr_result_ids),
                },
            }
        except Exception:
            if transaction:
                transaction.rollback()
            raise
        finally:
            close = getattr(connection, "close", None)
            if close:
                close()
