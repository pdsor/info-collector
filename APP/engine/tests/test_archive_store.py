"""页面归档存储测试。"""

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
