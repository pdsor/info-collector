"""湖北图片 OCR 规则配置测试。"""

from pathlib import Path

import yaml


def test_hubei_image_ocr_rule_outputs_only_ocr_rows():
    """湖北图片 OCR 规则应声明只输出图片表格行。"""
    rule_path = Path(__file__).resolve().parents[1] / "rules/数据要素/hubei_gov_image_ocr_article.yaml"
    rule = yaml.safe_load(rule_path.read_text(encoding="utf-8"))

    assert rule["image_extraction"]["output_mode"] == "ocr_rows_only"
    assert rule["governance"]["required_fields"] == ["id", "name"]
