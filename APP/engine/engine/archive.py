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
    _link_image_assets(normalized_blocks, normalized_assets)
    ocr_results = _build_ocr_results(normalized_blocks)
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
        "ocr_results": ocr_results,
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
        metadata_block_id = record.get("metadata", {}).get("block_id")
        if metadata_block_id and not record.get("block_id"):
            record["block_id"] = metadata_block_id
        normalized.append(record)
    return normalized


def _is_ocr_block(block):
    block_type = block.get("block_type")
    return block_type in {"ocr", "image_ocr"} or bool(block.get("ocr_text"))


def _link_image_assets(blocks, assets):
    assets_by_block_id = {
        asset.get("block_id"): asset
        for asset in assets
        if asset.get("block_id")
    }
    assets_by_source_url = {
        asset.get("source_url"): asset
        for asset in assets
        if asset.get("source_url")
    }
    assets_by_storage_uri = {
        asset.get("storage_uri"): asset
        for asset in assets
        if asset.get("storage_uri")
    }
    blocks_by_id = {block.get("id"): block for block in blocks}

    for block in blocks:
        if block.get("block_type") == "image":
            asset = _find_asset_for_block(
                block, assets_by_block_id, assets_by_source_url, assets_by_storage_uri
            )
            if asset:
                block.setdefault("asset_id", asset.get("id"))
                asset.setdefault("block_id", block.get("id"))

    for block in blocks:
        if not _is_ocr_block(block):
            continue
        parent_block = blocks_by_id.get(block.get("parent_block_id"))
        if parent_block and parent_block.get("asset_id"):
            block.setdefault("asset_id", parent_block.get("asset_id"))
        else:
            asset = _find_asset_for_block(
                block, assets_by_block_id, assets_by_source_url, assets_by_storage_uri
            )
            if asset:
                block.setdefault("asset_id", asset.get("id"))


def _find_asset_for_block(
    block, assets_by_block_id, assets_by_source_url, assets_by_storage_uri
):
    return (
        assets_by_block_id.get(block.get("id"))
        or assets_by_source_url.get(block.get("source_url"))
        or assets_by_storage_uri.get(block.get("storage_uri"))
    )


def _build_ocr_results(blocks):
    results = []
    for block in blocks:
        if not _is_ocr_block(block):
            continue
        results.append(
            {
                "page_id": None,
                "asset_id": block.get("asset_id"),
                "block_id": block.get("id"),
                "parent_block_id": block.get("parent_block_id"),
                "engine": block.get("engine"),
                "status": block.get("status") or "success",
                "ocr_text": block.get("ocr_text") or block.get("text") or "",
                "structured_data": block.get("structured_data") or {},
                "elapsed_seconds": block.get("elapsed_seconds"),
                "error": block.get("error"),
                "manual_review_required": bool(block.get("manual_review_required", False)),
            }
        )
    return results
