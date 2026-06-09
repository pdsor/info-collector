#!/usr/bin/env python3
"""单张图片 OCR 质量测试工具。"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

from engine.ocr_plugins.tesseract import TesseractOcrPlugin


DEFAULT_OUTPUT = Path("/tmp/single_image_ocr_quality_result.json")


def _build_config(args: argparse.Namespace) -> dict:
    preprocess = {
        "grayscale": not args.no_grayscale,
        "threshold": not args.no_threshold,
        "resize_ratio": args.resize_ratio,
    }
    return {
        "languages": args.languages,
        "psm": args.psm,
        "prefer_table_cells_text": args.prefer_table_cells_text,
        "preprocess": preprocess,
    }


def _image_info(path: Path, resize_ratio: float) -> dict:
    with Image.open(path) as image:
        resized_width = int(image.width * resize_ratio)
        resized_height = int(image.height * resize_ratio)
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "format": image.format,
            "mode": image.mode,
            "width": image.width,
            "height": image.height,
            "pixels": image.width * image.height,
            "resize_ratio": resize_ratio,
            "resized_width": resized_width,
            "resized_height": resized_height,
            "resized_pixels": resized_width * resized_height,
        }


def _quality_summary(text: str, structured_data: dict) -> dict:
    lines = [line for line in text.splitlines() if line.strip()]
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    ascii_letters = len(re.findall(r"[A-Za-z]", text))
    digits = len(re.findall(r"\d", text))
    weird_chars = len(re.findall(r"[^\sA-Za-z0-9\u4e00-\u9fff，。；：、（）()《》“”‘’！？,.|/\\-_%+]", text))
    words = structured_data.get("words") or []
    confidences = [
        float(word.get("conf"))
        for word in words
        if isinstance(word, dict) and float(word.get("conf", -1)) >= 0
    ]
    return {
        "text_length": len(text),
        "non_empty_lines": len(lines),
        "chinese_chars": chinese_chars,
        "ascii_letters": ascii_letters,
        "digits": digits,
        "weird_chars": weird_chars,
        "weird_char_ratio": round(weird_chars / max(len(text), 1), 4),
        "word_count": len(words),
        "avg_word_conf": round(sum(confidences) / len(confidences), 2) if confidences else None,
        "table_grid_detected": bool((structured_data.get("table_grid") or {}).get("rows")),
        "table_cell_rows": len(structured_data.get("table_cells") or []),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="单张图片 OCR 质量测试")
    parser.add_argument("image", help="要测试的图片路径")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON 结果输出路径")
    parser.add_argument("--text-output", default="", help="完整 OCR 文本输出路径，默认与 JSON 同名 .txt")
    parser.add_argument("--languages", nargs="+", default=["chi_sim", "eng"], help="Tesseract 语言")
    parser.add_argument("--psm", type=int, default=6, help="Tesseract PSM")
    parser.add_argument("--resize-ratio", type=float, default=2.0, help="预处理缩放倍数")
    parser.add_argument("--no-grayscale", action="store_true", help="不转灰度")
    parser.add_argument("--no-threshold", action="store_true", help="不做二值化阈值")
    parser.add_argument("--prefer-table-cells-text", action="store_true", help="检测到表格时用逐单元格 Markdown 表格作为主文本")
    parser.add_argument("--preview-chars", type=int, default=3000, help="控制台预览字符数")
    parser.add_argument("--check-only", action="store_true", help="只检查图片和配置，不执行 OCR")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser()
    output_path = Path(args.output).expanduser()
    text_output_path = Path(args.text_output).expanduser() if args.text_output else output_path.with_suffix(".txt")
    if not image_path.exists():
        print(f"图片不存在: {image_path}")
        return 2

    config = _build_config(args)
    info = _image_info(image_path, args.resize_ratio)
    print("图片信息:")
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print("OCR 配置:")
    print(json.dumps(config, ensure_ascii=False, indent=2))
    print(f"JSON 结果: {output_path}")
    print(f"文本结果: {text_output_path}")
    if args.check_only:
        print("检查完成，未执行 OCR。")
        return 0

    started_at = datetime.now().isoformat()
    started = time.time()
    print(f"开始 OCR: {started_at}", flush=True)
    result = TesseractOcrPlugin().recognize(str(image_path), config)
    finished_at = datetime.now().isoformat()
    text = result.text or ""
    structured_data = result.structured_data or {}
    payload = {
        "started_at": started_at,
        "finished_at": finished_at,
        "wall_seconds": round(time.time() - started, 2),
        "image": info,
        "config": config,
        "status": result.status,
        "plugin_elapsed_seconds": result.elapsed_seconds,
        "error": result.error,
        "quality": _quality_summary(text, structured_data),
        "text": text,
        "structured_data": structured_data,
    }

    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    text_output_path.write_text(text, encoding="utf-8")

    print("OCR 结束")
    print(f"结束时间: {finished_at}")
    print(f"wall_seconds: {payload['wall_seconds']}")
    print(f"status: {result.status}")
    print(f"plugin_elapsed_seconds: {result.elapsed_seconds}")
    print("质量摘要:")
    print(json.dumps(payload["quality"], ensure_ascii=False, indent=2))
    print("文本预览:")
    print(text[: max(args.preview_chars, 0)])
    print(f"完整 JSON 已写入: {output_path}")
    print(f"完整文本已写入: {text_output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
