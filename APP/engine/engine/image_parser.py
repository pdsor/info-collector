"""图片 OCR 文本结构化解析。"""

from __future__ import annotations

import re


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text or "").splitlines() if line.strip()]


def _split_line(line: str, delimiters: list[str]) -> list[str]:
    for delimiter in delimiters or ["|", "\t", ","]:
        if delimiter in line:
            return [part.strip() for part in line.split(delimiter)]
    return [line.strip()]


def _manual_record(text: str, error: str) -> tuple[list[dict], list[str], bool]:
    return [{"title": "OCR 半结构化结果", "ocr_text": text}], [error], True


def _clean_cell_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _parse_table(text: str, config: dict) -> tuple[list[dict], list[str], bool]:
    lines = _clean_lines(text)
    delimiters = config.get("delimiters") or ["|", "\t", ","]
    mapping = config.get("column_mapping") or {}
    for header_index, line in enumerate(lines):
        headers = _split_line(line, delimiters)
        if not any(mapping.get(header) for header in headers):
            continue
        records = []
        errors = []
        for row_index, row_line in enumerate(lines[header_index + 1:], start=1):
            values = _split_line(row_line, delimiters)
            if len(values) != len(headers):
                errors.append(f"第 {row_index} 行列数不一致")
                continue
            record = {}
            for header, value in zip(headers, values):
                target = mapping.get(header)
                if target:
                    record[target] = value
            if record:
                record["ocr_text"] = row_line
                records.append(record)
        if records:
            return records, errors, False
    return _manual_record(text, "未识别到表头或列数不一致")


def _parse_key_value(text: str, config: dict) -> tuple[list[dict], list[str], bool]:
    mapping = config.get("column_mapping") or {}
    record = {}
    for line in _clean_lines(text):
        match = re.match(r"^([^:：]+)[:：]\s*(.+)$", line)
        if not match:
            continue
        label, value = match.groups()
        target = mapping.get(label.strip())
        if target:
            record[target] = value.strip()
    if record:
        record["ocr_text"] = text
        return [record], [], False
    return _manual_record(text, "未识别到键值字段")


def _word_rows(words: list[dict], tolerance: int = 8) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda item: (item.get("top", 0), item.get("left", 0))):
        text = str(word.get("text") or "").strip()
        if not text:
            continue
        word = {**word, "text": text}
        for row in rows:
            row_top = sum(item.get("top", 0) for item in row) / len(row)
            if abs(word.get("top", 0) - row_top) <= tolerance:
                row.append(word)
                row.sort(key=lambda item: item.get("left", 0))
                break
        else:
            rows.append([word])
    return rows


def _row_text(row: list[dict]) -> str:
    return " ".join(word["text"] for word in sorted(row, key=lambda item: item.get("left", 0)))


def _is_id_text(text: str) -> bool:
    return bool(re.fullmatch(r"\d+", str(text or "").strip()))


def _is_id_row(row: list[dict]) -> bool:
    sorted_row = sorted(row, key=lambda item: item.get("left", 0))
    return bool(sorted_row and _is_id_text(sorted_row[0]["text"]))


def _word_center(word: dict) -> float:
    return word.get("left", 0) + (word.get("width", 0) or 0) / 2


def _match_header_words(header_row: list[dict], mapping: dict) -> list[dict]:
    headers = []
    words = sorted(header_row, key=lambda item: item.get("left", 0))
    for start in range(len(words)):
        phrase = ""
        for end in range(start, min(len(words), start + 6)):
            phrase += words[end]["text"]
            target = mapping.get(phrase)
            if not target:
                continue
            left = words[start].get("left", 0)
            right = words[end].get("left", 0) + (words[end].get("width", 0) or 0)
            headers.append({"field": target, "left": left, "center": (left + right) / 2})
    deduped = []
    seen = set()
    for header in sorted(headers, key=lambda item: item["center"]):
        if header["field"] in seen:
            continue
        seen.add(header["field"])
        deduped.append(header)
    return deduped


def _infer_id_header(rows: list[list[dict]], first_header_center: float | None) -> dict | None:
    centers = []
    for row in rows:
        sorted_row = sorted(row, key=lambda item: item.get("left", 0))
        if not sorted_row or not _is_id_text(sorted_row[0]["text"]):
            continue
        center = _word_center(sorted_row[0])
        if first_header_center is None or center < first_header_center:
            centers.append(center)
    if not centers:
        return None
    centers.sort()
    return {"field": "id", "left": centers[len(centers) // 2], "center": centers[len(centers) // 2]}


def _build_column_ranges(header_row: list[dict], mapping: dict, data_rows: list[list[dict]] | None = None) -> list[dict]:
    headers = _match_header_words(header_row, mapping)
    if "id" not in {header["field"] for header in headers}:
        first_header_center = min((header["center"] for header in headers), default=None)
        inferred_id = _infer_id_header(data_rows or [], first_header_center)
        if inferred_id:
            headers.append(inferred_id)
            headers.sort(key=lambda item: item["center"])
    if {"id", "name"} - {header["field"] for header in headers}:
        return []

    ranges = []
    for index, header in enumerate(headers):
        previous_center = headers[index - 1]["center"] if index > 0 else None
        next_center = headers[index + 1]["center"] if index + 1 < len(headers) else None
        start = (previous_center + header["center"]) / 2 if previous_center is not None else float("-inf")
        end = (header["center"] + next_center) / 2 if next_center is not None else float("inf")
        ranges.append({"field": header["field"], "start": start, "end": end})
    return ranges


def _record_row_groups(rows: list[list[dict]]) -> list[list[dict]]:
    groups = []
    current: list[dict] = []
    for row in rows:
        if _is_id_row(row):
            if current:
                groups.append(current)
            current = list(row)
        elif current:
            current.extend(row)
    if current:
        groups.append(current)
    return groups


def _words_text(words: list[dict]) -> str:
    return " ".join(
        word["text"]
        for word in sorted(words, key=lambda item: (item.get("left", 0), item.get("top", 0)))
    )


def _words_reading_text(words: list[dict]) -> str:
    return " ".join(
        word["text"]
        for word in sorted(words, key=lambda item: (item.get("top", 0), item.get("left", 0)))
    )


def _words_joined_text(words: list[dict]) -> str:
    return "".join(
        word["text"]
        for word in sorted(words, key=lambda item: (item.get("top", 0), item.get("left", 0)))
    )


def _cell_words(words: list[dict], left: float, right: float, top: float, bottom: float) -> list[dict]:
    cell_words = []
    for word in words:
        center_x = _word_center(word)
        center_y = word.get("top", 0) + (word.get("height", 0) or 0) / 2
        if left <= center_x < right and top <= center_y < bottom:
            cell_words.append(word)
    return cell_words


def _first_id(text: str) -> str:
    match = re.search(r"\d+", str(text or ""))
    return match.group(0) if match else str(text or "").strip()


def _parse_grid_table(words: list[dict], grid: dict, config: dict) -> tuple[list[dict], list[str], bool] | None:
    row_lines = sorted(grid.get("rows") or [])
    column_lines = sorted(grid.get("columns") or [])
    if len(row_lines) < 3 or len(column_lines) < 3:
        return None

    mapping = (config or {}).get("column_mapping") or {}
    column_fields: list[dict] = []
    for column_index in range(len(column_lines) - 1):
        header_words = _cell_words(
            words,
            column_lines[column_index],
            column_lines[column_index + 1],
            row_lines[0],
            row_lines[1],
        )
        header_text = _words_joined_text(header_words)
        target = mapping.get(header_text)
        if target:
            column_fields.append({"index": column_index, "field": target})
    if {"id", "name"} - {column["field"] for column in column_fields}:
        return None

    records = []
    errors = []
    for row_index in range(1, len(row_lines) - 1):
        record = {}
        ocr_parts = []
        for column in column_fields:
            cell_words_for_column = _cell_words(
                words,
                column_lines[column["index"]],
                column_lines[column["index"] + 1],
                row_lines[row_index],
                row_lines[row_index + 1],
            )
            value = _words_reading_text(cell_words_for_column).strip()
            if column["field"] == "id":
                value = _first_id(value)
            if value:
                record[column["field"]] = value
                ocr_parts.append(value)
        if not record:
            continue
        record["ocr_text"] = " ".join(ocr_parts)
        if not record.get("id") or not record.get("name"):
            record = {
                "id": record.get("id", "?"),
                "title": "OCR 半结构化结果",
                "ocr_text": " ".join(ocr_parts),
            }
            errors.append(f"第 {record.get('id', '?')} 行字段不完整")
        records.append(record)

    if records:
        return records, errors, bool(errors)
    return None


def _parse_table_cells(cells: list[list[str]], config: dict) -> tuple[list[dict], list[str], bool] | None:
    if len(cells or []) < 2:
        return None
    mapping = (config or {}).get("column_mapping") or {}
    column_order = list((config or {}).get("column_order") or [])
    if not column_order:
        header = [_clean_cell_text(cell).replace(" ", "") for cell in cells[0]]
        column_order = [mapping.get(label, "") for label in header]
    if {"id", "name"} - set(column_order):
        return None

    records = []
    errors = []
    pending_records = []
    for row in cells[1:]:
        record = {}
        parts = []
        for index, field in enumerate(column_order):
            if not field or index >= len(row):
                continue
            value = _clean_cell_text(row[index])
            if field == "id":
                value = _first_id(value)
            if value:
                record[field] = value
                parts.append(value)
        if not record:
            continue
        if not record.get("id") or not record.get("name"):
            continue
        pending_records.append((record, parts))

    if not pending_records:
        return None
    numeric_ids = [int(record["id"]) for record, _ in pending_records if str(record.get("id", "")).isdigit()]
    expected_id = numeric_ids[0] if numeric_ids else 1
    for record, parts in pending_records:
        record["id"] = str(expected_id)
        expected_id += 1
        if parts:
            parts[0] = record["id"]
        record["ocr_text"] = " ".join(parts)
        records.append(record)
    if records:
        return records, errors, bool(errors)
    return None


def _parse_positioned_table(words: list[dict], config: dict) -> tuple[list[dict], list[str], bool] | None:
    mapping = (config or {}).get("column_mapping") or {}
    rows = _word_rows(words)
    for header_index, row in enumerate(rows):
        ranges = _build_column_ranges(row, mapping, rows[header_index + 1:])
        if not ranges:
            continue

        records = []
        errors = []
        for data_row in _record_row_groups(rows[header_index + 1:]):
            sorted_row = sorted(data_row, key=lambda item: item.get("left", 0))
            if not sorted_row:
                continue

            values = {column["field"]: [] for column in ranges}
            for word in sorted_row:
                left = word.get("left", 0)
                width = word.get("width", 0) or 0
                position = left + width / 2
                for column in ranges:
                    if column["start"] <= position < column["end"]:
                        values[column["field"]].append(word["text"])
                        break

            record = {}
            for field, field_values in values.items():
                if not field_values:
                    continue
                record[field] = " ".join(field_values).strip()
            record["ocr_text"] = _words_text(sorted_row)
            if not record.get("id"):
                record["id"] = sorted_row[0]["text"]
            if not record.get("name"):
                record = {
                    "id": record.get("id", sorted_row[0]["text"]),
                    "title": "OCR 半结构化结果",
                    "ocr_text": _words_text(sorted_row),
                }
                errors.append(f"第 {record.get('id', '?')} 行字段不完整")
            records.append(record)

        if records:
            return records, errors, bool(errors)
    return None


def parse_ocr_text(text: str, config: dict) -> tuple[list[dict], list[str], bool]:
    """把 OCR 原始文本解析为业务记录、错误列表和半结构化标记。"""
    mode = (config or {}).get("mode", "table")
    if mode == "key_value":
        return _parse_key_value(text, config or {})
    return _parse_table(text, config or {})


def parse_ocr_result(ocr_result, config: dict) -> tuple[list[dict], list[str], bool]:
    """优先按 OCR 坐标解析，失败时回退到文本解析。"""
    config = config or {}
    structured_data = getattr(ocr_result, "structured_data", None) or {}
    words = structured_data.get("words") or []
    cells_result = _parse_table_cells(structured_data.get("table_cells") or [], config)
    if cells_result:
        return cells_result
    grid_result = _parse_grid_table(words, structured_data.get("table_grid") or {}, config)
    if grid_result:
        return grid_result
    positioned_result = _parse_positioned_table(words, config)
    if positioned_result:
        return positioned_result
    return parse_ocr_text(getattr(ocr_result, "text", ""), config)
