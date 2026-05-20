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
            status = "empty" if text == "" else "success"
            return OcrResult(
                plugin=self.name,
                status=status,
                text=text,
                error="",
                elapsed_seconds=round(time.time() - started_at, 4),
                structured_data={"words": words},
            )
        except Exception as exc:
            return OcrResult(
                plugin=self.name,
                status="unavailable",
                text="",
                error=str(exc),
                elapsed_seconds=round(time.time() - started_at, 4),
            )
