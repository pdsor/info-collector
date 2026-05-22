"""页面归档对象组装。"""

from copy import deepcopy
from hashlib import sha256


def build_archive_page(
    *,
    source_url,
    entry_url=None,
    final_url=None,
    domain,
    platform=None,
    subject=None,
    title,
    source_name=None,
    publish_time=None,
    fetched_at,
    html="",
    markdown="",
    blocks=None,
    assets=None,
):
    """把详情页采集结果组装为统一页面归档对象。"""
    normalized_blocks = _normalize_blocks(blocks or [])
    normalized_assets = _normalize_assets(assets or [])
    content_hash = _build_content_hash(source_url, final_url, html, markdown)

    contains_ocr = any(_is_ocr_block(block) for block in normalized_blocks)
    contains_table = any(block.get("block_type") == "table" for block in normalized_blocks)

    return {
        "meta": {
            "source_url": source_url,
            "entry_url": entry_url,
            "final_url": final_url or source_url,
            "domain": domain,
            "platform": platform,
            "subject": subject,
            "title": title,
            "source_name": source_name,
            "publish_time": publish_time,
            "fetched_at": fetched_at,
            "content_hash": content_hash,
            "contains_ocr": contains_ocr,
            "contains_table": contains_table,
            "requires_structuring": contains_ocr or contains_table,
        },
        "content": {
            "html": html or "",
            "markdown": markdown or "",
        },
        "blocks": normalized_blocks,
        "assets": normalized_assets,
        "paths": {
            "html": "page.html",
            "markdown": "page.md",
            "blocks": "blocks.json",
            "assets": "assets/manifest.json",
        },
    }


def _build_content_hash(source_url, final_url, html, markdown):
    payload = "\n".join(
        [
            source_url or "",
            final_url or "",
            html or "",
            markdown or "",
        ]
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _normalize_blocks(blocks):
    normalized = []
    for index, block in enumerate(blocks, start=1):
        record = deepcopy(block)
        block_id = record.pop("block_id", None) or record.get("id")
        block_type = record.pop("type", None) or record.get("block_type")
        block_order = record.pop("order", None) or record.get("block_order") or index

        record["id"] = block_id or f"block-{index}"
        record["block_type"] = block_type
        record["block_order"] = block_order
        normalized.append(record)
    return normalized


def _normalize_assets(assets):
    normalized = []
    for index, asset in enumerate(assets, start=1):
        record = deepcopy(asset)
        record.setdefault("id", f"asset-{index}")
        normalized.append(record)
    return normalized


def _is_ocr_block(block):
    block_type = block.get("block_type")
    return block_type in {"ocr", "image_ocr"} or bool(block.get("ocr_text"))
