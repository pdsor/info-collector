# 图片 OCR 表格逐行采集实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让湖北省政府图片表格规则输出“第三批湖北省高质量数据集名单”的逐行结构化记录，并在图片模式下不保留正文文章记录。

**Architecture:** 在现有图片 OCR 链路上增加 `output_mode: ocr_rows_only`，由引擎控制正文记录与 OCR 记录的互斥输出。Tesseract 插件补充可选的版面词块数据，`image_parser.py` 优先用版面词块按坐标重建表格行，失败时再保留现有文本分隔符解析和人工复核降级。

**Tech Stack:** Python、pytest、Click、parsel、requests、Pillow、pytesseract、现有 `InfoCollectorEngine`、`ImageExtractionRunner`、`GovernancePipeline`、Rule v2 YAML。

---

## 文件结构

- Modify: `APP/engine/engine/ocr_plugins/base.py`
  - 给 `OcrResult` 增加 `structured_data`，用于承载 OCR 词块和后续插件元数据。
- Modify: `APP/engine/engine/ocr_plugins/tesseract.py`
  - 增加 `_call_tesseract_data()`，读取 `pytesseract.image_to_data()` 的词块坐标。
- Modify: `APP/engine/engine/image_parser.py`
  - 新增 `parse_ocr_result()`；保留 `parse_ocr_text()` 兼容现有测试。
  - 新增坐标表格解析，按行首序号拆分业务记录。
- Modify: `APP/engine/engine/image_extraction.py`
  - 调用 `parse_ocr_result()`，并让字段不完整的行记录进入人工复核。
- Modify: `APP/engine/engine/engine.py`
  - 在 `_append_image_extraction_items()` 支持 `output_mode: ocr_rows_only`，只返回 OCR 记录。
- Modify: `APP/engine/engine/rule_parser.py`
  - 校验 `image_extraction.output_mode` 只能是 `append` 或 `ocr_rows_only`。
- Modify: `APP/engine/engine_cli.py`
  - `run-rule --format=json` 返回 `output_path`。
- Modify: `APP/engine/rules/数据要素/hubei_gov_image_ocr_article.yaml`
  - 设置 `image_extraction.output_mode: "ocr_rows_only"`。
  - 调整治理必填字段为 `id`、`name`。
- Test: `APP/engine/tests/test_image_parser.py`
- Test: `APP/engine/tests/test_ocr_plugins.py`
- Test: `APP/engine/tests/test_image_extraction.py`
- Test: `APP/engine/tests/test_rule_preview.py`
- Test: `APP/engine/tests/test_engine_cli.py`

---

### Task 1: OCR 结果承载版面词块

**Files:**
- Modify: `APP/engine/engine/ocr_plugins/base.py`
- Modify: `APP/engine/engine/ocr_plugins/tesseract.py`
- Test: `APP/engine/tests/test_ocr_plugins.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_ocr_plugins.py` 末尾追加：

```python
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
```

并在 `test_tesseract_success_returns_text()` 中补充模拟和断言：

```python
    monkeypatch.setattr(
        "engine.ocr_plugins.tesseract._call_tesseract_data",
        lambda *args, **kwargs: [{"text": "序号", "left": 10, "top": 20, "width": 30, "height": 12, "conf": 95.0}],
    )

    assert result.structured_data["words"][0]["text"] == "序号"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_ocr_plugins.py -q`

Expected: FAIL，提示 `OcrResult.__init__()` 不接受 `structured_data`，或 `result.structured_data` 不存在。

- [ ] **Step 3: 实现最小代码**

在 `APP/engine/engine/ocr_plugins/base.py` 中修改：

```python
@dataclass
class OcrResult:
    """OCR 插件统一结果。"""

    plugin: str
    status: str
    text: str = ""
    error: str = ""
    elapsed_seconds: float = 0.0
    structured_data: dict | None = None
```

`to_item_fields()` 保持不返回 `structured_data`。

在 `APP/engine/engine/ocr_plugins/tesseract.py` 中新增：

```python
def _call_tesseract_data(image_path: str, languages: list[str], psm: int, preprocess: dict) -> list[dict]:
    """调用 pytesseract，返回带坐标的词块。"""
    from PIL import Image
    import pytesseract

    image = _prepare_image(image_path, preprocess)
    lang = "+".join(languages or ["chi_sim", "eng"])
    config = f"--psm {int(psm or 6)}"
    data = pytesseract.image_to_data(image, lang=lang, config=config, output_type=pytesseract.Output.DICT)
    words = []
    for index, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text or "").strip()
        if not text:
            continue
        words.append({
            "text": text,
            "left": int(data["left"][index]),
            "top": int(data["top"][index]),
            "width": int(data["width"][index]),
            "height": int(data["height"][index]),
            "conf": float(data["conf"][index]) if str(data["conf"][index]).replace(".", "", 1).lstrip("-").isdigit() else -1.0,
        })
    return words
```

同时把 `_call_tesseract()` 中的图片预处理抽成 `_prepare_image()`：

```python
def _prepare_image(image_path: str, preprocess: dict):
    """按规则配置预处理图片。"""
    from PIL import Image

    image = Image.open(image_path)
    resize_ratio = float((preprocess or {}).get("resize_ratio") or 1)
    if resize_ratio > 1:
        image = image.resize((int(image.width * resize_ratio), int(image.height * resize_ratio)))
    if (preprocess or {}).get("grayscale"):
        image = image.convert("L")
    if (preprocess or {}).get("threshold"):
        image = image.point(lambda value: 255 if value > 180 else 0)
    return image
```

并在 `TesseractOcrPlugin.recognize()` 成功分支中传入：

```python
            languages = (config or {}).get("languages") or ["chi_sim", "eng"]
            psm = int((config or {}).get("psm") or 6)
            preprocess = (config or {}).get("preprocess") or {}
            text = _call_tesseract(image_path, languages, psm, preprocess).strip()
            words = _call_tesseract_data(image_path, languages, psm, preprocess)
            status = "empty" if text == "" else "success"
            return OcrResult(
                plugin=self.name,
                status=status,
                text=text,
                error="",
                elapsed_seconds=round(time.time() - started_at, 4),
                structured_data={"words": words},
            )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_ocr_plugins.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/ocr_plugins/base.py APP/engine/engine/ocr_plugins/tesseract.py APP/engine/tests/test_ocr_plugins.py
git commit -m "增加OCR版面词块结果"
```

---

### Task 2: 按 OCR 版面词块拆分业务行

**Files:**
- Modify: `APP/engine/engine/image_parser.py`
- Test: `APP/engine/tests/test_image_parser.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_image_parser.py` 追加：

```python
from engine.ocr_plugins import OcrResult
from engine.image_parser import parse_ocr_result


def test_parse_ocr_result_groups_positioned_words_into_dataset_rows():
    """真实 OCR 词块按序号行重建为数据集记录。"""
    result = OcrResult(
        plugin="fake",
        status="success",
        text="第三批湖北省高质量数据集名单\n序号 数据集名称 数据领域 申报单位\n1 水环境监测数据集 自然资源 武汉市生态环境局\n2 车载红外高质量数据集 交通运输 湖北某公司",
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
                {"text": "2", "left": 12, "top": 60, "width": 8, "height": 10},
                {"text": "车载红外高质量数据集", "left": 70, "top": 60, "width": 130, "height": 10},
                {"text": "交通运输", "left": 220, "top": 60, "width": 55, "height": 10},
                {"text": "湖北某公司", "left": 330, "top": 60, "width": 90, "height": 10},
            ]
        },
    )
    config = {
        "mode": "table",
        "column_mapping": {
            "序号": "id",
            "数据集名称": "name",
            "数据领域": "category",
            "申报单位": "department",
        },
    }

    records, errors, semi_structured = parse_ocr_result(result, config)

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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_parser.py -q`

Expected: FAIL，提示 `parse_ocr_result` 不存在。

- [ ] **Step 3: 实现最小代码**

在 `APP/engine/engine/image_parser.py` 中新增以下函数，并保持原 `parse_ocr_text()` 不变：

```python
def _word_rows(words: list[dict]) -> list[list[dict]]:
    """按纵向位置把 OCR 词块归并为行。"""
    rows: list[list[dict]] = []
    for word in sorted(words, key=lambda item: (int(item.get("top", 0)), int(item.get("left", 0)))):
        top = int(word.get("top", 0))
        height = max(1, int(word.get("height", 10) or 10))
        matched = None
        for row in rows:
            row_top = int(row[0].get("top", 0))
            row_height = max(1, int(row[0].get("height", 10) or 10))
            if abs(top - row_top) <= max(height, row_height) * 0.7:
                matched = row
                break
        if matched is None:
            rows.append([word])
        else:
            matched.append(word)
    return [sorted(row, key=lambda item: int(item.get("left", 0))) for row in rows]


def _row_text(row: list[dict]) -> str:
    """把一行 OCR 词块合并为可审计原文。"""
    return " ".join(str(word.get("text", "")).strip() for word in row if str(word.get("text", "")).strip())


def _is_id_text(text: str) -> bool:
    """识别表格序号。"""
    return bool(re.fullmatch(r"\d{1,3}", str(text or "").strip()))


def _build_column_ranges(header_row: list[dict], mapping: dict) -> list[tuple[str, int, int]]:
    """根据表头词块生成字段横向范围。"""
    headers = []
    for word in header_row:
        label = str(word.get("text", "")).strip()
        target = mapping.get(label)
        if target:
            left = int(word.get("left", 0))
            width = int(word.get("width", 0) or 0)
            headers.append((target, left, left + width))
    if not headers:
        return []
    headers.sort(key=lambda item: item[1])
    ranges = []
    for index, (target, left, right) in enumerate(headers):
        start = 0 if index == 0 else (headers[index - 1][2] + left) // 2
        end = 10**9 if index == len(headers) - 1 else (right + headers[index + 1][1]) // 2
        ranges.append((target, start, end))
    return ranges


def _parse_positioned_table(ocr_result, config: dict) -> tuple[list[dict], list[str], bool] | None:
    """按 OCR 坐标解析表格。"""
    words = ((getattr(ocr_result, "structured_data", None) or {}).get("words") or [])
    if not words:
        return None
    mapping = config.get("column_mapping") or {}
    rows = _word_rows(words)
    header_index = None
    column_ranges = []
    for index, row in enumerate(rows):
        column_ranges = _build_column_ranges(row, mapping)
        if any(target == "id" for target, _, _ in column_ranges) and any(target == "name" for target, _, _ in column_ranges):
            header_index = index
            break
    if header_index is None:
        return None

    records = []
    errors = []
    for row in rows[header_index + 1:]:
        if not row:
            continue
        first_text = str(row[0].get("text", "")).strip()
        if not _is_id_text(first_text):
            if records:
                records[-1]["ocr_text"] = f"{records[-1]['ocr_text']} {_row_text(row)}".strip()
            continue
        record = {"ocr_text": _row_text(row)}
        for target, start, end in column_ranges:
            values = [
                str(word.get("text", "")).strip()
                for word in row
                if start <= int(word.get("left", 0)) < end and str(word.get("text", "")).strip()
            ]
            if values:
                record[target] = "".join(values) if target in {"name", "department"} else " ".join(values)
        if not record.get("id"):
            record["id"] = first_text
        if not record.get("name"):
            errors.append(f"第 {record.get('id', '?')} 行字段不完整")
        records.append(record)

    if not records:
        return None
    return records, errors, bool(errors)


def parse_ocr_result(ocr_result, config: dict) -> tuple[list[dict], list[str], bool]:
    """解析 OCR 结果，优先使用坐标词块，失败时回退到纯文本解析。"""
    positioned = _parse_positioned_table(ocr_result, config or {})
    if positioned is not None:
        return positioned
    return parse_ocr_text(getattr(ocr_result, "text", ""), config or {})
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_parser.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/image_parser.py APP/engine/tests/test_image_parser.py
git commit -m "支持OCR坐标表格逐行解析"
```

---

### Task 3: 图片链路使用 OCR 结果解析并标记不完整行

**Files:**
- Modify: `APP/engine/engine/image_extraction.py`
- Test: `APP/engine/tests/test_image_extraction.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_image_extraction.py` 追加：

```python
class PositionedImageOcrPlugin:
    name = "positioned_image_ocr"

    def recognize(self, image_path: str, config: dict) -> OcrResult:
        return OcrResult(
            plugin=self.name,
            status="success",
            text="序号 数据集名称 数据领域 申报单位\n1 水环境监测数据集 自然资源 武汉市生态环境局",
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


def test_image_extraction_uses_positioned_ocr_rows(monkeypatch, tmp_path):
    """图片扩展应把 OCR 坐标表格拆成业务行。"""
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
    assert records[0]["manual_review_required"] is False
    assert records[0]["semi_structured"] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_extraction.py -q`

Expected: FAIL，返回半结构化记录或缺少 `category`。

- [ ] **Step 3: 实现最小代码**

在 `APP/engine/engine/image_extraction.py` 顶部修改导入：

```python
from .image_parser import parse_ocr_result
```

把 `extract()` 中：

```python
                parsed_records, parse_errors, semi_structured = parse_ocr_text(
                    ocr_result.text,
                    self.config.get("parse") or {},
                )
```

替换为：

```python
                parsed_records, parse_errors, semi_structured = parse_ocr_result(
                    ocr_result,
                    self.config.get("parse") or {},
                )
```

同时删除未使用的 `parse_ocr_text` 导入。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_extraction.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/image_extraction.py APP/engine/tests/test_image_extraction.py
git commit -m "图片OCR链路使用坐标表格解析"
```

---

### Task 4: 支持 OCR 行专用输出模式

**Files:**
- Modify: `APP/engine/engine/engine.py`
- Modify: `APP/engine/engine/rule_parser.py`
- Test: `APP/engine/tests/test_rule_preview.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_rule_preview.py` 追加：

```python
def test_preview_rule_ocr_rows_only_excludes_article_item(tmp_path, monkeypatch):
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
    rule_path = tmp_path / "ocr_rows_only.yaml"
    rule_path.write_text(
        """
rule_id: "ocr-rows-only"
source_id: "ocr-rows-only-source"
version: 1
status: DRAFT
source:
  platform: "hubei_gov"
  type: "html"
  url: "https://www.hubei.gov.cn/path/article.shtml"
list:
  items_path: "css:article"
extract:
  title: { selector: "h1", type: "text" }
image_extraction:
  enabled: true
  output_mode: "ocr_rows_only"
  trigger:
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
    plugin: "rows_only_ocr"
  parse:
    mode: "table"
    delimiters: ["|"]
    column_mapping:
      序号: "id"
      数据名称: "name"
output:
  fields: ["id", "name", "title", "ocr_plugin", "source_img_url", "manual_review_required"]
  save_raw: false
governance:
  sanitize: true
  required_fields: ["id", "name"]
  min_completeness: 0.5
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

    assert result["total_collected"] == 2
    assert [item["name"] for item in result["items"]] == ["企业登记数据集", "公共信用数据集"]
    assert all(item.get("title") != "正文标题" for item in result["items"])

    engine.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_preview.py::test_preview_rule_ocr_rows_only_excludes_article_item -q`

Expected: FAIL，`total_collected` 为 3 或正文记录仍在结果中。

- [ ] **Step 3: 实现最小代码**

在 `APP/engine/engine/engine.py` 中修改 `_append_image_extraction_items()`：

```python
    def _append_image_extraction_items(self, html_content: str, items: list, rule: dict, page_url: str) -> list:
        """在标准网页采集结果后按配置处理图片 OCR 记录。"""
        runner = ImageExtractionRunner(rule)
        ocr_items = runner.extract(html_content, items, page_url=page_url)
        self.last_ocr_summary = runner.summary if runner.summary.get("enabled") else {}
        output_mode = (rule.get("image_extraction") or {}).get("output_mode", "append")
        if output_mode == "ocr_rows_only":
            return ocr_items
        if ocr_items:
            return items + ocr_items
        return items
```

在 `APP/engine/engine/rule_parser.py` 的 `_validate_image_extraction()` 中追加：

```python
        output_mode = config.get("output_mode", "append")
        if output_mode not in {"append", "ocr_rows_only"}:
            raise ValueError("image_extraction.output_mode must be append or ocr_rows_only")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_preview.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/engine.py APP/engine/engine/rule_parser.py APP/engine/tests/test_rule_preview.py
git commit -m "支持图片OCR行专用输出模式"
```

---

### Task 5: CLI JSON 返回输出文件路径

**Files:**
- Modify: `APP/engine/engine_cli.py`
- Create: `APP/engine/tests/test_engine_cli.py`

- [ ] **Step 1: 写失败测试**

创建 `APP/engine/tests/test_engine_cli.py`：

```python
"""引擎命令行测试。"""

import json

from click.testing import CliRunner

from engine_cli import cli


def test_run_rule_json_includes_output_path(monkeypatch):
    """run-rule JSON 摘要应返回输出文件路径，便于定位明细。"""
    class FakeEngine:
        def run(self, rule_path, event_handler=None):
            return {
                "status": "success",
                "total_collected": 2,
                "dedup_filtered": 0,
                "collected": 2,
                "duration": 1.23,
                "output_path": "/tmp/output/data.json",
            }

        def close(self):
            return None

    monkeypatch.setattr("engine_cli._engine", lambda: FakeEngine())
    monkeypatch.setattr("engine_cli._resolve_rule_path", lambda rule_path: rule_path)

    result = CliRunner().invoke(cli, ["run-rule", "rules/demo.yaml", "--format=json"])

    assert result.exit_code == 0
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["success"] is True
    assert payload["output_path"] == "/tmp/output/data.json"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_engine_cli.py -q`

Expected: FAIL，`output_path` 不存在。

- [ ] **Step 3: 实现最小代码**

在 `APP/engine/engine_cli.py` 的 `run_rule_cmd()` JSON 输出中增加：

```python
                "output_path": result.get("output_path"),
```

完整片段：

```python
            click.echo(json.dumps({
                "success": result.get("status") == "success",
                "total_collected": result.get("total_collected", 0),
                "dedup_filtered": result.get("dedup_filtered", 0),
                "new_count": result.get("collected", 0),
                "duration": round(duration, 2),
                "output_path": result.get("output_path"),
            }, ensure_ascii=False))
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_engine_cli.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine_cli.py APP/engine/tests/test_engine_cli.py
git commit -m "命令行JSON返回输出路径"
```

---

### Task 6: 湖北规则切换为图片逐行输出

**Files:**
- Modify: `APP/engine/rules/数据要素/hubei_gov_image_ocr_article.yaml`
- Test: `APP/engine/tests/test_rule_v2.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_rule_v2.py` 追加：

```python
def test_hubei_image_ocr_rule_uses_rows_only_output():
    """湖北图片 OCR 规则应只输出图片表格行。"""
    from engine.rule_parser import RuleParser

    parser = RuleParser()
    rule = parser.load_rule("rules/数据要素/hubei_gov_image_ocr_article.yaml")

    assert rule["image_extraction"]["output_mode"] == "ocr_rows_only"
    assert rule["governance"]["required_fields"] == ["id", "name"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_v2.py::test_hubei_image_ocr_rule_uses_rows_only_output -q`

Expected: FAIL，`output_mode` 不存在或必填字段仍是 `title`。

- [ ] **Step 3: 修改规则**

在 `APP/engine/rules/数据要素/hubei_gov_image_ocr_article.yaml` 的 `image_extraction` 下加入：

```yaml
  output_mode: "ocr_rows_only"
```

把治理必填字段从：

```yaml
  required_fields:
    - "title"
```

改为：

```yaml
  required_fields:
    - "id"
    - "name"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_v2.py::test_hubei_image_ocr_rule_uses_rows_only_output -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/rules/数据要素/hubei_gov_image_ocr_article.yaml APP/engine/tests/test_rule_v2.py
git commit -m "湖北图片OCR规则改为逐行输出"
```

---

### Task 7: 全量回归和湖北单次验证

**Files:**
- No code changes unless verification exposes a defect.

- [ ] **Step 1: 运行 OCR 和规则相关单测**

Run:

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_image_parser.py tests/test_ocr_plugins.py tests/test_image_extraction.py tests/test_rule_v2.py tests/test_rule_preview.py tests/test_engine_cli.py -q
```

Expected: PASS。

- [ ] **Step 2: 运行 Dashboard 预览 API 回归**

Run:

```bash
python -m pytest APP/dashboard/tests/test_rules_preview_api.py -q
```

Expected: PASS。

- [ ] **Step 3: 运行湖北规则**

Run:

```bash
cd APP/engine && ./venv.sh run python engine_cli.py run-rule "rules/数据要素/hubei_gov_image_ocr_article.yaml" --format=json
```

Expected:

- JSON 摘要包含 `success: true`。
- JSON 摘要包含非空 `output_path`。
- `total_collected` 和 `new_count` 不再是 3，目标接近 25。

- [ ] **Step 4: 检查输出文件**

Run:

```bash
cd APP/engine && .venv/bin/python - <<'PY'
import json
from pathlib import Path

path = max(Path("output/数据要素/hubei_gov").glob("hubei_gov_image_ocr_article_*.json"), key=lambda item: item.stat().st_mtime)
data = json.loads(path.read_text(encoding="utf-8"))
items = data["data"]
print(path)
print("count", len(items))
print("article_records", sum(1 for item in items if item.get("title") == "湖北省数据局发布第三批湖北省高质量数据集"))
print("review_required", sum(1 for item in items if item.get("manual_review_required")))
print(json.dumps(items[:3], ensure_ascii=False, indent=2))
PY
```

Expected:

- `article_records 0`
- `count` 目标为 25；如 OCR 质量导致偏差，必须记录实际值和原因。
- 前 3 条包含 `id`、`name`、`source_img_url`、`ocr_status`。

- [ ] **Step 5: 提交验证修正或记录结果**

如果 Step 3 或 Step 4 发现实现缺陷，先按 TDD 补测试再修正。若无需修正，不提交额外代码。

---

## 自查清单

- 设计覆盖：计划覆盖逐行输出、正文过滤、多图合并、审计字段、CLI 输出路径和湖北规则切换。
- 占位扫描：未发现未落实的占位描述。
- 类型一致性：`OcrResult.structured_data` 是 `dict | None`，解析入口统一为 `parse_ocr_result(ocr_result, config)`。
- 风险：Tesseract OCR 质量仍可能导致少数行字段不完整；计划要求用 `manual_review_required` 和 `parse_errors` 标记，而不是静默丢弃。
