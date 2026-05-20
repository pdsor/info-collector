"""OCR 插件入口。"""

from .base import OcrPlugin, OcrResult
from .registry import get_ocr_plugin, list_ocr_plugins, register_ocr_plugin, resolve_ocr_plugin_name
from .tesseract import TesseractOcrPlugin

register_ocr_plugin(TesseractOcrPlugin())

__all__ = [
    "OcrPlugin",
    "OcrResult",
    "TesseractOcrPlugin",
    "get_ocr_plugin",
    "list_ocr_plugins",
    "register_ocr_plugin",
    "resolve_ocr_plugin_name",
]
