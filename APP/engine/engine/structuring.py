"""OCR 块精抽 → structured_records。"""


def run_structuring(blocks, structuring_cfg):
    """从 blocks 中按策略生成 structured_records。"""
    if not (structuring_cfg or {}).get("enabled"):
        return []
    records = []
    for strategy in (structuring_cfg.get("strategies") or []):
        try:
            records.extend(_apply_strategy(blocks, strategy))
        except Exception:
            pass
    return records


def _apply_strategy(blocks, strategy):
    applies_to = strategy.get("applies_to") or {}
    block_types = applies_to.get("block_types") or ["ocr"]
    keywords = applies_to.get("keywords") or []
    record_type = strategy.get("record_type") or "generic_row"

    records = []
    for block in blocks:
        if block.get("block_type") not in block_types:
            continue
        text = block.get("ocr_text") or block.get("text") or ""
        rows = _parse_table_rows(text, keywords)
        for row_data, raw_columns in rows:
            records.append({
                "record_type": record_type,
                "source_block_id": block.get("id"),
                "data": row_data,
                "raw_columns": raw_columns,
            })
    return records


def _parse_table_rows(text, header_keywords):
    """从 OCR 文本中找到含关键词的 header 行，解析后续数据行。"""
    if not header_keywords:
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header_idx = None
    header_cols = []
    for i, line in enumerate(lines):
        if any(kw in line for kw in header_keywords):
            header_cols = line.split()
            header_idx = i
            break
    if header_idx is None or not header_cols:
        return []
    rows = []
    for line in lines[header_idx + 1:]:
        tokens = line.split()
        if not tokens:
            continue
        row_data = {col: (tokens[j] if j < len(tokens) else "") for j, col in enumerate(header_cols)}
        rows.append((row_data, tokens))
    return rows
