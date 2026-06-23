import json
import sys
from textwrap import dedent
from types import SimpleNamespace

from PIL import Image

from run_paddleocr_image_test import (
    _extract_table_markdown,
    _html_table_to_markdown,
    _run_table_recognition,
    _table_markdown_from_lines,
)


def line(text, x, y):
    return {
        "text": text,
        "score": 0.99,
        "box": [[x - 5, y - 5], [x + 5, y - 5], [x + 5, y + 5], [x - 5, y + 5]],
    }


def test_table_markdown_has_real_newlines_and_repairs_first_sequence_id():
    lines = [
        line("序号", 40, 20),
        line("案例名称", 190, 20),
        line("牵头单位", 430, 20),
        line("参与单位", 610, 20),
        line("11", 40, 60),
        line("第一条案例", 190, 60),
        line("第一牵头单位", 430, 60),
        line("第一参与单位", 610, 60),
        line("2", 40, 100),
        line("第二条案例", 190, 100),
        line("第二牵头单位", 430, 100),
        line("第二参与单位", 610, 100),
    ]

    markdown, corrections = _table_markdown_from_lines(lines, image_width=686)

    assert markdown.splitlines() == [
        "| 序号 | 案例名称 | 牵头单位 | 参与单位 |",
        "| --- | --- | --- | --- |",
        "| 1 | 第一条案例 | 第一牵头单位 | 第一参与单位 |",
        "| 2 | 第二条案例 | 第二牵头单位 | 第二参与单位 |",
    ]
    assert corrections == [
        {"row": "1", "cell": "0", "source": "11", "target": "1", "reason": "连续序号纠错"}
    ]


def test_table_markdown_does_not_apply_word_specific_corrections():
    lines = [
        line("序号", 40, 20),
        line("案例名称", 190, 20),
        line("牵头单位", 430, 20),
        line("参与单位", 610, 20),
        line("1", 40, 60),
        line("测试案例", 190, 60),
        line("测试单位", 430, 60),
        line("某某科技有限公", 610, 60),
        line("2", 40, 100),
        line("第二案例", 190, 100),
        line("第二单位", 430, 100),
        line("司、其他单位", 610, 100),
    ]

    markdown, corrections = _table_markdown_from_lines(lines, image_width=686)

    assert "某某科技有限公" in markdown
    assert "司、其他单位" in markdown
    assert "某某科技有限公司" not in markdown
    assert not any(item["reason"] == "固定词替换" for item in corrections)


def test_table_markdown_keeps_real_row_eleven_when_sequence_continues_to_twelve():
    lines = [
        line("序号", 40, 20),
        line("案例名称", 190, 20),
        line("牵头单位", 430, 20),
        line("参与单位", 610, 20),
        line("11", 40, 60),
        line("第十一条案例", 190, 60),
        line("第十一牵头单位", 430, 60),
        line("第十一参与单位", 610, 60),
        line("12", 40, 100),
        line("第十二条案例", 190, 100),
        line("第十二牵头单位", 430, 100),
        line("第十二参与单位", 610, 100),
    ]

    markdown, corrections = _table_markdown_from_lines(lines, image_width=686)

    assert "| 11 | 第十一条案例 | 第十一牵头单位 | 第十一参与单位 |" in markdown
    assert "| 12 | 第十二条案例 | 第十二牵头单位 | 第十二参与单位 |" in markdown
    assert corrections == []


def test_extract_table_markdown_reads_paddlex_table_res_list_pred_html():
    payload = {
        "res": {
            "table_res_list": [
                {"pred_html": "<html><body><table><tr><td>序号</td></tr></table></body></html>"}
            ]
        }
    }

    assert _extract_table_markdown([payload]).startswith("<html>")


def test_html_table_to_markdown_converts_structure_html():
    html = dedent(
        """
        <html><body><table>
        <tr><td>序号</td><td>案例名称</td></tr>
        <tr><td>1</td><td>测试|案例</td></tr>
        </table></body></html>
        """
    )

    assert _html_table_to_markdown(html).splitlines() == [
        "| 序号 | 案例名称 |",
        "| --- | --- |",
        "| 1 | 测试\\|案例 |",
    ]


def test_run_table_recognition_supports_ppstructurev3(monkeypatch, tmp_path):
    captured = {}

    class Result:
        json = {
            "res": {
                "table_res_list": [
                    {
                        "pred_html": (
                            "<html><body><table><tr><td>序号</td></tr>"
                            "<tr><td>1</td></tr></table></body></html>"
                        )
                    }
                ]
            }
        }

    class FakePipeline:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

        def predict(self, image_path):
            captured["image_path"] = image_path
            return [Result()]

    image_path = tmp_path / "table.png"
    Image.new("RGB", (8, 4), color="white").save(image_path)
    monkeypatch.setitem(
        sys.modules,
        "paddleocr",
        SimpleNamespace(PPStructureV3=FakePipeline),
    )

    html, markdown, structure = _run_table_recognition(
        image_path=image_path,
        pipeline_name="PPStructureV3",
        limit_side_len=960,
    )

    assert html.startswith("<html>")
    assert markdown.splitlines()[0] == "| 序号 |"
    assert structure["pipeline"] == "PPStructureV3"
    assert structure["row_count"] == 1
    assert structure["raw_results"][0]["res"]["table_res_list"][0]["pred_html"].startswith("<html>")
    assert captured["image_path"] == str(image_path)
