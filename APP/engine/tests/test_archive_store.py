"""页面归档存储测试。"""

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
