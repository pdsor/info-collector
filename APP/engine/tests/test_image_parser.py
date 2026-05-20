"""图片 OCR 文本解析测试。"""

from engine.image_parser import parse_ocr_result, parse_ocr_text
from engine.ocr_plugins import OcrResult


def test_parse_table_text_maps_columns_to_business_fields():
    """表格 OCR 文本按表头映射为业务记录。"""
    text = "序号 | 数据名称 | 发布时间\n1 | 企业登记数据集 | 2026-01-05\n2 | 公共信用数据集 | 2026-01-06"
    config = {
        "mode": "table",
        "delimiters": ["|", "\t", ","],
        "column_mapping": {"序号": "id", "数据名称": "name", "发布时间": "publish_time"},
    }

    records, errors, semi_structured = parse_ocr_text(text, config)

    assert records == [
        {"id": "1", "name": "企业登记数据集", "publish_time": "2026-01-05", "ocr_text": "1 | 企业登记数据集 | 2026-01-05"},
        {"id": "2", "name": "公共信用数据集", "publish_time": "2026-01-06", "ocr_text": "2 | 公共信用数据集 | 2026-01-06"},
    ]
    assert errors == []
    assert semi_structured is False


def test_parse_key_value_text_maps_labels_to_business_fields():
    """键值 OCR 文本按字段映射为单条业务记录。"""
    text = "项目名称：智慧园区数据治理平台\n申报单位：某某科技有限公司\n所属行业：软件和信息技术服务业"
    config = {
        "mode": "key_value",
        "column_mapping": {"项目名称": "project_name", "申报单位": "applicant_unit", "所属行业": "industry"},
    }

    records, errors, semi_structured = parse_ocr_text(text, config)

    assert records == [{
        "project_name": "智慧园区数据治理平台",
        "applicant_unit": "某某科技有限公司",
        "industry": "软件和信息技术服务业",
        "ocr_text": text,
    }]
    assert errors == []
    assert semi_structured is False


def test_parse_unstructured_text_returns_manual_review_record():
    """无法解析时输出半结构化人工复核记录。"""
    records, errors, semi_structured = parse_ocr_text(
        "无法稳定拆分的 OCR 原文",
        {"mode": "table", "delimiters": ["|"], "column_mapping": {"标题": "title"}},
    )

    assert records == [{"title": "OCR 半结构化结果", "ocr_text": "无法稳定拆分的 OCR 原文"}]
    assert errors == ["未识别到表头或列数不一致"]
    assert semi_structured is True


def test_parse_ocr_result_groups_positioned_words_into_dataset_rows():
    """坐标 OCR 结果按表头位置聚合为数据集表格记录。"""
    ocr_result = OcrResult(
        plugin="tesseract",
        status="success",
        text="",
        structured_data={
            "words": [
                {"text": "序号", "left": 10, "top": 10, "width": 20, "height": 10},
                {"text": "数据集名称", "left": 70, "top": 10, "width": 70, "height": 10},
                {"text": "数据领域", "left": 220, "top": 10, "width": 60, "height": 10},
                {"text": "申报单位", "left": 330, "top": 10, "width": 60, "height": 10},
                {"text": "1", "left": 12, "top": 35, "width": 10, "height": 10},
                {"text": "水环境监测数据集", "left": 70, "top": 35, "width": 120, "height": 10},
                {"text": "自然资源", "left": 220, "top": 35, "width": 60, "height": 10},
                {"text": "武汉市生态环境局", "left": 330, "top": 35, "width": 80, "height": 10},
                {"text": "2", "left": 12, "top": 60, "width": 10, "height": 10},
                {"text": "车载红外高质量数据集", "left": 70, "top": 60, "width": 140, "height": 10},
                {"text": "交通运输", "left": 220, "top": 60, "width": 60, "height": 10},
                {"text": "湖北某公司", "left": 330, "top": 60, "width": 80, "height": 10},
            ]
        },
    )
    config = {
        "column_mapping": {"序号": "id", "数据集名称": "name", "数据领域": "category", "申报单位": "department"}
    }

    records, errors, semi_structured = parse_ocr_result(ocr_result, config)

    assert records == [
        {
            "id": "1",
            "name": "水环境监测数据集",
            "category": "自然资源",
            "department": "武汉市生态环境局",
            "ocr_text": "1 水环境监测数据集 自然资源 武汉市生态环境局",
        },
        {
            "id": "2",
            "name": "车载红外高质量数据集",
            "category": "交通运输",
            "department": "湖北某公司",
            "ocr_text": "2 车载红外高质量数据集 交通运输 湖北某公司",
        },
    ]
    assert errors == []
    assert semi_structured is False


def test_parse_ocr_result_falls_back_to_text_when_positioned_header_not_found():
    """坐标表头无法识别时应回退到文本解析。"""
    ocr_result = OcrResult(
        plugin="tesseract",
        status="success",
        text="序号 | 数据名称\n1 | 企业登记数据集",
        structured_data={
            "words": [
                {"text": "错误表头", "left": 10, "top": 10, "width": 40, "height": 10},
                {"text": "1", "left": 12, "top": 35, "width": 10, "height": 10},
                {"text": "企业登记数据集", "left": 70, "top": 35, "width": 100, "height": 10},
            ]
        },
    )
    config = {
        "mode": "table",
        "delimiters": ["|"],
        "column_mapping": {"序号": "id", "数据名称": "name"},
    }

    records, errors, semi_structured = parse_ocr_result(ocr_result, config)

    assert records == [{"id": "1", "name": "企业登记数据集", "ocr_text": "1 | 企业登记数据集"}]
    assert errors == []
    assert semi_structured is False


def test_parse_ocr_result_degrades_when_positioned_columns_are_ambiguous():
    """长字段跨列明显歧义时应安全降级，不静默产出错列记录。"""
    ocr_result = OcrResult(
        plugin="tesseract",
        status="success",
        text="无法稳定拆分的 OCR 原文",
        structured_data={
            "words": [
                {"text": "序号", "left": 10, "top": 10, "width": 20, "height": 10},
                {"text": "数据集名称", "left": 70, "top": 10, "width": 70, "height": 10},
                {"text": "数据领域", "left": 220, "top": 10, "width": 60, "height": 10},
                {"text": "申报单位", "left": 330, "top": 10, "width": 60, "height": 10},
                {"text": "1", "left": 12, "top": 35, "width": 10, "height": 10},
                {"text": "车载红外高质量数据集", "left": 150, "top": 35, "width": 110, "height": 10},
                {"text": "交通运输", "left": 220, "top": 35, "width": 60, "height": 10},
                {"text": "湖北某公司", "left": 330, "top": 35, "width": 80, "height": 10},
            ]
        },
    )
    config = {
        "column_mapping": {"序号": "id", "数据集名称": "name", "数据领域": "category", "申报单位": "department"}
    }

    records, errors, semi_structured = parse_ocr_result(ocr_result, config)

    assert records == [{"title": "OCR 半结构化结果", "ocr_text": "无法稳定拆分的 OCR 原文"}]
    assert errors == ["未识别到表头或列数不一致"]
    assert semi_structured is True
