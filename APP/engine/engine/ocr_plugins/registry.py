"""OCR 插件注册表。"""

from __future__ import annotations

from .base import OcrPlugin


_PLUGINS: dict[str, OcrPlugin] = {}


def register_ocr_plugin(plugin: OcrPlugin):
    """注册 OCR 插件。"""
    name = getattr(plugin, "name", "").strip()
    if not name:
        raise ValueError("OCR 插件缺少 name")
    _PLUGINS[name] = plugin


def get_ocr_plugin(name: str) -> OcrPlugin:
    """获取 OCR 插件。"""
    plugin_name = name or "tesseract"
    plugin = _PLUGINS.get(plugin_name)
    if plugin is None:
        raise ValueError(f"未知 OCR 插件: {plugin_name}")
    return plugin


def list_ocr_plugins() -> list[str]:
    """列出已注册 OCR 插件名称。"""
    return sorted(_PLUGINS)


def resolve_ocr_plugin_name(config: dict) -> str:
    """从规则 OCR 配置解析插件名称，兼容 engine 字段。"""
    config = config or {}
    return config.get("plugin") or config.get("engine") or "tesseract"
