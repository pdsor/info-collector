"""规则沙箱试采测试。"""


def test_preview_rule_returns_limited_governed_items_without_saving(tmp_path, monkeypatch):
    """试采返回限定条数，并且不写正式输出文件。"""
    from engine.engine import InfoCollectorEngine

    html = """
    <html><body>
      <article><h1>第一条</h1><a href="/a">链接</a></article>
      <article><h1>第二条</h1><a href="/b">链接</a></article>
    </body></html>
    """
    rule_path = tmp_path / "rule.yaml"
    rule_path.write_text(
        """
rule_id: "preview-rule"
source_id: "preview-source"
version: 1
status: DRAFT
source:
  platform: "preview"
  type: "html"
  url: "https://example.com"
list:
  items_path: "css:article"
extract:
  title: { selector: "h1", type: "text" }
  url: { selector: "a", type: "attribute", attribute: "href" }
output:
  fields: ["title", "url"]
  save_raw: false
governance:
  sanitize: true
""".strip(),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    engine = InfoCollectorEngine(dedup_db_path=":memory:", state_dir=str(output_dir))
    monkeypatch.setattr(engine.html_crawler, "fetch", lambda *args, **kwargs: html)

    result = engine.preview_rule(str(rule_path), limit=1)

    assert result["success"] is True
    assert result["status"] in {"success", "partial_success"}
    assert result["total_collected"] == 2
    assert result["preview_count"] == 1
    assert result["items"][0]["title"] == "第一条"
    assert not list(output_dir.glob("**/*.json"))

    engine.close()


def test_preview_rule_includes_ocr_summary_and_items(tmp_path, monkeypatch):
    """试采应走 OCR 插件链路并返回摘要。"""
    from engine.engine import InfoCollectorEngine
    from engine.ocr_plugins import OcrResult, register_ocr_plugin

    class PreviewOcrPlugin:
        name = "preview_ocr"

        def recognize(self, image_path: str, config: dict) -> OcrResult:
            return OcrResult(
                plugin=self.name,
                status="success",
                text="序号 | 数据名称\n1 | 企业登记数据集",
                error="",
                elapsed_seconds=0.01,
            )

    register_ocr_plugin(PreviewOcrPlugin())
    html = """
    <html><body>
      <article class="container hbgov-category-container">
        <div class="hbgov-article-content"><img src="/upload/table.png" alt="数据清单"></div>
      </article>
    </body></html>
    """
    rule_path = tmp_path / "ocr_rule.yaml"
    rule_path.write_text(
        """
rule_id: "preview-ocr-rule"
source_id: "preview-ocr-source"
version: 1
status: DRAFT
source:
  platform: "hubei_gov"
  type: "html"
  url: "https://www.hubei.gov.cn/path/article.shtml"
list:
  items_path: "css:article"
extract:
  article_text: { selector: ".hbgov-article-content", type: "text" }
image_extraction:
  enabled: true
  trigger:
    when_empty: false
    domains: ["hubei.gov.cn"]
    img_keywords: ["数据", "png"]
  images:
    selector: ".hbgov-article-content img"
    src_attribute: "src"
    include_alt: true
    max_images: 5
  download:
    dir_template: "__TMP__/{task_id}"
    retries: 1
    timeout_seconds: 3
    max_size_mb: 1
  ocr:
    plugin: "preview_ocr"
    languages: ["chi_sim", "eng"]
  parse:
    mode: "table"
    delimiters: ["|"]
    column_mapping:
      序号: "id"
      数据名称: "name"
output:
  fields: ["article_text", "id", "name", "ocr_plugin", "ocr_text", "source_img_url", "manual_review_required"]
  save_raw: false
governance:
  sanitize: true
  required_fields: ["article_text"]
  min_completeness: 0.1
""".replace("__TMP__", str(tmp_path)),
        encoding="utf-8",
    )
    engine = InfoCollectorEngine(dedup_db_path=":memory:", state_dir=str(tmp_path / "output"))
    monkeypatch.setattr(engine.html_crawler, "fetch", lambda *args, **kwargs: html)
    monkeypatch.setattr(
        "engine.image_extraction.ImageExtractionRunner.download_image",
        lambda *args, **kwargs: str(tmp_path / "table.png"),
    )

    result = engine.preview_rule(str(rule_path), limit=10)

    assert result["ocr_summary"]["triggered"] is True
    assert result["ocr_summary"]["plugin"] == "preview_ocr"
    assert result["ocr_summary"]["images_found"] == 1
    assert any(item.get("ocr_plugin") == "preview_ocr" for item in result["items"])
    assert any(item.get("source_img_url") == "https://www.hubei.gov.cn/upload/table.png" for item in result["items"])

    engine.close()

