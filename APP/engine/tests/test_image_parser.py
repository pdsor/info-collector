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

    assert records == [
        {
            "id": "1",
            "title": "OCR 半结构化结果",
            "ocr_text": "1 车载红外高质量数据集 交通运输 湖北某公司",
        }
    ]
    assert errors == ["第 1 行字段不完整"]
    assert semi_structured is True


def test_parse_ocr_result_keeps_incomplete_positioned_rows_for_review():
    """坐标行缺少关键字段时不能静默丢弃，应保留人工复核记录。"""
    ocr_result = OcrResult(
        plugin="tesseract",
        status="success",
        text="",
        structured_data={
            "words": [
                {"text": "序号", "left": 10, "top": 10, "width": 20, "height": 10},
                {"text": "数据集名称", "left": 70, "top": 10, "width": 70, "height": 10},
                {"text": "1", "left": 12, "top": 35, "width": 10, "height": 10},
                {"text": "企业登记数据集", "left": 70, "top": 35, "width": 100, "height": 10},
                {"text": "2", "left": 12, "top": 60, "width": 10, "height": 10},
            ]
        },
    )
    config = {"column_mapping": {"序号": "id", "数据集名称": "name"}}

    records, errors, semi_structured = parse_ocr_result(ocr_result, config)

    assert records == [
        {"id": "1", "name": "企业登记数据集", "ocr_text": "1 企业登记数据集"},
        {"id": "2", "title": "OCR 半结构化结果", "ocr_text": "2"},
    ]
    assert errors == ["第 2 行字段不完整"]
    assert semi_structured is True


def test_parse_ocr_result_handles_split_headers_and_inferred_id_column():
    """真实图片 OCR 中表头可能被拆词，序号列也可能缺少表头。"""
    ocr_result = OcrResult(
        plugin="tesseract",
        status="success",
        text="无法稳定拆分的 OCR 原文",
        structured_data={
            "words": [
                {"text": "数据", "left": 278, "top": 92, "width": 66, "height": 10},
                {"text": "集", "left": 359, "top": 92, "width": 19, "height": 10},
                {"text": "名", "left": 390, "top": 92, "width": 17, "height": 10},
                {"text": "称", "left": 421, "top": 92, "width": 23, "height": 10},
                {"text": "申报", "left": 1230, "top": 92, "width": 82, "height": 10},
                {"text": "单位", "left": 1311, "top": 86, "width": 49, "height": 10},
                {"text": "3", "left": 102, "top": 430, "width": 12, "height": 10},
                {"text": "智路", "left": 243, "top": 426, "width": 66, "height": 10},
                {"text": "交通运输", "left": 330, "top": 426, "width": 138, "height": 10},
                {"text": "四川", "left": 1146, "top": 451, "width": 72, "height": 10},
                {"text": "易方科技有限公司", "left": 1242, "top": 448, "width": 180, "height": 10},
                {"text": "4", "left": 100, "top": 584, "width": 12, "height": 10},
                {"text": "两点十分", "left": 223, "top": 581, "width": 180, "height": 10},
                {"text": "动画数据集", "left": 412, "top": 580, "width": 96, "height": 10},
                {"text": "武汉两点十分影视有限公司", "left": 1230, "top": 580, "width": 206, "height": 10},
            ]
        },
    )
    config = {
        "column_mapping": {"序号": "id", "数据集名称": "name", "申报单位": "department"}
    }

    records, errors, semi_structured = parse_ocr_result(ocr_result, config)

    assert records == [
        {
            "id": "3",
            "name": "智路 交通运输",
            "department": "四川 易方科技有限公司",
            "ocr_text": "3 智路 交通运输 四川 易方科技有限公司",
        },
        {
            "id": "4",
            "name": "两点十分 动画数据集",
            "department": "武汉两点十分影视有限公司",
            "ocr_text": "4 两点十分 动画数据集 武汉两点十分影视有限公司",
        },
    ]
    assert errors == []
    assert semi_structured is False


def test_parse_ocr_result_uses_table_grid_cells_when_available():
    """有表格网格时应按单元格边界聚合多行文本。"""
    ocr_result = OcrResult(
        plugin="tesseract",
        status="success",
        text="无法稳定拆分的 OCR 原文",
        structured_data={
            "table_grid": {
                "rows": [0, 40, 130, 260],
                "columns": [0, 80, 260, 420, 600],
            },
            "words": [
                {"text": "序号", "left": 20, "top": 10, "width": 30, "height": 10},
                {"text": "数据集", "left": 110, "top": 10, "width": 60, "height": 10},
                {"text": "名称", "left": 175, "top": 10, "width": 40, "height": 10},
                {"text": "行业领域", "left": 300, "top": 10, "width": 70, "height": 10},
                {"text": "申报单位", "left": 460, "top": 10, "width": 70, "height": 10},
                {"text": "1", "left": 35, "top": 75, "width": 10, "height": 10},
                {"text": "人群血小板", "left": 110, "top": 55, "width": 90, "height": 10},
                {"text": "全景多模态", "left": 115, "top": 80, "width": 90, "height": 10},
                {"text": "数据集", "left": 130, "top": 105, "width": 50, "height": 10},
                {"text": "医疗卫生", "left": 300, "top": 80, "width": 70, "height": 10},
                {"text": "武汉血液中心", "left": 455, "top": 80, "width": 100, "height": 10},
                {"text": "2", "left": 35, "top": 190, "width": 10, "height": 10},
                {"text": "基于高通量", "left": 105, "top": 155, "width": 90, "height": 10},
                {"text": "光谱流式", "left": 115, "top": 180, "width": 70, "height": 10},
                {"text": "诊断数据集", "left": 110, "top": 205, "width": 90, "height": 10},
                {"text": "医疗卫生", "left": 300, "top": 190, "width": 70, "height": 10},
                {"text": "华中科技大学", "left": 450, "top": 170, "width": 100, "height": 10},
                {"text": "同济医院", "left": 465, "top": 195, "width": 70, "height": 10},
            ],
        },
    )
    config = {
        "column_mapping": {"序号": "id", "数据集名称": "name", "行业领域": "category", "申报单位": "department"}
    }

    records, errors, semi_structured = parse_ocr_result(ocr_result, config)

    assert records == [
        {
            "id": "1",
            "name": "人群血小板 全景多模态 数据集",
            "category": "医疗卫生",
            "department": "武汉血液中心",
            "ocr_text": "1 人群血小板 全景多模态 数据集 医疗卫生 武汉血液中心",
        },
        {
            "id": "2",
            "name": "基于高通量 光谱流式 诊断数据集",
            "category": "医疗卫生",
            "department": "华中科技大学 同济医院",
            "ocr_text": "2 基于高通量 光谱流式 诊断数据集 医疗卫生 华中科技大学 同济医院",
        },
    ]
    assert errors == []
    assert semi_structured is False


def test_parse_ocr_result_uses_ocr_table_cells_with_column_order():
    """单元格 OCR 结果应按规则列顺序直接生成逐行记录。"""
    ocr_result = OcrResult(
        plugin="tesseract",
        status="success",
        text="",
        structured_data={
            "table_cells": [
                ["序号", "数据集名称", "数据集模态", "行业领域", "申报单位"],
                ["1", "人群血小板全景多模\n态数据集", "文本，图形图像，\n其他", "医疗卫生", "武汉血液中心"],
                ["2", "基于高通量光谱流式\n的 AML-MRD 诊断数据\n集", "其他", "医疗卫生", "华中科技大学同济医\n学院附属同济医院"],
            ],
        },
    )
    config = {
        "column_order": ["id", "name", "data_item", "category", "department"],
        "column_mapping": {"序号": "id", "数据集名称": "name", "数据集模态": "data_item", "行业领域": "category", "申报单位": "department"},
    }

    records, errors, semi_structured = parse_ocr_result(ocr_result, config)

    assert records == [
        {
            "id": "1",
            "name": "人群血小板全景多模 态数据集",
            "data_item": "文本，图形图像， 其他",
            "category": "医疗卫生",
            "department": "武汉血液中心",
            "ocr_text": "1 人群血小板全景多模 态数据集 文本，图形图像， 其他 医疗卫生 武汉血液中心",
        },
        {
            "id": "2",
            "name": "基于高通量光谱流式 的 AML-MRD 诊断数据 集",
            "data_item": "其他",
            "category": "医疗卫生",
            "department": "华中科技大学同济医 学院附属同济医院",
            "ocr_text": "2 基于高通量光谱流式 的 AML-MRD 诊断数据 集 其他 医疗卫生 华中科技大学同济医 学院附属同济医院",
        },
    ]
    assert errors == []
    assert semi_structured is False


def test_parse_ocr_result_skips_table_cell_rows_without_numeric_id():
    """单元格 OCR 中没有数字序号的跨页残留行不应作为名单记录输出。"""
    ocr_result = OcrResult(
        plugin="tesseract",
        status="success",
        text="",
        structured_data={
            "table_cells": [
                ["序号", "数据集名称", "数据集模态", "行业领域", "申报单位"],
                ["", "", "", "治理", ""],
                ["15", "水环境监测数据集", "视频，结构化", "绿色低碳，城市治理", "武汉市生态环境局"],
            ],
        },
    )
    config = {
        "column_order": ["id", "name", "data_item", "category", "department"],
        "column_mapping": {"序号": "id", "数据集名称": "name", "数据集模态": "data_item", "行业领域": "category", "申报单位": "department"},
    }

    records, errors, semi_structured = parse_ocr_result(ocr_result, config)

    assert records == [
        {
            "id": "15",
            "name": "水环境监测数据集",
            "data_item": "视频，结构化",
            "category": "绿色低碳，城市治理",
            "department": "武汉市生态环境局",
            "ocr_text": "15 水环境监测数据集 视频，结构化 绿色低碳，城市治理 武汉市生态环境局",
        }
    ]
    assert errors == []
    assert semi_structured is False


def test_parse_ocr_result_repairs_sequential_table_cell_ids():
    """连续名单表格中的序号 OCR 误识别应按行序修正。"""
    ocr_result = OcrResult(
        plugin="tesseract",
        status="success",
        text="",
        structured_data={
            "table_cells": [
                ["序号", "数据集名称"],
                ["1", "第一条数据集"],
                ["2", "第二条数据集"],
                ["$", "第三条数据集"],
                ["4", "第四条数据集"],
            ],
        },
    )
    config = {
        "column_order": ["id", "name"],
        "column_mapping": {"序号": "id", "数据集名称": "name"},
    }

    records, errors, semi_structured = parse_ocr_result(ocr_result, config)

    assert [record["id"] for record in records] == ["1", "2", "3", "4"]
    assert errors == []
    assert semi_structured is False
