"""图片 OCR 行专用输出测试。"""


def test_ocr_rows_only_excludes_article_item(tmp_path, monkeypatch):
    """OCR 行专用模式下不输出正文文章记录。"""
    from engine.engine import InfoCollectorEngine
    from engine.ocr_plugins import OcrResult, register_ocr_plugin

    class RowsOnlyOcrPlugin:
        name = "rows_only_ocr"

        def recognize(self, image_path: str, config: dict) -> OcrResult:
            return OcrResult(
                plugin=self.name,
                status="success",
                text="序号 | 数据名称\n1 | 企业登记数据集\n2 | 公共信用数据集",
                error="",
                elapsed_seconds=0.01,
            )

    register_ocr_plugin(RowsOnlyOcrPlugin())
    html = """
    <html><body>
      <article class="container hbgov-category-container">
        <h1>正文标题</h1>
        <div class="hbgov-article-content"><img src="/upload/table.png" alt="数据清单"></div>
      </article>
    </body></html>
    """
    rule = {
        "rule_id": "ocr-rows-only",
        "source_id": "ocr-rows-only-source",
        "version": 1,
        "status": "DRAFT",
        "source": {
            "platform": "hubei_gov",
            "type": "html",
            "url": "https://www.hubei.gov.cn/path/article.shtml",
        },
        "list": {"items_path": "css:article"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "image_extraction": {
            "enabled": True,
            "output_mode": "ocr_rows_only",
            "trigger": {"domains": ["hubei.gov.cn"], "img_keywords": ["数据", "png"]},
            "images": {
                "selector": ".hbgov-article-content img",
                "src_attribute": "src",
                "include_alt": True,
                "max_images": 5,
            },
            "download": {
                "dir_template": str(tmp_path / "{task_id}"),
                "retries": 1,
                "timeout_seconds": 3,
                "max_size_mb": 1,
            },
            "ocr": {"plugin": "rows_only_ocr"},
            "parse": {
                "mode": "table",
                "delimiters": ["|"],
                "column_mapping": {"序号": "id", "数据名称": "name"},
            },
        },
    }
    engine = InfoCollectorEngine(dedup_db_path=":memory:", state_dir=str(tmp_path / "output"))
    monkeypatch.setattr(engine.html_crawler, "fetch", lambda *args, **kwargs: html)
    monkeypatch.setattr(
        "engine.image_extraction.ImageExtractionRunner.download_image",
        lambda *args, **kwargs: str(tmp_path / "table.png"),
    )

    try:
        items = engine.crawl(rule)
    finally:
        engine.close()

    assert len(items) == 2
    assert [item["name"] for item in items] == ["企业登记数据集", "公共信用数据集"]
    assert all(item.get("title") != "正文标题" for item in items)
