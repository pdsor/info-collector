"""图片采集扩展链路测试。"""

from engine.image_extraction import ImageExtractionRunner
from engine.ocr_plugins import OcrResult, register_ocr_plugin


class FakeImageOcrPlugin:
    name = "fake_image_ocr"

    def recognize(self, image_path: str, config: dict) -> OcrResult:
        return OcrResult(
            plugin=self.name,
            status="success",
            text="序号 | 数据名称\n1 | 企业登记数据集",
            error="",
            elapsed_seconds=0.01,
        )


class EmptyImageOcrPlugin:
    name = "empty_image_ocr"

    def recognize(self, image_path: str, config: dict) -> OcrResult:
        return OcrResult(plugin=self.name, status="empty", text="", error="", elapsed_seconds=0.01)


class PositionedImageOcrPlugin:
    name = "positioned_image_ocr"

    def recognize(self, image_path: str, config: dict) -> OcrResult:
        return OcrResult(
            plugin=self.name,
            status="success",
            text="无法稳定拆分的 OCR 原文",
            error="",
            elapsed_seconds=0.01,
            structured_data={
                "words": [
                    {"text": "序号", "left": 10, "top": 10, "width": 20, "height": 10},
                    {"text": "数据集名称", "left": 70, "top": 10, "width": 70, "height": 10},
                    {"text": "数据领域", "left": 220, "top": 10, "width": 60, "height": 10},
                    {"text": "申报单位", "left": 330, "top": 10, "width": 60, "height": 10},
                    {"text": "1", "left": 12, "top": 35, "width": 8, "height": 10},
                    {"text": "水环境监测数据集", "left": 70, "top": 35, "width": 110, "height": 10},
                    {"text": "自然资源", "left": 220, "top": 35, "width": 55, "height": 10},
                    {"text": "武汉市生态环境局", "left": 330, "top": 35, "width": 120, "height": 10},
                ]
            },
        )


class PartialPositionedImageOcrPlugin:
    name = "partial_positioned_image_ocr"

    def recognize(self, image_path: str, config: dict) -> OcrResult:
        return OcrResult(
            plugin=self.name,
            status="success",
            text="序号 数据集名称",
            error="",
            elapsed_seconds=0.01,
            structured_data={
                "words": [
                    {"text": "序号", "left": 10, "top": 10, "width": 20, "height": 10},
                    {"text": "数据集名称", "left": 70, "top": 10, "width": 70, "height": 10},
                    {"text": "1", "left": 12, "top": 35, "width": 8, "height": 10},
                    {"text": "企业登记数据集", "left": 70, "top": 35, "width": 100, "height": 10},
                    {"text": "2", "left": 12, "top": 60, "width": 8, "height": 10},
                ]
            },
        )


class ResetIdImageOcrPlugin:
    name = "reset_id_image_ocr"
    calls = 0

    def recognize(self, image_path: str, config: dict) -> OcrResult:
        ResetIdImageOcrPlugin.calls += 1
        if ResetIdImageOcrPlugin.calls == 1:
            cells = [["序号", "数据集名称"], ["1", "第一条"], ["2", "第二条"]]
        else:
            cells = [["序号", "数据集名称"], ["1", "第三条"], ["2", "第四条"]]
        return OcrResult(
            plugin=self.name,
            status="success",
            text="序号 数据集名称",
            error="",
            elapsed_seconds=0.01,
            structured_data={"table_cells": cells},
        )


def _rule(tmp_path, plugin="fake_image_ocr"):
    return {
        "source": {"url": "https://www.hubei.gov.cn/path/article.shtml", "platform": "hubei_gov"},
        "image_extraction": {
            "enabled": True,
            "trigger": {"when_empty": False, "domains": ["hubei.gov.cn"], "img_keywords": ["数据", "png"]},
            "images": {"selector": ".hbgov-article-content img", "src_attribute": "src", "include_alt": True, "max_images": 5},
            "download": {"dir_template": str(tmp_path / "{task_id}"), "retries": 1, "timeout_seconds": 3, "max_size_mb": 1},
            "ocr": {"plugin": plugin, "languages": ["chi_sim", "eng"], "psm": 6},
            "parse": {"mode": "table", "delimiters": ["|"], "column_mapping": {"序号": "id", "数据名称": "name", "数据集名称": "name"}},
        },
    }


def test_image_extraction_uses_configured_ocr_plugin(monkeypatch, tmp_path):
    """图片扩展通过插件注册表调用指定 OCR 插件。"""
    register_ocr_plugin(FakeImageOcrPlugin())
    html = '<div class="hbgov-article-content"><img src="/upload/table.png" alt="数据清单"></div>'

    class FakeResponse:
        headers = {"content-type": "image/png", "content-length": "4"}
        content = b"fake"

        def raise_for_status(self):
            return None

    monkeypatch.setattr("engine.image_extraction.requests.get", lambda *args, **kwargs: FakeResponse())

    records = ImageExtractionRunner(_rule(tmp_path)).extract(html, [], page_url="https://www.hubei.gov.cn/path/article.shtml")

    assert records[0]["id"] == "1"
    assert records[0]["name"] == "企业登记数据集"
    assert records[0]["ocr_plugin"] == "fake_image_ocr"
    assert records[0]["ocr_engine"] == "fake_image_ocr"
    assert records[0]["source_img_url"] == "https://www.hubei.gov.cn/upload/table.png"
    assert records[0]["manual_review_required"] is False


def test_image_extraction_returns_manual_review_record_when_plugin_text_empty(monkeypatch, tmp_path):
    """OCR 插件返回空文本时仍输出图片来源和人工复核记录。"""
    register_ocr_plugin(EmptyImageOcrPlugin())
    html = '<div class="hbgov-article-content"><img src="table.jpg" alt="附件表"></div>'

    class FakeResponse:
        headers = {"content-type": "image/jpeg", "content-length": "4"}
        content = b"fake"

        def raise_for_status(self):
            return None

    monkeypatch.setattr("engine.image_extraction.requests.get", lambda *args, **kwargs: FakeResponse())

    records = ImageExtractionRunner(_rule(tmp_path, plugin="empty_image_ocr")).extract(
        html,
        [],
        page_url="https://www.hubei.gov.cn/path/article.shtml",
    )

    assert records[0]["title"] == "OCR 半结构化结果"
    assert records[0]["source_img_url"] == "https://www.hubei.gov.cn/path/table.jpg"
    assert records[0]["ocr_plugin"] == "empty_image_ocr"
    assert records[0]["manual_review_required"] is True
    assert records[0]["ocr_status"] == "empty"


def test_image_extraction_prefers_positioned_ocr_result(monkeypatch, tmp_path):
    """带坐标词块的 OCR 结果应优先走坐标解析。"""
    register_ocr_plugin(PositionedImageOcrPlugin())
    html = '<div class="hbgov-article-content"><img src="/upload/table.png" alt="数据清单"></div>'

    class FakeResponse:
        headers = {"content-type": "image/png", "content-length": "4"}
        content = b"fake"

        def raise_for_status(self):
            return None

    monkeypatch.setattr("engine.image_extraction.requests.get", lambda *args, **kwargs: FakeResponse())
    rule = _rule(tmp_path, plugin="positioned_image_ocr")
    rule["image_extraction"]["parse"]["column_mapping"].update({"数据领域": "category", "申报单位": "department"})

    records = ImageExtractionRunner(rule).extract(html, [], page_url="https://www.hubei.gov.cn/path/article.shtml")

    assert records[0]["id"] == "1"
    assert records[0]["name"] == "水环境监测数据集"
    assert records[0]["category"] == "自然资源"
    assert records[0]["department"] == "武汉市生态环境局"
    assert records[0]["ocr_text"] == "1 水环境监测数据集 自然资源 武汉市生态环境局"
    assert records[0]["manual_review_required"] is False
    assert records[0]["semi_structured"] is False


def test_image_extraction_marks_parse_errors_for_review(monkeypatch, tmp_path):
    """存在解析错误时记录应进入人工复核。"""
    register_ocr_plugin(PartialPositionedImageOcrPlugin())
    html = '<div class="hbgov-article-content"><img src="/upload/table.png" alt="数据清单"></div>'

    class FakeResponse:
        headers = {"content-type": "image/png", "content-length": "4"}
        content = b"fake"

        def raise_for_status(self):
            return None

    monkeypatch.setattr("engine.image_extraction.requests.get", lambda *args, **kwargs: FakeResponse())
    records = ImageExtractionRunner(_rule(tmp_path, plugin="partial_positioned_image_ocr")).extract(
        html,
        [],
        page_url="https://www.hubei.gov.cn/path/article.shtml",
    )

    assert records[0]["name"] == "企业登记数据集"
    assert records[0]["manual_review_required"] is True
    assert records[0]["semi_structured"] is True
    assert records[0]["parse_errors"] == ["第 2 行字段不完整"]
    assert records[1]["title"] == "OCR 半结构化结果"
    assert records[1]["manual_review_required"] is True


def test_image_extraction_can_renumber_rows_across_images(monkeypatch, tmp_path):
    """多张图片承载同一张名单时可按输出顺序全局重编号。"""
    ResetIdImageOcrPlugin.calls = 0
    register_ocr_plugin(ResetIdImageOcrPlugin())
    html = """
    <div class="hbgov-article-content">
      <img src="/upload/table-1.png" alt="数据清单">
      <img src="/upload/table-2.png" alt="数据清单">
    </div>
    """

    class FakeResponse:
        headers = {"content-type": "image/png", "content-length": "4"}
        content = b"fake"

        def raise_for_status(self):
            return None

    monkeypatch.setattr("engine.image_extraction.requests.get", lambda *args, **kwargs: FakeResponse())
    rule = _rule(tmp_path, plugin="reset_id_image_ocr")
    rule["image_extraction"]["parse"]["column_order"] = ["id", "name"]
    rule["image_extraction"]["parse"]["renumber_rows"] = True

    records = ImageExtractionRunner(rule).extract(html, [], page_url="https://www.hubei.gov.cn/path/article.shtml")

    assert [record["id"] for record in records] == ["1", "2", "3", "4"]
    assert [record["name"] for record in records] == ["第一条", "第二条", "第三条", "第四条"]
