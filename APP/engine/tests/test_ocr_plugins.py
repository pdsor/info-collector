"""OCR 插件注册表测试。"""

from engine.ocr_plugins import OcrResult, get_ocr_plugin, register_ocr_plugin, resolve_ocr_plugin_name


class FakeOcrPlugin:
    name = "fake"

    def recognize(self, image_path: str, config: dict) -> OcrResult:
        return OcrResult(
            plugin="fake",
            status="success",
            text="序号 | 数据名称\n1 | 企业登记数据集",
            error="",
            elapsed_seconds=0.01,
        )


def test_register_and_get_custom_ocr_plugin():
    """可注册并获取自定义 OCR 插件。"""
    register_ocr_plugin(FakeOcrPlugin())

    plugin = get_ocr_plugin("fake")
    result = plugin.recognize("/tmp/fake.png", {})

    assert plugin.name == "fake"
    assert result.to_item_fields() == {
        "ocr_plugin": "fake",
        "ocr_engine": "fake",
        "ocr_status": "success",
        "ocr_text": "序号 | 数据名称\n1 | 企业登记数据集",
        "ocr_error": "",
        "ocr_elapsed_seconds": 0.01,
        "ocr_empty": False,
        "manual_review_required": False,
    }


def test_resolve_ocr_plugin_name_prefers_plugin_and_keeps_engine_compatibility():
    """规则优先使用 plugin 字段，并兼容旧 engine 字段。"""
    assert resolve_ocr_plugin_name({"plugin": "fake", "engine": "tesseract"}) == "fake"
    assert resolve_ocr_plugin_name({"engine": "tesseract"}) == "tesseract"
    assert resolve_ocr_plugin_name({}) == "tesseract"


def test_unknown_ocr_plugin_raises_clear_error():
    """未知 OCR 插件返回明确错误。"""
    try:
        get_ocr_plugin("missing")
    except ValueError as exc:
        assert "未知 OCR 插件" in str(exc)
    else:
        raise AssertionError("未知 OCR 插件必须报错")


def test_default_tesseract_plugin_is_registered():
    """默认 Tesseract 插件应自动注册。"""
    plugin = get_ocr_plugin("tesseract")

    assert plugin.name == "tesseract"


def test_tesseract_unavailable_returns_manual_review(monkeypatch, tmp_path):
    """Tesseract 不可用时插件返回人工复核状态。"""
    from engine.ocr_plugins.tesseract import TesseractOcrPlugin

    image_path = tmp_path / "table.png"
    image_path.write_bytes(b"not-a-real-image")

    def raise_missing(*args, **kwargs):
        raise RuntimeError("tesseract missing")

    monkeypatch.setattr("engine.ocr_plugins.tesseract._call_tesseract", raise_missing)

    result = TesseractOcrPlugin().recognize(
        str(image_path),
        {"languages": ["chi_sim", "eng"], "psm": 6, "preprocess": {"grayscale": True}},
    )

    assert result.plugin == "tesseract"
    assert result.status == "unavailable"
    assert result.text == ""
    assert result.manual_review_required is True
    assert "tesseract missing" in result.error


def test_tesseract_success_returns_text(monkeypatch, tmp_path):
    """Tesseract 插件成功时返回文本。"""
    from engine.ocr_plugins.tesseract import TesseractOcrPlugin

    image_path = tmp_path / "table.png"
    image_path.write_bytes(b"fake-image")
    monkeypatch.setattr("engine.ocr_plugins.tesseract._call_tesseract", lambda *args, **kwargs: "序号 | 数据名称\n1 | 企业登记数据集")
    monkeypatch.setattr(
        "engine.ocr_plugins.tesseract._call_tesseract_data",
        lambda *args, **kwargs: [{"text": "序号", "left": 10, "top": 20, "width": 30, "height": 12, "conf": 95.0}],
    )

    result = TesseractOcrPlugin().recognize(str(image_path), {"languages": ["chi_sim", "eng"], "psm": 6})

    assert result.status == "success"
    assert result.text == "序号 | 数据名称\n1 | 企业登记数据集"
    assert result.manual_review_required is False
    assert result.structured_data["words"][0]["text"] == "序号"


def test_ocr_result_to_item_fields_excludes_structured_data():
    """OCR 结构化元数据不直接写入普通输出字段。"""
    result = OcrResult(
        plugin="fake",
        status="success",
        text="序号 数据集名称",
        error="",
        elapsed_seconds=0.01,
        structured_data={"words": [{"text": "序号", "left": 1, "top": 2, "width": 3, "height": 4}]},
    )

    fields = result.to_item_fields()

    assert "structured_data" not in fields
    assert fields["ocr_text"] == "序号 数据集名称"
