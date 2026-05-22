"""页面归档存储测试。"""

import os
from pathlib import Path

import pytest


def test_archive_store_persists_page_block_and_asset():
    """归档存储应能保存页面、块和资产元数据。"""
    from engine.archive_store import ArchiveStore

    store = ArchiveStore(dsn="postgresql://test/test")

    page_id = store.save_page(
        {
            "source_url": "https://www.hubei.gov.cn/a.shtml",
            "entry_url": "https://www.hubei.gov.cn/list.shtml",
            "domain": "www.hubei.gov.cn",
            "platform": "hubei_gov",
            "subject": "数据要素",
            "title": "第三批湖北省高质量数据集名单",
            "fetched_at": "2026-05-21T15:30:00+08:00",
            "content_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "html": "<html><body><h1>第三批湖北省高质量数据集名单</h1></body></html>",
            "markdown": "# 第三批湖北省高质量数据集名单",
            "metadata": {"source_name": "湖北省数据局"},
        }
    )
    block_id = store.save_block(
        page_id,
        {
            "block_order": 1,
            "block_type": "heading",
            "text": "第三批湖北省高质量数据集名单",
            "metadata": {},
        },
    )
    asset_id = store.save_asset(
        page_id,
        {
            "block_id": block_id,
            "asset_type": "image",
            "source_url": "https://www.hubei.gov.cn/img.png",
            "storage_uri": "/tmp/scraper_imgs/x.png",
            "file_name": "x.png",
            "extension": ".png",
            "mime_type": "image/png",
            "size_bytes": 12345,
            "content_hash": "abc",
            "downloaded": True,
            "metadata": {},
        },
    )

    assert page_id
    assert block_id
    assert asset_id
    assert store.pages[0]["id"] == page_id
    assert store.blocks[0]["page_id"] == page_id
    assert store.assets[0]["block_id"] == block_id


def test_archive_store_rejects_empty_dsn():
    """缺少连接串时归档存储应明确报错。"""
    from engine.archive_store import ArchiveStore

    with pytest.raises(ValueError, match="dsn"):
        ArchiveStore(dsn="")


def test_archive_store_from_env_reads_archive_pg_dsn(monkeypatch):
    """应优先从环境变量读取 PostgreSQL 连接串。"""
    from engine.archive_store import ArchiveStore

    monkeypatch.setenv("ARCHIVE_PG_DSN", "postgresql://env/test")

    store = ArchiveStore.from_env()

    assert store.dsn == "postgresql://env/test"


def test_archive_store_from_rule_falls_back_to_rule_dsn():
    """规则中的 archive_store.dsn 应作为后备来源。"""
    from engine.archive_store import ArchiveStore

    store = ArchiveStore.from_rule({"archive_store": {"dsn": "postgresql://rule/test"}})

    assert store.dsn == "postgresql://rule/test"


def test_build_page_payload_includes_page_fields_and_metadata():
    """页面 payload 应包含主记录字段和 metadata。"""
    from engine.archive_store import ArchiveStore

    payload = ArchiveStore.build_page_payload(
        {
            "source_url": "https://www.hubei.gov.cn/a.shtml",
            "entry_url": "https://www.hubei.gov.cn/list.shtml",
            "final_url": "https://www.hubei.gov.cn/final.shtml",
            "domain": "www.hubei.gov.cn",
            "platform": "hubei_gov",
            "subject": "数据要素",
            "title": "第三批湖北省高质量数据集名单",
            "source_name": "湖北省数据局",
            "publish_time": "2026-05-21T15:30:00+08:00",
            "fetched_at": "2026-05-21T15:31:00+08:00",
            "content_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            "html": "<html></html>",
            "markdown": "# 第三批湖北省高质量数据集名单",
            "metadata": {"source_name": "湖北省数据局"},
        }
    )

    assert payload["source_url"] == "https://www.hubei.gov.cn/a.shtml"
    assert payload["entry_url"] == "https://www.hubei.gov.cn/list.shtml"
    assert payload["final_url"] == "https://www.hubei.gov.cn/final.shtml"
    assert payload["domain"] == "www.hubei.gov.cn"
    assert payload["platform"] == "hubei_gov"
    assert payload["subject"] == "数据要素"
    assert payload["title"] == "第三批湖北省高质量数据集名单"
    assert payload["metadata"] == {"source_name": "湖北省数据局"}


def test_build_block_payload_includes_block_relationship_fields():
    """页面块 payload 应包含块层级关键字段。"""
    from engine.archive_store import ArchiveStore

    payload = ArchiveStore.build_block_payload(
        "page-1",
        {
            "block_order": 2,
            "block_type": "paragraph",
            "parent_block_id": "block-1",
            "text": "正文",
            "metadata": {"foo": "bar"},
        },
    )

    assert payload["page_id"] == "page-1"
    assert payload["block_order"] == 2
    assert payload["block_type"] == "paragraph"
    assert payload["parent_block_id"] == "block-1"


def test_build_asset_payload_includes_asset_and_metadata_fields():
    """资产 payload 应包含定位与存储字段。"""
    from engine.archive_store import ArchiveStore

    payload = ArchiveStore.build_asset_payload(
        "page-1",
        {
            "block_id": "block-1",
            "asset_type": "image",
            "source_url": "https://www.hubei.gov.cn/img.png",
            "storage_uri": "/tmp/scraper_imgs/x.png",
            "metadata": {"alt": "名单图片"},
        },
    )

    assert payload["page_id"] == "page-1"
    assert payload["block_id"] == "block-1"
    assert payload["asset_type"] == "image"
    assert payload["storage_uri"] == "/tmp/scraper_imgs/x.png"
    assert payload["metadata"] == {"alt": "名单图片"}


def test_build_ocr_payload_includes_text_and_structured_data():
    """OCR payload 应保留文本和结构化结果。"""
    from engine.archive_store import ArchiveStore

    payload = ArchiveStore.build_ocr_payload(
        "page-1",
        {
            "asset_id": "asset-1",
            "block_id": "block-ocr-1",
            "ocr_text": "高质量数据集名单",
            "structured_data": {"rows": []},
        },
    )

    assert payload["page_id"] == "page-1"
    assert payload["asset_id"] == "asset-1"
    assert payload["block_id"] == "block-ocr-1"
    assert payload["ocr_text"] == "高质量数据集名单"
    assert payload["structured_data"] == {"rows": []}


def test_build_structured_record_payload_includes_record_fields():
    """结构化记录 payload 应包含来源块、记录类型和原始列。"""
    from engine.archive_store import ArchiveStore

    payload = ArchiveStore.build_structured_record_payload(
        "page-1",
        {
            "source_block_id": "block-1",
            "record_type": "table_row",
            "data": {"id": "1", "name": "企业登记数据集"},
            "raw_columns": ["1", "企业登记数据集"],
        },
    )

    assert payload["page_id"] == "page-1"
    assert payload["source_block_id"] == "block-1"
    assert payload["record_type"] == "table_row"
    assert payload["data"] == {"id": "1", "name": "企业登记数据集"}
    assert payload["raw_columns"] == ["1", "企业登记数据集"]


def test_archive_postgres_migration_defines_page_archive_schema():
    """PostgreSQL 迁移应定义页面归档主库表结构。"""
    repo_root = Path(__file__).resolve().parents[3]
    sql_path = repo_root / "migrations" / "20260521_archive_postgres.sql"
    sql = sql_path.read_text(encoding="utf-8").lower()

    for table_name in [
        "archive_pages",
        "archive_blocks",
        "archive_assets",
        "ocr_results",
        "structured_records",
    ]:
        assert f"create table if not exists {table_name}" in sql

    expected_fields = [
        "source_url text",
        "domain text",
        "title text",
        "fetched_at timestamp with time zone",
        "content_hash text",
        "page_id uuid",
        "block_order integer",
        "block_type text",
        "asset_type text",
        "storage_uri text",
        "mime_type text",
        "size_bytes bigint",
        "asset_id uuid",
        "block_id uuid",
        "ocr_text text",
        "source_block_id uuid",
        "record_type text",
    ]
    for field_definition in expected_fields:
        assert field_definition in sql

    for jsonb_field in [
        "breadcrumb jsonb",
        "metadata jsonb",
        "structured_data jsonb",
        "data jsonb",
        "raw_columns jsonb",
    ]:
        assert jsonb_field in sql

    for forbidden_binary_type in [" bytea", " blob", " binary"]:
        assert forbidden_binary_type not in sql

    expected_indexes = [
        "archive_pages_source_url_hash_idx on archive_pages (content_hash)",
        "archive_pages_domain_idx on archive_pages (domain)",
        "archive_pages_platform_subject_idx on archive_pages (platform, subject)",
        "archive_blocks_page_order_idx on archive_blocks (page_id, block_order)",
        "archive_assets_page_idx on archive_assets (page_id)",
        "ocr_results_page_idx on ocr_results (page_id)",
        "structured_records_page_type_idx on structured_records (page_id, record_type)",
    ]
    for index_definition in expected_indexes:
        assert index_definition in sql
