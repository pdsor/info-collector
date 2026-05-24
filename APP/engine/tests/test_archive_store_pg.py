"""PostgreSQL 真实连接集成测试。

需要设置环境变量 ARCHIVE_PG_DSN 才会执行（例如：
  export ARCHIVE_PG_DSN="postgresql://user:pass@localhost:5432/testdb"
）。未设置时整组跳过。
"""

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("ARCHIVE_PG_DSN"),
    reason="ARCHIVE_PG_DSN not set — skipping PG integration tests",
)


@pytest.fixture(scope="module")
def pg_store():
    """建表 + 产出 ArchiveStore；模块结束后删表。"""
    from sqlalchemy import create_engine, text

    from engine.archive_store import ARCHIVE_METADATA, ArchiveStore

    dsn = os.getenv("ARCHIVE_PG_DSN")
    engine = create_engine(dsn)

    # 使用独立 schema 隔离测试
    schema = f"test_{uuid.uuid4().hex[:8]}"
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.commit()

    ARCHIVE_METADATA.create_all(engine)

    store = ArchiveStore(dsn=dsn)
    yield store

    # Teardown — 删除测试 schema
    ARCHIVE_METADATA.drop_all(engine)
    with engine.connect() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
    engine.dispose()


def _sample_archive_page(*, content_hash=None):
    h = content_hash or uuid.uuid4().hex * 2
    return {
        "meta": {
            "source_url": f"https://example.com/detail/{h[:8]}.html",
            "entry_url": "https://example.com/list.html",
            "final_url": f"https://example.com/detail/{h[:8]}.html",
            "domain": "example.com",
            "platform": "example",
            "subject": "数据要素",
            "title": f"测试归档页 {h[:8]}",
            "source_name": "示例来源",
            "publish_time": None,
            "fetched_at": "2026-05-24T10:00:00+08:00",
            "content_hash": h,
            "contains_ocr": False,
            "contains_table": False,
            "requires_structuring": False,
        },
        "content": {"html": "<html><body>test</body></html>", "markdown": "test"},
        "blocks": [
            {"id": "b1", "block_order": 1, "block_type": "heading", "text": "测试标题"},
            {"id": "b2", "block_order": 2, "block_type": "paragraph", "text": "测试正文"},
        ],
        "assets": [],
        "ocr_results": [],
        "structured_records": [],
    }


def test_pg_save_and_query_page(pg_store):
    """保存页面后能从 archive_pages 查回。"""
    from sqlalchemy import create_engine, select, text

    from engine.archive_store import ARCHIVE_PAGES

    page = _sample_archive_page()
    result = pg_store.save_archive_page(page)

    page_id = result["page_id"]
    assert page_id

    engine = create_engine(os.getenv("ARCHIVE_PG_DSN"))
    with engine.connect() as conn:
        row = conn.execute(
            select(ARCHIVE_PAGES).where(ARCHIVE_PAGES.c.id == page_id)
        ).fetchone()
    engine.dispose()

    assert row is not None
    assert row.title == page["meta"]["title"]
    assert row.domain == "example.com"


def test_pg_save_blocks_linked_to_page(pg_store):
    """保存后 archive_blocks 各块的 page_id 指向新页面。"""
    from sqlalchemy import create_engine, select

    from engine.archive_store import ARCHIVE_BLOCKS

    page = _sample_archive_page()
    result = pg_store.save_archive_page(page)
    page_id = result["page_id"]

    engine = create_engine(os.getenv("ARCHIVE_PG_DSN"))
    with engine.connect() as conn:
        rows = conn.execute(
            select(ARCHIVE_BLOCKS).where(ARCHIVE_BLOCKS.c.page_id == page_id)
        ).fetchall()
    engine.dispose()

    assert len(rows) == 2
    types = {r.block_type for r in rows}
    assert types == {"heading", "paragraph"}


def test_pg_save_structured_records(pg_store):
    """structured_records 随页面一起写入并可查回。"""
    from sqlalchemy import create_engine, select

    from engine.archive_store import STRUCTURED_RECORDS

    page = _sample_archive_page()
    page["structured_records"] = [
        {
            "record_type": "dataset_row",
            "source_block_id": "b2",
            "data": {"序号": "1", "名称": "数据集A"},
            "raw_columns": ["1", "数据集A"],
        }
    ]
    result = pg_store.save_archive_page(page)
    page_id = result["page_id"]

    assert result["counts"]["structured_records"] == 1

    engine = create_engine(os.getenv("ARCHIVE_PG_DSN"))
    with engine.connect() as conn:
        rows = conn.execute(
            select(STRUCTURED_RECORDS).where(STRUCTURED_RECORDS.c.page_id == page_id)
        ).fetchall()
    engine.dispose()

    assert len(rows) == 1
    assert rows[0].record_type == "dataset_row"


def test_pg_rollback_on_failure(pg_store):
    """写入途中失败应回滚，不留半吊子记录。"""
    from sqlalchemy import create_engine, select

    from engine.archive_store import ARCHIVE_PAGES

    original_connect = pg_store._connect

    call_count = {"n": 0}

    def bad_connect():
        conn = original_connect()
        original_execute = conn.execute

        def patched_execute(stmt):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("模拟块写入失败")
            return original_execute(stmt)

        conn.execute = patched_execute
        return conn

    pg_store._connect = bad_connect

    page = _sample_archive_page()
    hash_before = page["meta"]["content_hash"]

    with pytest.raises(RuntimeError):
        pg_store.save_archive_page(page)

    pg_store._connect = original_connect

    engine = create_engine(os.getenv("ARCHIVE_PG_DSN"))
    with engine.connect() as conn:
        rows = conn.execute(
            select(ARCHIVE_PAGES).where(ARCHIVE_PAGES.c.content_hash == hash_before)
        ).fetchall()
    engine.dispose()

    assert rows == []
