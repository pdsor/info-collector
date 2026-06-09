#!/usr/bin/env python3
"""PaddleOCR 单张真实图片测试工具。"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image


DEFAULT_OUTPUT = Path("/tmp/paddleocr_image_result.json")
DEFAULT_HOME = Path("/tmp/paddleocr-home")


def _prepare_runtime(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(home)
    os.environ["XDG_CACHE_HOME"] = str(home / ".cache")
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(home / ".paddlex")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


def _image_info(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "format": image.format,
            "mode": image.mode,
            "width": image.width,
            "height": image.height,
            "pixels": image.width * image.height,
        }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _result_to_dict(result: Any) -> dict[str, Any]:
    if hasattr(result, "json"):
        try:
            payload = result.json
            if isinstance(payload, dict):
                return _json_safe(payload)
        except Exception:
            pass
    if hasattr(result, "to_dict"):
        try:
            return _json_safe(result.to_dict())
        except Exception:
            pass
    if isinstance(result, dict):
        return _json_safe(result)
    return {"raw": _json_safe(result)}


def _extract_texts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("res"), dict):
        payload = payload["res"]
    candidates = []
    for key in ("rec_texts", "texts"):
        value = payload.get(key)
        if isinstance(value, list):
            scores = payload.get("rec_scores") or payload.get("scores") or []
            boxes = (
                payload.get("rec_polys")
                or payload.get("dt_polys")
                or _boxes_to_polys(payload.get("rec_boxes"))
                or _boxes_to_polys(payload.get("boxes"))
                or []
            )
            for index, text in enumerate(value):
                candidates.append(
                    {
                        "index": index,
                        "text": str(text),
                        "score": scores[index] if index < len(scores) else None,
                        "box": boxes[index] if index < len(boxes) else None,
                    }
                )
            return candidates
    raw = payload.get("raw")
    if isinstance(raw, list):
        for index, item in enumerate(raw):
            candidates.append({"index": index, "text": str(item), "score": None, "box": None})
    return candidates


def _boxes_to_polys(boxes: Any) -> list[list[list[float]]]:
    polys = []
    if not isinstance(boxes, list):
        return polys
    for box in boxes:
        if not isinstance(box, (list, tuple)) or len(box) != 4:
            continue
        x1, y1, x2, y2 = [float(value) for value in box]
        polys.append([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])
    return polys


def _box_center(box: Any) -> tuple[float, float]:
    points = box or []
    xs = [float(point[0]) for point in points if isinstance(point, (list, tuple)) and len(point) >= 2]
    ys = [float(point[1]) for point in points if isinstance(point, (list, tuple)) and len(point) >= 2]
    if not xs or not ys:
        return 0.0, 0.0
    return sum(xs) / len(xs), sum(ys) / len(ys)


def _rows_from_lines(lines: list[dict[str, Any]], y_tolerance: float = 14.0) -> list[list[dict[str, Any]]]:
    positioned = []
    for line in lines:
        x, y = _box_center(line.get("box"))
        positioned.append({**line, "_x": x, "_y": y})
    positioned.sort(key=lambda item: (item["_y"], item["_x"]))
    rows: list[list[dict[str, Any]]] = []
    for line in positioned:
        if not rows:
            rows.append([line])
            continue
        current_y = sum(item["_y"] for item in rows[-1]) / len(rows[-1])
        if abs(line["_y"] - current_y) <= y_tolerance:
            rows[-1].append(line)
        else:
            rows.append([line])
    for row in rows:
        row.sort(key=lambda item: item["_x"])
    return rows


def _is_noise_line(line: dict[str, Any]) -> bool:
    text = str(line.get("text") or "").strip()
    score = line.get("score")
    if score is None:
        return False
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        return False
    return score_value < 0.5 and text in {"I", "l", "|", "丨"}


def _normalize_ocr_text(text: str) -> str:
    normalized = text.strip()
    return " ".join(normalized.split()) if " " in normalized else normalized


def _apply_context_fixes(cells: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    return [_normalize_ocr_text(cell) for cell in cells], []


def _repair_sequence_id(value: str, expected: int, next_value: str = "") -> tuple[str, dict[str, str] | None]:
    text = value.strip()
    if text == str(expected):
        return text, None
    if expected == 1 and text in {"11", "I1", "l1", "|1"} and next_value.strip() == "2":
        return "1", {"source": text, "target": "1", "reason": "连续序号纠错"}
    return text, None


def _repair_table_sequence_ids(table_rows: list[list[str]]) -> tuple[list[list[str]], list[dict[str, str]]]:
    repaired = [row[:] for row in table_rows]
    corrections: list[dict[str, str]] = []
    for row_index, row in enumerate(repaired):
        next_value = repaired[row_index + 1][0] if row_index + 1 < len(repaired) else ""
        fixed_id, change = _repair_sequence_id(row[0], row_index + 1, next_value)
        if change:
            row[0] = fixed_id
            corrections.append({"row": str(row_index + 1), "cell": "0", **change})
    return repaired, corrections


def _join_cell_text(existing: str, addition: str) -> str:
    addition = _normalize_ocr_text(addition)
    existing = existing.strip()
    if not existing:
        return addition
    if not addition:
        return existing
    if existing.endswith((",", "，", "、", "“", "\"", "（", "(")):
        return existing + addition
    return existing + addition


def _markdown_cell(text: str) -> str:
    return _normalize_ocr_text(text).replace("|", "\\|").strip()


def _table_markdown_from_lines(lines: list[dict[str, Any]], image_width: int) -> tuple[str, list[dict[str, str]]]:
    """按四列表格版式把 OCR 文本重组成 Markdown 表格。"""
    if not lines or not any(line.get("box") for line in lines):
        return "", []
    boundaries = [0, image_width * 0.13, image_width * 0.43, image_width * 0.66, image_width + 1]
    positioned = []
    for line in lines:
        if _is_noise_line(line):
            continue
        x, y = _box_center(line.get("box"))
        if x <= 0 and y <= 0:
            continue
        positioned.append({**line, "_x": x, "_y": y})
    anchors = [
        line
        for line in positioned
        if str(line.get("text") or "").strip().isdigit() and line["_x"] < boundaries[1]
    ]
    anchors.sort(key=lambda item: item["_y"])
    if anchors:
        header = ["序号", "案例名称", "牵头单位", "参与单位"]
        header_y = min((line["_y"] for line in positioned), default=0.0)
        header_bottom = max(
            (line["_y"] for line in positioned if abs(line["_y"] - header_y) <= 18),
            default=header_y,
        )
        table_rows: list[list[str]] = []
        corrections: list[dict[str, str]] = []
        for index, anchor in enumerate(anchors):
            start_y = header_bottom + 12 if index == 0 else (anchors[index - 1]["_y"] + anchor["_y"]) / 2
            end_y = (
                (anchor["_y"] + anchors[index + 1]["_y"]) / 2
                if index + 1 < len(anchors)
                else float("inf")
            )
            cells = [str(anchor.get("text") or "").strip(), "", "", ""]
            row_lines = [
                line
                for line in positioned
                if start_y <= line["_y"] < end_y and line is not anchor
            ]
            row_lines.sort(key=lambda item: (item["_y"], item["_x"]))
            for line in row_lines:
                text = str(line.get("text") or "").strip()
                if not text:
                    continue
                col = 0
                for col_index in range(4):
                    if boundaries[col_index] <= line["_x"] < boundaries[col_index + 1]:
                        col = col_index
                        break
                if col == 0 and not text.isdigit():
                    continue
                if col == 0:
                    cells[0] = text
                else:
                    cells[col] = _join_cell_text(cells[col], text)
            fixed_cells, _changes = _apply_context_fixes(cells)
            for change in _changes:
                corrections.append({"row": str(index + 1), **change})
            table_rows.append(fixed_cells)
        table_rows, sequence_corrections = _repair_table_sequence_ids(table_rows)
        corrections.extend(sequence_corrections)
        lines_md = [
            "| " + " | ".join(header) + " |",
            "| --- | --- | --- | --- |",
        ]
        for row in table_rows:
            lines_md.append("| " + " | ".join(_markdown_cell(cell) for cell in row) + " |")
        return "\n".join(lines_md), corrections

    rows = _rows_from_lines(lines)
    table_rows: list[list[str]] = []
    current: list[list[str]] | None = None
    for visual_row in rows:
        cells = ["", "", "", ""]
        for line in visual_row:
            x = line.get("_x", 0)
            col = 0
            for index in range(4):
                if boundaries[index] <= x < boundaries[index + 1]:
                    col = index
                    break
            text = str(line.get("text") or "").strip()
            if text:
                cells[col] = _join_cell_text(cells[col], text)
        first = cells[0].strip()
        if first in {"序号", "1", "2", "3", "4", "5"} or first.isdigit():
            current = cells
            table_rows.append(current)
        elif current:
            for index, text in enumerate(cells):
                if text:
                    current[index] = _join_cell_text(current[index], text)
    if len(table_rows) < 2:
        return "", []
    data_rows, sequence_corrections = _repair_table_sequence_ids(table_rows[1:])
    table_rows = [table_rows[0], *data_rows]
    lines_md = [
        "| " + " | ".join(table_rows[0]) + " |",
        "| --- | --- | --- | --- |",
    ]
    for row in table_rows[1:]:
        lines_md.append("| " + " | ".join(row) + " |")
    return "\n".join(lines_md), sequence_corrections


def _markdown_from_lines(lines: list[dict[str, Any]]) -> str:
    return "\n".join(line["text"] for line in lines if line.get("text"))


def main() -> int:
    parser = argparse.ArgumentParser(description="PaddleOCR 单张图片 CPU 测试")
    parser.add_argument("image", help="真实图片路径")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON 输出路径")
    parser.add_argument("--home", default=str(DEFAULT_HOME), help="PaddleOCR/PaddleX 可写 HOME 缓存目录")
    parser.add_argument("--lang", default="ch", help="OCR 语言，中文默认 ch")
    parser.add_argument("--det-model", default="PP-OCRv5_mobile_det", help="文本检测模型名")
    parser.add_argument("--rec-model", default="PP-OCRv5_mobile_rec", help="文本识别模型名")
    parser.add_argument("--limit-side-len", type=int, default=960, help="检测输入长边限制")
    parser.add_argument("--preview-chars", type=int, default=3000, help="控制台预览字符数")
    parser.add_argument("--check-only", action="store_true", help="只检查图片和环境，不执行 OCR")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser()
    output_path = Path(args.output).expanduser()
    text_path = output_path.with_suffix(".txt")
    markdown_path = output_path.with_suffix(".md")
    home = Path(args.home).expanduser()
    _prepare_runtime(home)

    if not image_path.exists():
        print(f"图片不存在: {image_path}")
        return 2

    info = _image_info(image_path)
    print("图片信息:")
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print("PaddleOCR 配置:")
    config = {
        "lang": args.lang,
        "text_detection_model_name": args.det_model,
        "text_recognition_model_name": args.rec_model,
        "text_det_limit_side_len": args.limit_side_len,
        "use_doc_orientation_classify": False,
        "use_doc_unwarping": False,
        "use_textline_orientation": False,
        "home": str(home),
    }
    print(json.dumps(config, ensure_ascii=False, indent=2))
    print(f"JSON 结果: {output_path}")
    print(f"文本结果: {text_path}")
    print(f"Markdown 结果: {markdown_path}")
    if args.check_only:
        print("检查完成，未执行 OCR。")
        return 0

    from paddleocr import PaddleOCR

    started_at = datetime.now().isoformat()
    started = time.time()
    print(f"开始 PaddleOCR: {started_at}", flush=True)
    ocr = PaddleOCR(
        lang=args.lang,
        text_detection_model_name=args.det_model,
        text_recognition_model_name=args.rec_model,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        text_det_limit_side_len=args.limit_side_len,
    )
    raw_results = ocr.predict(str(image_path))
    elapsed = round(time.time() - started, 2)
    result_payloads = [_result_to_dict(item) for item in (raw_results if isinstance(raw_results, list) else [raw_results])]
    lines = []
    for payload in result_payloads:
        lines.extend(_extract_texts(payload))
    text = _markdown_from_lines(lines)
    table_markdown, corrections = _table_markdown_from_lines(lines, info["width"])
    payload = {
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
        "wall_seconds": elapsed,
        "image": info,
        "config": config,
        "line_count": len(lines),
        "text_length": len(text),
        "lines": lines,
        "text": text,
        "table_markdown": table_markdown,
        "corrections": corrections,
        "raw_results": result_payloads,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    text_path.write_text(text, encoding="utf-8")
    markdown_path.write_text(table_markdown or text, encoding="utf-8")

    print("PaddleOCR 结束")
    print(f"wall_seconds: {elapsed}")
    print(f"line_count: {len(lines)}")
    print(f"text_length: {len(text)}")
    print("文本预览:")
    print((table_markdown or text)[: max(args.preview_chars, 0)])
    print(f"完整 JSON 已写入: {output_path}")
    print(f"完整文本已写入: {text_path}")
    print(f"Markdown 已写入: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
