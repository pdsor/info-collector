"""OCR 插件协议。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class OcrResult:
    """OCR 插件统一结果。"""

    plugin: str
    status: str
    text: str = ""
    error: str = ""
    elapsed_seconds: float = 0.0
    structured_data: dict | None = None
    quality_status: str = "usable"
    quality_reasons: list[str] | None = None

    @property
    def empty(self) -> bool:
        return self.text.strip() == ""

    @property
    def manual_review_required(self) -> bool:
        return self.status != "success" or self.empty or self.quality_status != "usable"

    def to_item_fields(self) -> dict:
        """转换为采集记录中的 OCR 字段。"""
        return {
            "ocr_plugin": self.plugin,
            "ocr_engine": self.plugin,
            "ocr_status": self.status,
            "ocr_text": self.text,
            "ocr_error": self.error,
            "ocr_elapsed_seconds": self.elapsed_seconds,
            "ocr_empty": self.empty,
            "ocr_quality_status": self.quality_status,
            "ocr_quality_reasons": self.quality_reasons or [],
            "manual_review_required": self.manual_review_required,
        }


class OcrPlugin(Protocol):
    """OCR 插件接口。"""

    name: str

    def recognize(self, image_path: str, config: dict) -> OcrResult:
        """识别图片并返回统一 OCR 结果。"""
