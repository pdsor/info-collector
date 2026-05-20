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


def _build_column_ranges(header_row: list[dict], mapping: dict) -> list[dict]:
    headers = []
    for word in sorted(header_row, key=lambda item: item.get("left", 0)):
        target = mapping.get(word["text"])
        if target:
            headers.append({"field": target, "left": word.get("left", 0)})
    if {"id", "name"} - {header["field"] for header in headers}:
        return []

    ranges = []
    for index, header in enumerate(headers):
        previous_left = headers[index - 1]["left"] if index > 0 else None
        next_left = headers[index + 1]["left"] if index + 1 < len(headers) else None
        start = (previous_left + header["left"]) / 2 if previous_left is not None else float("-inf")
        end = (header["left"] + next_left) / 2 if next_left is not None else float("inf")
        ranges.append({"field": header["field"], "start": start, "end": end})
    return ranges


def _parse_positioned_table(words: list[dict], config: dict) -> tuple[list[dict], list[str], bool] | None:
    mapping = (config or {}).get("column_mapping") or {}
    rows = _word_rows(words)
    for header_index, row in enumerate(rows):
        ranges = _build_column_ranges(row, mapping)
        if not ranges:
            continue

        records = []
        for data_row in rows[header_index + 1:]:
            sorted_row = sorted(data_row, key=lambda item: item.get("left", 0))
            if not sorted_row or not _is_id_text(sorted_row[0]["text"]):
                continue

            values = {column["field"]: [] for column in ranges}
            for word in sorted_row:
                left = word.get("left", 0)
                for column in ranges:
                    if column["start"] <= left < column["end"]:
                        values[column["field"]].append(word["text"])
                        break

            if not values.get("id") or not values.get("name"):
                continue

            record = {}
            for field, field_values in values.items():
                if not field_values:
                    continue
                separator = "" if field in {"name", "department"} else " "
                record[field] = separator.join(field_values)
            record["ocr_text"] = _row_text(sorted_row)
            records.append(record)

        if records:
            return records, [], False
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
    positioned_result = _parse_positioned_table(structured_data.get("words") or [], config)
    if positioned_result:
        return positioned_result
    return parse_ocr_text(getattr(ocr_result, "text", ""), config)
