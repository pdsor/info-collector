"""Tesseract OCR 插件。"""

from __future__ import annotations

import time
from pathlib import Path

from .base import OcrResult


def _prepare_image(image_path: str, preprocess: dict):
    """按规则配置预处理图片。"""
    from PIL import Image

    image = Image.open(image_path)
    resize_ratio = float((preprocess or {}).get("resize_ratio") or 1)
    if resize_ratio > 1:
        image = image.resize((int(image.width * resize_ratio), int(image.height * resize_ratio)))
    if (preprocess or {}).get("grayscale"):
        image = image.convert("L")
    if (preprocess or {}).get("threshold"):
        image = image.point(lambda value: 255 if value > 180 else 0)
    return image


def _call_tesseract(image_path: str, languages: list[str], psm: int, preprocess: dict) -> str:
    """调用 pytesseract，把图片转换为文本。"""
    import pytesseract

    image = _prepare_image(image_path, preprocess)
    lang = "+".join(languages or ["chi_sim", "eng"])
    config = f"--psm {int(psm or 6)}"
    return pytesseract.image_to_string(image, lang=lang, config=config)


def _call_tesseract_data(image_path: str, languages: list[str], psm: int, preprocess: dict) -> list[dict]:
    """调用 pytesseract，返回带坐标的词块。"""
    import pytesseract

    image = _prepare_image(image_path, preprocess)
    lang = "+".join(languages or ["chi_sim", "eng"])
    config = f"--psm {int(psm or 6)}"
    data = pytesseract.image_to_data(image, lang=lang, config=config, output_type=pytesseract.Output.DICT)
    words = []
    for index, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text or "").strip()
        if not text:
            continue
        words.append(
            {
                "text": text,
                "left": int(data["left"][index]),
                "top": int(data["top"][index]),
                "width": int(data["width"][index]),
                "height": int(data["height"][index]),
                "conf": float(data["conf"][index]) if str(data["conf"][index]).replace(".", "", 1).lstrip("-").isdigit() else -1.0,
            }
        )
    return words


def _line_groups(indexes) -> list[int]:
    groups = []
    start = None
    previous = None
    for index in indexes:
        index = int(index)
        if start is None:
            start = previous = index
        elif index <= previous + 2:
            previous = index
        else:
            groups.append((start + previous) // 2)
            start = previous = index
    if start is not None:
        groups.append((start + previous) // 2)
    return groups


def _detect_table_grid(image_path: str, preprocess: dict) -> dict:
    """从二值图片中检测表格横线和竖线。"""
    import numpy as np

    image = _prepare_image(image_path, preprocess).convert("L")
    pixels = np.asarray(image)
    dark = pixels < 80
    row_counts = dark.sum(axis=1)
    column_counts = dark.sum(axis=0)
    row_indexes = np.where(row_counts > image.width * 0.5)[0]
    column_indexes = np.where(column_counts > image.height * 0.5)[0]
    rows = _line_groups(row_indexes)
    columns = _line_groups(column_indexes)
    if len(rows) < 3 or len(columns) < 3:
        return {}
    return {"rows": rows, "columns": columns, "width": image.width, "height": image.height}


def _recognize_table_cells(image_path: str, languages: list[str], psm: int, preprocess: dict, grid: dict) -> list[list[str]]:
    """按检测到的表格网格逐单元格 OCR。"""
    import pytesseract

    rows = grid.get("rows") or []
    columns = grid.get("columns") or []
    if len(rows) < 3 or len(columns) < 3:
        return []

    image = _prepare_image(image_path, preprocess).convert("L")
    lang = "+".join(languages or ["chi_sim", "eng"])
    config = f"--psm {int(psm or 6)}"
    table_cells = []
    padding = 4
    for row_index in range(len(rows) - 1):
        row_cells = []
        for column_index in range(len(columns) - 1):
            box = (
                columns[column_index] + padding,
                rows[row_index] + padding,
                columns[column_index + 1] - padding,
                rows[row_index + 1] - padding,
            )
            cell_image = image.crop(box)
            text = pytesseract.image_to_string(cell_image, lang=lang, config=config).strip()
            row_cells.append(text)
        table_cells.append(row_cells)
    return table_cells


class TesseractOcrPlugin:
    """本地 Tesseract OCR 插件。"""

    name = "tesseract"

    def recognize(self, image_path: str, config: dict) -> OcrResult:
        """识别图片，失败时返回人工复核状态。"""
        started_at = time.time()
        try:
            if not Path(image_path).exists():
                raise FileNotFoundError(f"图片文件不存在: {image_path}")
            languages = (config or {}).get("languages") or ["chi_sim", "eng"]
            psm = int((config or {}).get("psm") or 6)
            preprocess = (config or {}).get("preprocess") or {}
            text = _call_tesseract(image_path, languages, psm, preprocess).strip()
            try:
                words = _call_tesseract_data(image_path, languages, psm, preprocess)
            except Exception:
                words = []
            try:
                table_grid = _detect_table_grid(image_path, preprocess)
            except Exception:
                table_grid = {}
            try:
                table_cells = _recognize_table_cells(image_path, languages, psm, preprocess, table_grid)
            except Exception:
                table_cells = []
            status = "empty" if text == "" else "success"
            return OcrResult(
                plugin=self.name,
                status=status,
                text=text,
                error="",
                elapsed_seconds=round(time.time() - started_at, 4),
                structured_data={"words": words, "table_grid": table_grid, "table_cells": table_cells},
            )
        except Exception as exc:
            return OcrResult(
                plugin=self.name,
                status="unavailable",
                text="",
                error=str(exc),
                elapsed_seconds=round(time.time() - started_at, 4),
            )
