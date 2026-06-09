#!/usr/bin/env python3
"""单独测试国家数据局超长图片 OCR。

用途：长时间运行单张图片 OCR，判断当前 Tesseract 配置最终能否正常返回。
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from PIL import Image

from engine.ocr_plugins.tesseract import TesseractOcrPlugin


IMAGE_PATH = Path(
    "/tmp/scraper_imgs/cd76c1e9f045/"
    "cd76c1e9f045b4a2197119114d677fdefad6a148a10826b2ed0c262907c1c51c.jpg"
)
OUTPUT_PATH = Path("/tmp/nda_long_image_ocr_result.json")

OCR_CONFIG = {
    "languages": ["chi_sim", "eng"],
    "psm": 6,
    "preprocess": {
        "grayscale": True,
        "threshold": True,
        "resize_ratio": 2,
    },
}


def _image_info(path: Path) -> dict:
    with Image.open(path) as image:
        ratio = float(OCR_CONFIG["preprocess"]["resize_ratio"])
        resized_width = int(image.width * ratio)
        resized_height = int(image.height * ratio)
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "format": image.format,
            "mode": image.mode,
            "width": image.width,
            "height": image.height,
            "pixels": image.width * image.height,
            "resize_ratio": ratio,
            "resized_width": resized_width,
            "resized_height": resized_height,
            "resized_pixels": resized_width * resized_height,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="单独运行国家数据局超长图片 OCR 测试")
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="只检查图片路径和配置，不执行 OCR",
    )
    args = parser.parse_args()

    if not IMAGE_PATH.exists():
        print(f"图片不存在: {IMAGE_PATH}")
        return 2

    info = _image_info(IMAGE_PATH)
    print("图片信息:")
    print(json.dumps(info, ensure_ascii=False, indent=2))
    print("OCR 配置:")
    print(json.dumps(OCR_CONFIG, ensure_ascii=False, indent=2))
    print(f"结果文件: {OUTPUT_PATH}")

    if args.check_only:
        print("检查完成，未执行 OCR。")
        return 0

    started_at = datetime.now().isoformat()
    started = time.time()
    print(f"开始 OCR: {started_at}", flush=True)

    result = TesseractOcrPlugin().recognize(str(IMAGE_PATH), OCR_CONFIG)

    finished_at = datetime.now().isoformat()
    wall_seconds = round(time.time() - started, 2)
    payload = {
        "started_at": started_at,
        "finished_at": finished_at,
        "wall_seconds": wall_seconds,
        "image": info,
        "config": OCR_CONFIG,
        "status": result.status,
        "plugin_elapsed_seconds": result.elapsed_seconds,
        "text_length": len(result.text or ""),
        "error": result.error,
        "text": result.text,
        "structured_data": result.structured_data,
    }

    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("OCR 结束")
    print(f"结束时间: {finished_at}")
    print(f"wall_seconds: {wall_seconds}")
    print(f"status: {result.status}")
    print(f"plugin_elapsed_seconds: {result.elapsed_seconds}")
    print(f"text_length: {len(result.text or '')}")
    print(f"error: {result.error}")
    print("文本预览:")
    print((result.text or "")[:2000])
    print(f"完整结果已写入: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
