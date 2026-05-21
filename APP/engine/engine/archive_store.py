"""页面归档存储接口。"""

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

    def save_page(self, page):
        """保存页面归档记录并返回页面 ID。"""
        page_id = str(uuid4())
        record = deepcopy(page)
        record["id"] = page_id
        self.pages.append(record)
        return page_id

    def save_block(self, page_id, block):
        """保存页面内容块并返回块 ID。"""
        block_id = str(uuid4())
        record = deepcopy(block)
        record["id"] = block_id
        record["page_id"] = page_id
        self.blocks.append(record)
        return block_id

    def save_asset(self, page_id, asset):
        """保存页面资产元数据并返回资产 ID。"""
        asset_id = str(uuid4())
        record = deepcopy(asset)
        record["id"] = asset_id
        record["page_id"] = page_id
        self.assets.append(record)
        return asset_id
