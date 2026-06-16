"""OCR 插件注册表测试。"""

import json
from pathlib import Path

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
        "ocr_quality_status": "usable",
        "ocr_quality_reasons": [],
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


def test_default_paddleocr_plugin_is_registered():
    """默认 PaddleOCR 插件应自动注册。"""
    plugin = get_ocr_plugin("paddleocr")

    assert plugin.name == "paddleocr"


def test_paddleocr_plugin_reads_subprocess_payload(monkeypatch, tmp_path):
    """PaddleOCR 插件应读取子进程 JSON，并优先返回 Markdown 表格。"""
    from engine.ocr_plugins.paddleocr import PaddleOcrPlugin

    image_path = tmp_path / "table.png"
    image_path.write_bytes(b"fake-image")
    python_path = tmp_path / "python"
    runner_path = tmp_path / "runner.py"
    python_path.write_text("", encoding="utf-8")
    runner_path.write_text("", encoding="utf-8")

    def fake_run(command, check, capture_output, text, timeout):
        fake_run.command = command
        output_path = command[command.index("--output") + 1]
        from subprocess import CompletedProcess

        Path(output_path).write_text(
            json.dumps(
                {
                    "wall_seconds": 1.23,
                    "text": "原始文本",
                    "table_markdown": "| 序号 | 名称 |\n| --- | --- |\n| 1 | 数码互联 |",
                    "corrections": [{"row": "1", "source": "码互联", "target": "数码互联"}],
                    "lines": [{"text": "数码互联"}],
                    "image": {"width": 100, "height": 50},
                    "config": {"lang": "ch"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("engine.ocr_plugins.paddleocr.subprocess.run", fake_run)

    result = PaddleOcrPlugin().recognize(
        str(image_path),
        {
            "python": str(python_path),
            "runner": str(runner_path),
            "timeout_seconds": 5,
            "min_text_length": 5,
            "min_line_count": 2,
        },
    )

    assert result.status == "success"
    assert result.text.startswith("| 序号 | 名称 |")
    assert result.structured_data["raw_text"] == "原始文本"
    assert result.structured_data["markdown"] == result.text
    assert result.structured_data["corrections"][0]["target"] == "数码互联"


def test_paddleocr_prefers_table_structure_markdown(monkeypatch, tmp_path):
    """启用表格结构识别时应优先使用结构化表格结果。"""
    from engine.ocr_plugins.paddleocr import PaddleOcrPlugin

    image_path = tmp_path / "table.png"
    image_path.write_bytes(b"fake-image")
    python_path = tmp_path / "python"
    runner_path = tmp_path / "runner.py"
    python_path.write_text("", encoding="utf-8")
    runner_path.write_text("", encoding="utf-8")

    def fake_run(command, check, capture_output, text, timeout):
        fake_run.command = command
        output_path = command[command.index("--output") + 1]
        from subprocess import CompletedProcess

        Path(output_path).write_text(
            json.dumps(
                    {
                        "wall_seconds": 1.23,
                        "text": "普通文本",
                        "table_markdown": "| 普通 |",
                        "table_structure_html": "<table><tr><td>序号</td><td>案例名称</td></tr><tr><td>1</td><td>测试</td></tr></table>",
                        "table_structure_markdown": "| 序号 | 案例名称 |\n| --- | --- |\n| 1 | 测试 |",
                        "table_structure": {"pipeline": "PPStructureV3", "row_count": 2, "raw_results": [{"res": {}}]},
                        "lines": [{"text": "普通文本"}],
                        "image": {"width": 1000, "height": 800},
                        "config": {"table_recognition": True},
                    },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("engine.ocr_plugins.paddleocr.subprocess.run", fake_run)

    result = PaddleOcrPlugin().recognize(
        str(image_path),
        {
            "python": str(python_path),
            "runner": str(runner_path),
            "timeout_seconds": 5,
            "table_recognition": True,
            "table_recognition_pipeline": "PPStructureV3",
        },
    )

    assert result.text.startswith("| 序号 | 案例名称 |")
    assert "--table-recognition" in fake_run.command
    assert fake_run.command[fake_run.command.index("--table-recognition-pipeline") + 1] == "PPStructureV3"
    assert result.structured_data["markdown"] == "| 普通 |"
    assert result.structured_data["table_structure_markdown"].startswith("| 序号 |")
    assert result.structured_data["table_structure_html"].startswith("<table>")
    assert result.structured_data["table_structure"]["pipeline"] == "PPStructureV3"
    assert result.status == "success"
    assert result.quality_status == "usable"


def test_paddleocr_quality_falls_back_to_lines_when_table_structure_empty(monkeypatch, tmp_path):
    """表格结构识别为空时质量评估应回退普通 OCR 行数。"""
    from engine.ocr_plugins.paddleocr import PaddleOcrPlugin

    image_path = tmp_path / "table.png"
    image_path.write_bytes(b"fake-image")
    python_path = tmp_path / "python"
    runner_path = tmp_path / "runner.py"
    python_path.write_text("", encoding="utf-8")
    runner_path.write_text("", encoding="utf-8")

    def fake_run(command, check, capture_output, text, timeout):
        output_path = command[command.index("--output") + 1]
        from subprocess import CompletedProcess

        Path(output_path).write_text(
            json.dumps(
                {
                    "wall_seconds": 1.23,
                    "text": "普通文本内容足够长用于验证质量评估回退",
                    "table_markdown": "",
                    "table_structure_html": "",
                    "table_structure": {"pipeline": "PPStructureV3", "row_count": 0, "raw_results": []},
                    "lines": [{"text": "第一行"}, {"text": "第二行"}],
                    "image": {"width": 1000, "height": 800},
                    "config": {"table_recognition": True},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("engine.ocr_plugins.paddleocr.subprocess.run", fake_run)

    result = PaddleOcrPlugin().recognize(
        str(image_path),
        {
            "python": str(python_path),
            "runner": str(runner_path),
            "timeout_seconds": 5,
            "min_text_length": 5,
            "min_line_count": 2,
        },
    )

    assert result.status == "success"
    assert result.quality_status == "usable"


def test_paddleocr_short_text_requires_manual_review(monkeypatch, tmp_path):
    """PaddleOCR 短文本应标记为低置信度并要求人工复核。"""
    from engine.ocr_plugins.paddleocr import PaddleOcrPlugin

    image_path = tmp_path / "short.png"
    image_path.write_bytes(b"fake-image")
    python_path = tmp_path / "python"
    runner_path = tmp_path / "runner.py"
    python_path.write_text("", encoding="utf-8")
    runner_path.write_text("", encoding="utf-8")

    def fake_run(command, check, capture_output, text, timeout):
        output_path = command[command.index("--output") + 1]
        from subprocess import CompletedProcess

        Path(output_path).write_text(
            json.dumps(
                {
                    "wall_seconds": 0.12,
                    "text": "短文本",
                    "table_markdown": "",
                    "corrections": [],
                    "lines": [{"text": "短文本"}],
                    "image": {"width": 100, "height": 50},
                    "config": {"lang": "ch"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("engine.ocr_plugins.paddleocr.subprocess.run", fake_run)

    result = PaddleOcrPlugin().recognize(
        str(image_path),
        {
            "python": str(python_path),
            "runner": str(runner_path),
            "timeout_seconds": 5,
            "min_text_length": 20,
            "min_line_count": 2,
            "large_image_pixels": 200000,
        },
    )

    assert result.status == "success_low_confidence"
    assert result.quality_status == "manual_review_required"
    assert result.manual_review_required is True
    fields = result.to_item_fields()
    assert fields["ocr_quality_status"] == "manual_review_required"
    assert "text_too_short" in fields["ocr_quality_reasons"]


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
    monkeypatch.setattr(
        "engine.ocr_plugins.tesseract._detect_table_grid",
        lambda *args, **kwargs: {"rows": [0, 40, 100], "columns": [0, 80, 260]},
    )
    monkeypatch.setattr(
        "engine.ocr_plugins.tesseract._recognize_table_cells",
        lambda *args, **kwargs: [["序号", "数据集名称"], ["1", "企业登记数据集"]],
    )

    result = TesseractOcrPlugin().recognize(str(image_path), {"languages": ["chi_sim", "eng"], "psm": 6})

    assert result.status == "success"
    assert result.text == "序号 | 数据名称\n1 | 企业登记数据集"
    assert result.manual_review_required is False
    assert result.structured_data["words"][0]["text"] == "序号"
    assert result.structured_data["table_grid"]["rows"] == [0, 40, 100]
    assert result.structured_data["table_cells"][1] == ["1", "企业登记数据集"]


def test_tesseract_success_keeps_text_when_structured_data_fails(monkeypatch, tmp_path):
    """词块提取失败不应拖垮已成功的文本 OCR。"""
    from engine.ocr_plugins.tesseract import TesseractOcrPlugin

    image_path = tmp_path / "table.png"
    image_path.write_bytes(b"fake-image")
    monkeypatch.setattr("engine.ocr_plugins.tesseract._call_tesseract", lambda *args, **kwargs: "序号 | 数据名称")

    def raise_data_error(*args, **kwargs):
        raise RuntimeError("image_to_data failed")

    monkeypatch.setattr("engine.ocr_plugins.tesseract._call_tesseract_data", raise_data_error)

    result = TesseractOcrPlugin().recognize(str(image_path), {"languages": ["chi_sim", "eng"], "psm": 6})

    assert result.status == "success"
    assert result.text == "序号 | 数据名称"
    assert result.manual_review_required is False
    assert result.structured_data == {"words": [], "table_grid": {}, "table_cells": []}


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
    assert fields["ocr_quality_status"] == "usable"
    assert fields["ocr_quality_reasons"] == []
