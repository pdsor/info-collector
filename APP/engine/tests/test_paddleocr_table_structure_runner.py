"""PaddleOCR 表格结构 runner 测试。"""

import json
import sys
from types import SimpleNamespace

from PIL import Image

from run_paddleocr_table_structure_test import (
    _extract_table_markdown,
    _json_safe,
    main,
    _normalize_pipeline_result,
)


def test_json_safe_converts_unknown_objects():
    class Value:
        def __str__(self):
            return "value-object"

    assert _json_safe({"a": Value()}) == {"a": "value-object"}


def test_json_safe_recurses_into_tolist_result():
    class Value:
        def __str__(self):
            return "value-object"

    class Values:
        def tolist(self):
            return [{"a": Value()}]

    assert _json_safe(Values()) == [{"a": "value-object"}]


def test_normalize_pipeline_result_accepts_json_property():
    class Result:
        json = {"res": {"html": "<table></table>", "markdown": "| A |"}}

    payload = _normalize_pipeline_result(Result())

    assert payload["res"]["html"] == "<table></table>"
    assert payload["res"]["markdown"] == "| A |"


def test_extract_table_markdown_prefers_markdown_then_html():
    markdown_payload = {"res": {"markdown": "| 序号 |", "html": "<table></table>"}}
    html_payload = {"res": {"html": "<table><tr><td>序号</td></tr></table>"}}

    assert _extract_table_markdown([markdown_payload]) == "| 序号 |"
    assert _extract_table_markdown([html_payload]).startswith("<table>")


def test_extract_table_markdown_prefers_later_markdown_before_earlier_html():
    html_payload = {"res": {"html": "<table><tr><td>序号</td></tr></table>"}}
    markdown_payload = {"res": {"markdown": "| 序号 |"}}

    assert _extract_table_markdown([html_payload, markdown_payload]) == "| 序号 |"


def test_main_writes_outputs_and_creates_parent_directory(monkeypatch, tmp_path):
    captured = {}

    class Result:
        json = {"res": {"markdown": "| 序号 |"}}

    class FakePipeline:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def predict(self, image_path):
            captured["image_path"] = image_path
            return Result()

    image_path = tmp_path / "table.png"
    Image.new("RGB", (8, 4), color="white").save(image_path)
    output_path = tmp_path / "missing" / "result.json"
    home_path = tmp_path / "paddle-home"

    monkeypatch.setitem(
        sys.modules,
        "paddleocr",
        SimpleNamespace(TableRecognitionPipelineV2=FakePipeline),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_paddleocr_table_structure_test.py",
            str(image_path),
            "--output",
            str(output_path),
            "--home",
            str(home_path),
            "--limit-side-len",
            "123",
            "--preview-chars",
            "0",
        ],
    )

    assert main() == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert output_path.with_suffix(".md").read_text(encoding="utf-8") == "| 序号 |"
    assert payload["table_markdown"] == "| 序号 |"
    assert captured["image_path"] == str(image_path)
    assert captured["kwargs"]["text_det_limit_side_len"] == 123
    assert captured["kwargs"]["use_layout_detection"] is False
