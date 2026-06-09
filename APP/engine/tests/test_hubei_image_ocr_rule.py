"""NDA 图片 OCR 规则配置测试。"""

from pathlib import Path

import yaml


def test_nda_rule_enables_paddleocr_image_ocr():
    """NDA 规则应启用 PaddleOCR 图片识别。"""
    rule_path = Path(__file__).resolve().parents[1] / "rules/数据要素/nda_gov_data_element_cases.yaml"
    rule = yaml.safe_load(rule_path.read_text(encoding="utf-8"))

    assert rule["archive"]["image_ocr"]["enabled"] is True
    assert rule["archive"]["image_ocr"]["ocr"]["plugin"] == "paddleocr"
