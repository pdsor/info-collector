# 图片 OCR 采集能力实现计划

> **面向代理执行者：** 必需子技能：使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务逐项执行。本计划使用复选框语法跟踪进度。

**Goal:** 在现有 Rule v2 的 `html` 和 `browser` 采集链路后增加本地图片 OCR 补充采集能力，并让输出继续走统一 `meta + data` 与治理管道。

**Architecture:** 新增独立 OCR 子模块负责图片候选发现、下载缓存、Tesseract 调用和 OCR 文本结构化解析；`InfoCollectorEngine` 在 HTML/Browser 标准提取之后按 `image_extraction` 规则决定是否补充 OCR 记录；Rule Center 试采复用同一引擎入口并展示 OCR 摘要。首版只实现 Tesseract + Pillow 预处理，不接入 Agent、云 OCR、视觉模型或 Crawl4AI。

**Tech Stack:** Python、pytest、requests、parsel、Pillow、pytesseract、Flask、Vue 3 CDN、现有 `InfoCollectorEngine`、`GovernancePipeline`、`OutputManager`。

---

## 文件结构

- Create: `APP/engine/engine/image_ocr.py`
  - 负责 OCR 配置默认值、图片预处理、Tesseract 调用、OCR 状态对象。
- Create: `APP/engine/engine/image_parser.py`
  - 负责 `table` 与 `key_value` OCR 文本解析，输出扁平化业务字段和解析错误。
- Create: `APP/engine/engine/image_extraction.py`
  - 负责触发判定、图片候选发现、URL 补全、下载缓存、OCR 调度、记录组装和试采摘要。
- Modify: `APP/engine/engine/engine.py`
  - 在 `_crawl_html()` 与 `_crawl_browser()` 取得页面 HTML 后调用图片采集扩展，并在 `preview_rule()` 返回 OCR 摘要。
- Modify: `APP/engine/engine/rule_parser.py`
  - 校验 `image_extraction` 配置块，不允许非本地 OCR 引擎和 AI 相关配置。
- Modify: `APP/engine/requirements.txt`
  - 增加 `Pillow` 与 `pytesseract`。
- Modify: `APP/dashboard/static/js/app.js`
  - Rule Center 试采结果展示图片候选、下载、OCR 状态、人工复核标记。
- Test: `APP/engine/tests/test_image_parser.py`
- Test: `APP/engine/tests/test_image_extraction.py`
- Test: `APP/engine/tests/test_rule_v2.py`
- Test: `APP/engine/tests/test_rule_preview.py`
- Test: `APP/dashboard/tests/test_rules_preview_api.py`

---

### Task 1: OCR 文本结构化解析

**Files:**
- Create: `APP/engine/engine/image_parser.py`
- Test: `APP/engine/tests/test_image_parser.py`

- [ ] **Step 1: 写失败测试**

创建 `APP/engine/tests/test_image_parser.py`：

```python
"""图片 OCR 文本解析测试。"""

from engine.image_parser import parse_ocr_text


def test_parse_table_text_maps_columns_to_business_fields():
    """表格 OCR 文本按表头映射为多条业务记录。"""
    text = "序号 | 数据名称 | 发布时间\n1 | 企业登记数据集 | 2023-03-01\n2 | 公共信用数据集 | 2023-03-02"
    config = {
        "mode": "table",
        "delimiters": ["|", "\t", ","],
        "column_mapping": {
            "序号": "id",
            "数据名称": "name",
            "发布时间": "publish_time",
        },
    }

    records, errors, semi_structured = parse_ocr_text(text, config)

    assert records == [
        {"id": "1", "name": "企业登记数据集", "publish_time": "2023-03-01", "ocr_text": "1 | 企业登记数据集 | 2023-03-01"},
        {"id": "2", "name": "公共信用数据集", "publish_time": "2023-03-02", "ocr_text": "2 | 公共信用数据集 | 2023-03-02"},
    ]
    assert errors == []
    assert semi_structured is False


def test_parse_key_value_text_maps_labels_to_business_fields():
    """键值 OCR 文本按字段映射为单条业务记录。"""
    text = "项目名称：智慧园区数据治理平台\n申报单位：某某科技有限公司\n所属行业：软件和信息技术服务业"
    config = {
        "mode": "key_value",
        "column_mapping": {
            "项目名称": "project_name",
            "申报单位": "applicant_unit",
            "所属行业": "industry",
        },
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_parser.py -q`

Expected: FAIL，提示 `engine.image_parser` 不存在。

- [ ] **Step 3: 实现解析模块**

创建 `APP/engine/engine/image_parser.py`，实现以下接口：

```python
"""图片 OCR 文本结构化解析。"""

from __future__ import annotations

import re


def _clean_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text or "").splitlines() if line.strip()]


def _split_line(line: str, delimiters: list[str]) -> list[str]:
    for delimiter in delimiters or ["|", "\t", ","]:
        if delimiter in line:
            return [part.strip() for part in line.split(delimiter)]
    return [line.strip()]


def _parse_table(text: str, config: dict) -> tuple[list[dict], list[str], bool]:
    lines = _clean_lines(text)
    delimiters = config.get("delimiters") or ["|", "\t", ","]
    mapping = config.get("column_mapping") or {}
    for header_index, line in enumerate(lines):
        headers = _split_line(line, delimiters)
        mapped = [mapping.get(header) for header in headers]
        if not any(mapped):
            continue
        records = []
        errors = []
        for row_index, row_line in enumerate(lines[header_index + 1:], start=1):
            values = _split_line(row_line, delimiters)
            if len(values) != len(headers):
                errors.append(f"第 {row_index} 行列数不一致")
                continue
            record = {}
            for header, value in zip(headers, values):
                target = mapping.get(header)
                if target:
                    record[target] = value
            if record:
                record["ocr_text"] = row_line
                records.append(record)
        if records:
            return records, errors, False
    return [{"title": "OCR 半结构化结果", "ocr_text": text}], ["未识别到表头或列数不一致"], True


def _parse_key_value(text: str, config: dict) -> tuple[list[dict], list[str], bool]:
    mapping = config.get("column_mapping") or {}
    record = {}
    for line in _clean_lines(text):
        match = re.match(r"^([^:：]+)[:：]\s*(.+)$", line)
        if not match:
            continue
        label, value = match.groups()
        target = mapping.get(label.strip())
        if target:
            record[target] = value.strip()
    if record:
        record["ocr_text"] = text
        return [record], [], False
    return [{"title": "OCR 半结构化结果", "ocr_text": text}], ["未识别到键值字段"], True


def parse_ocr_text(text: str, config: dict) -> tuple[list[dict], list[str], bool]:
    """把 OCR 原始文本解析为业务记录、错误列表和半结构化标记。"""
    mode = (config or {}).get("mode", "table")
    if mode == "key_value":
        return _parse_key_value(text, config or {})
    return _parse_table(text, config or {})
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_parser.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/image_parser.py APP/engine/tests/test_image_parser.py
git commit -m "新增图片 OCR 文本解析"
```

### Task 2: 本地 Tesseract OCR 适配

**Files:**
- Create: `APP/engine/engine/image_ocr.py`
- Modify: `APP/engine/requirements.txt`
- Test: `APP/engine/tests/test_image_extraction.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_image_extraction.py` 添加：

```python
"""图片 OCR 采集链路测试。"""

from engine.image_ocr import run_tesseract_ocr


def test_tesseract_unavailable_returns_manual_review(monkeypatch, tmp_path):
    """Tesseract 不可用时返回人工复核状态，不抛异常。"""
    image_path = tmp_path / "table.png"
    image_path.write_bytes(b"not-a-real-image")

    def raise_missing(*args, **kwargs):
        raise RuntimeError("tesseract missing")

    monkeypatch.setattr("engine.image_ocr._call_tesseract", raise_missing)

    result = run_tesseract_ocr(
        str(image_path),
        {
            "engine": "tesseract",
            "languages": ["chi_sim", "eng"],
            "psm": 6,
            "preprocess": {"grayscale": True, "threshold": True, "resize_ratio": 2},
        },
    )

    assert result["ocr_engine"] == "tesseract"
    assert result["ocr_status"] == "unavailable"
    assert result["ocr_text"] == ""
    assert result["manual_review_required"] is True
    assert "tesseract missing" in result["ocr_error"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_extraction.py::test_tesseract_unavailable_returns_manual_review -q`

Expected: FAIL，提示 `engine.image_ocr` 不存在。

- [ ] **Step 3: 实现 OCR 适配模块**

创建 `APP/engine/engine/image_ocr.py`：

```python
"""本地图片 OCR 适配器。"""

from __future__ import annotations

import time
from pathlib import Path


def _call_tesseract(image, languages: list[str], psm: int) -> str:
    import pytesseract

    lang = "+".join(languages or ["chi_sim", "eng"])
    config = f"--psm {int(psm or 6)}"
    return pytesseract.image_to_string(image, lang=lang, config=config)


def _preprocess_image(image_path: str, preprocess: dict):
    from PIL import Image

    image = Image.open(image_path)
    resize_ratio = float((preprocess or {}).get("resize_ratio") or 1)
    if resize_ratio > 1:
        width, height = image.size
        image = image.resize((int(width * resize_ratio), int(height * resize_ratio)))
    if (preprocess or {}).get("grayscale"):
        image = image.convert("L")
    if (preprocess or {}).get("threshold"):
        image = image.point(lambda pixel: 255 if pixel > 160 else 0)
    return image


def run_tesseract_ocr(image_path: str, config: dict) -> dict:
    """执行本地 Tesseract OCR，失败时返回人工复核记录。"""
    start = time.time()
    result = {
        "ocr_engine": "tesseract",
        "ocr_text": "",
        "ocr_elapsed_ms": 0,
        "ocr_status": "error",
        "ocr_error": "",
        "ocr_empty": True,
        "manual_review_required": True,
    }
    try:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")
        image = _preprocess_image(str(path), (config or {}).get("preprocess") or {})
        text = _call_tesseract(
            image,
            (config or {}).get("languages") or ["chi_sim", "eng"],
            int((config or {}).get("psm") or 6),
        ).strip()
        result["ocr_text"] = text
        result["ocr_status"] = "empty" if not text else "success"
        result["ocr_empty"] = not bool(text)
        result["manual_review_required"] = not bool(text)
    except Exception as exc:
        result["ocr_status"] = "unavailable"
        result["ocr_error"] = str(exc)
    finally:
        result["ocr_elapsed_ms"] = int((time.time() - start) * 1000)
    return result
```

在 `APP/engine/requirements.txt` 增加：

```text
Pillow>=10.0.0
pytesseract>=0.3.10
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_extraction.py::test_tesseract_unavailable_returns_manual_review -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/image_ocr.py APP/engine/tests/test_image_extraction.py APP/engine/requirements.txt
git commit -m "接入本地 Tesseract OCR 适配"
```

### Task 3: 图片发现、下载和记录组装

**Files:**
- Create: `APP/engine/engine/image_extraction.py`
- Test: `APP/engine/tests/test_image_extraction.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_image_extraction.py` 追加：

```python
from engine.image_extraction import ImageExtractionRunner


def test_image_runner_discovers_downloads_and_builds_records(monkeypatch, tmp_path):
    """图片采集器发现图片、缓存下载结果并展开 OCR 表格记录。"""
    html = '<html><body><img src="/table.png" alt="数据集清单"></body></html>'
    image_bytes = b"png-bytes"

    class FakeResponse:
        headers = {"content-length": str(len(image_bytes))}
        content = image_bytes

        def raise_for_status(self):
            return None

    monkeypatch.setattr("engine.image_extraction.requests.get", lambda *args, **kwargs: FakeResponse())
    monkeypatch.setattr(
        "engine.image_extraction.run_tesseract_ocr",
        lambda path, config: {
            "ocr_engine": "tesseract",
            "ocr_text": "序号 | 数据名称 | 发布时间\n1 | 企业登记数据集 | 2023-03-01",
            "ocr_elapsed_ms": 12,
            "ocr_status": "success",
            "ocr_error": "",
            "ocr_empty": False,
            "manual_review_required": False,
        },
    )

    rule = {
        "name": "OCR 测试",
        "source": {"url": "https://example.com/page", "platform": "example"},
        "image_extraction": {
            "enabled": True,
            "trigger": {"when_empty": True, "img_keywords": ["清单"]},
            "images": {"selector": "img", "src_attribute": "src", "include_alt": True, "max_images": 10},
            "download": {"dir_template": str(tmp_path / "{task_id}"), "max_size_mb": 5},
            "ocr": {"engine": "tesseract", "languages": ["chi_sim", "eng"], "psm": 6},
            "parse": {
                "mode": "table",
                "delimiters": ["|", "\t", ","],
                "column_mapping": {"序号": "id", "数据名称": "name", "发布时间": "publish_time"},
            },
        },
    }

    runner = ImageExtractionRunner(rule)
    records, summary = runner.extract(
        page_url="https://example.com/page",
        page_title="测试页",
        html_content=html,
        existing_items=[],
    )

    assert summary["candidate_count"] == 1
    assert summary["download_success_count"] == 1
    assert summary["ocr_success_count"] == 1
    assert records[0]["id"] == "1"
    assert records[0]["name"] == "企业登记数据集"
    assert records[0]["url"] == "https://example.com/page"
    assert records[0]["source_img_url"] == "https://example.com/table.png"
    assert records[0]["source_img_alt"] == "数据集清单"
    assert records[0]["ocr_engine"] == "tesseract"
    assert records[0]["semi_structured"] is False
    assert records[0]["manual_review_required"] is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_extraction.py::test_image_runner_discovers_downloads_and_builds_records -q`

Expected: FAIL，提示 `ImageExtractionRunner` 不存在。

- [ ] **Step 3: 实现图片采集器**

创建 `APP/engine/engine/image_extraction.py`，包含这些公开接口：

```python
"""图片内嵌数据采集扩展。"""

from __future__ import annotations

import hashlib
import mimetypes
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import parsel
import requests

from .image_ocr import run_tesseract_ocr
from .image_parser import parse_ocr_text


class ImageExtractionRunner:
    """按 Rule v2 image_extraction 配置执行图片 OCR 补充采集。"""

    def __init__(self, rule: dict):
        self.rule = rule
        self.config = rule.get("image_extraction") or {}
        self.summary = {
            "enabled": bool(self.config.get("enabled")),
            "triggered": False,
            "candidate_count": 0,
            "download_success_count": 0,
            "download_failed_count": 0,
            "download_skipped_count": 0,
            "ocr_success_count": 0,
            "ocr_empty_count": 0,
            "ocr_unavailable_count": 0,
            "record_count": 0,
        }
```

实现细节：

- `_should_trigger(page_url, html_content, existing_items)`：
  - `enabled` 为假时返回 `False`。
  - `trigger.when_empty` 为真且 `existing_items` 为空时返回 `True`。
  - 页面域名包含任一 `trigger.domains` 时返回 `True`。
  - HTML 中图片 `src`、文件名或 `alt` 命中任一 `trigger.img_keywords` 时返回 `True`。
- `_discover_images(page_url, html_content)`：
  - 使用 `parsel.Selector(text=html_content).css(selector)` 查找图片。
  - 默认 `selector=img`、`src_attribute=src`、`max_images=10`。
  - 通过 `urljoin(page_url, src)` 补全绝对 URL。
- `_download_image(candidate)`：
  - 默认目录 `/tmp/scraper_imgs/{task_id}`，`task_id` 使用规则名哈希前 12 位。
  - 文件名为 `{sha256(url)[:16]}.{ext}`，扩展名优先来自 URL，缺失时用响应 `content-type`。
  - 默认重试 3 次、间隔 2 秒、超时 15 秒、最大 5MB。
  - 下载失败只更新摘要并返回带错误的候选，不抛出。
- `extract(page_url, page_title, html_content, existing_items)`：
  - 触发失败时返回 `([], summary)`。
  - 每张成功下载图片调用 `run_tesseract_ocr()`。
  - OCR 成功后调用 `parse_ocr_text()`，将一张图多行展开为多条记录。
  - OCR 不可用或 OCR 为空时输出一条人工复核记录。
  - 每条记录补充 `url`、`source_url`、`source_img_url`、`source_img_path`、`source_img_alt`、`ocr_engine`、`ocr_text`、`ocr_empty`、`semi_structured`、`manual_review_required`、`parse_errors`。
  - 对没有独立 `raw_id` 的记录设置 `raw_id="{图片哈希}_{行号}"`。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_extraction.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/image_extraction.py APP/engine/tests/test_image_extraction.py
git commit -m "实现图片发现下载和记录组装"
```

### Task 4: Rule v2 配置校验

**Files:**
- Modify: `APP/engine/engine/rule_parser.py`
- Test: `APP/engine/tests/test_rule_v2.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_rule_v2.py` 追加：

```python
def test_rule_parser_accepts_local_image_extraction_config():
    """Rule v2 接受本地 Tesseract 图片采集配置。"""
    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "ocr-rule",
        "source_id": "ocr-source",
        "version": 1,
        "status": "TESTING",
        "source": {"type": "html", "platform": "example", "url": "https://example.com"},
        "list": {"items_path": "css:article"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "image_extraction": {
            "enabled": True,
            "ocr": {"engine": "tesseract", "languages": ["chi_sim", "eng"]},
            "parse": {"mode": "table", "column_mapping": {"数据名称": "name"}},
        },
    }

    assert RuleParser().validate(rule) is True


def test_rule_parser_rejects_cloud_or_ai_ocr_engine():
    """Rule v2 禁止云 OCR、Agent 和视觉模型配置。"""
    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "ocr-rule",
        "source_id": "ocr-source",
        "version": 1,
        "source": {"type": "html", "platform": "example", "url": "https://example.com"},
        "list": {"items_path": "css:article"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "image_extraction": {
            "enabled": True,
            "ocr": {"engine": "vision_model"},
            "parse": {"mode": "table", "column_mapping": {"数据名称": "name"}},
        },
    }

    try:
        RuleParser().validate(rule)
    except ValueError as exc:
        assert "本地 OCR" in str(exc)
    else:
        raise AssertionError("非本地 OCR 引擎必须校验失败")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_v2.py -q`

Expected: FAIL，第二个测试未拒绝 `vision_model`。

- [ ] **Step 3: 增加校验逻辑**

在 `RuleParser` 新增 `_validate_image_extraction()`，并在 `_validate_rule_v2()` 与旧规则 `validate()` 中调用：

```python
def _validate_image_extraction(self, rule: dict):
    """校验图片 OCR 配置，只允许本地确定性 OCR。"""
    config = rule.get("image_extraction")
    if not config:
        return
    if not isinstance(config, dict):
        raise ValueError("image_extraction must be an object")
    ocr = config.get("ocr") or {}
    engine = ocr.get("engine", "tesseract")
    if engine != "tesseract":
        raise ValueError("image_extraction 仅支持本地 OCR 引擎 tesseract")
    parse = config.get("parse") or {}
    mode = parse.get("mode", "table")
    if mode not in {"table", "key_value"}:
        raise ValueError("image_extraction.parse.mode must be table or key_value")
    if parse and not isinstance(parse.get("column_mapping") or {}, dict):
        raise ValueError("image_extraction.parse.column_mapping must be an object")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_v2.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/rule_parser.py APP/engine/tests/test_rule_v2.py
git commit -m "校验图片 OCR 规则配置"
```

### Task 5: 引擎 HTML/Browser 链路集成

**Files:**
- Modify: `APP/engine/engine/engine.py`
- Test: `APP/engine/tests/test_image_extraction.py`
- Test: `APP/engine/tests/test_rule_preview.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_image_extraction.py` 追加：

```python
def test_engine_appends_ocr_records_to_html_crawl(monkeypatch, tmp_path):
    """HTML 标准提取为空时，引擎补充 OCR 记录。"""
    from engine.engine import InfoCollectorEngine

    html = '<html><body><img src="/table.png" alt="数据集清单"></body></html>'
    monkeypatch.setattr(
        "engine.image_extraction.run_tesseract_ocr",
        lambda path, config: {
            "ocr_engine": "tesseract",
            "ocr_text": "序号 | 数据名称\n1 | 企业登记数据集",
            "ocr_elapsed_ms": 8,
            "ocr_status": "success",
            "ocr_error": "",
            "ocr_empty": False,
            "manual_review_required": False,
        },
    )

    class FakeResponse:
        headers = {"content-length": "4"}
        content = b"data"

        def raise_for_status(self):
            return None

    monkeypatch.setattr("engine.image_extraction.requests.get", lambda *args, **kwargs: FakeResponse())

    rule = {
        "rule_id": "ocr-rule",
        "source_id": "ocr-source",
        "version": 1,
        "source": {"type": "html", "platform": "example", "url": "https://example.com/page"},
        "list": {"items_path": "css:.missing"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "image_extraction": {
            "enabled": True,
            "trigger": {"when_empty": True},
            "images": {"selector": "img", "src_attribute": "src", "include_alt": True},
            "download": {"dir_template": str(tmp_path / "{task_id}")},
            "ocr": {"engine": "tesseract"},
            "parse": {"mode": "table", "delimiters": ["|"], "column_mapping": {"序号": "id", "数据名称": "name"}},
        },
        "output": {"fields": ["id", "name", "url"]},
    }
    engine = InfoCollectorEngine(dedup_db_path=":memory:")
    monkeypatch.setattr(engine.html_crawler, "fetch", lambda *args, **kwargs: html)

    items = engine.crawl(rule)

    assert items[0]["id"] == "1"
    assert items[0]["name"] == "企业登记数据集"
    assert items[0]["source_url"] == "https://example.com/page"
    assert engine.last_image_extraction_summary["record_count"] == 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_extraction.py::test_engine_appends_ocr_records_to_html_crawl -q`

Expected: FAIL，引擎未调用图片采集扩展。

- [ ] **Step 3: 集成到引擎**

在 `APP/engine/engine/engine.py`：

```python
from .image_extraction import ImageExtractionRunner
```

在 `__init__()` 增加：

```python
self.last_image_extraction_summary = {}
```

新增辅助方法：

```python
def _append_image_extraction(self, rule: dict, page_url: str, html_content: str, items: list) -> list:
    """在 HTML/Browser 标准提取后补充图片 OCR 记录。"""
    self.last_image_extraction_summary = {}
    config = rule.get("image_extraction") or {}
    if not config.get("enabled"):
        return items
    runner = ImageExtractionRunner(rule)
    page_title = rule.get("name") or rule.get("source", {}).get("platform", "")
    ocr_items, summary = runner.extract(
        page_url=page_url,
        page_title=page_title,
        html_content=html_content,
        existing_items=items,
    )
    self.last_image_extraction_summary = summary
    return [*items, *ocr_items]
```

在 `_crawl_html()` 和 `_crawl_browser()` 中，把标准提取结果先赋值给 `items`，最后返回：

```python
return self._append_image_extraction(rule, url, html_content, items)
```

`preview_rule()` 的返回值补充：

```python
"image_extraction": self.last_image_extraction_summary,
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_extraction.py tests/test_rule_preview.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/engine.py APP/engine/tests/test_image_extraction.py APP/engine/tests/test_rule_preview.py
git commit -m "集成图片 OCR 到采集引擎"
```

### Task 6: 治理输出和完整运行闭环

**Files:**
- Modify: `APP/engine/tests/test_integration.py`
- Modify: `APP/engine/engine/image_extraction.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_integration.py` 追加：

```python
def test_full_pipeline_outputs_ocr_records_with_governance(tmp_path, monkeypatch):
    """完整运行输出 OCR 记录，且每条记录进入治理管道。"""
    import json
    import yaml
    from engine.engine import InfoCollectorEngine

    html = '<html><body><img src="/table.png" alt="数据集清单"></body></html>'
    monkeypatch.setattr(
        "engine.image_extraction.run_tesseract_ocr",
        lambda path, config: {
            "ocr_engine": "tesseract",
            "ocr_text": "序号 | 数据名称 | 发布时间\n1 | 企业登记数据集 | 2023-03-01\n2 | 公共信用数据集 | 2023-03-02",
            "ocr_elapsed_ms": 10,
            "ocr_status": "success",
            "ocr_error": "",
            "ocr_empty": False,
            "manual_review_required": False,
        },
    )

    class FakeResponse:
        headers = {"content-length": "4"}
        content = b"data"

        def raise_for_status(self):
            return None

    monkeypatch.setattr("engine.image_extraction.requests.get", lambda *args, **kwargs: FakeResponse())

    output_dir = tmp_path / "output"
    rule_path = tmp_path / "rule.yaml"
    rule = {
        "rule_id": "ocr-rule",
        "source_id": "ocr-source",
        "version": 1,
        "name": "图片 OCR 集成测试",
        "subject": "测试",
        "source": {"type": "html", "platform": "example", "url": "https://example.com/page"},
        "list": {"items_path": "css:.missing"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "image_extraction": {
            "enabled": True,
            "trigger": {"when_empty": True},
            "images": {"selector": "img", "src_attribute": "src", "include_alt": True},
            "download": {"dir_template": str(tmp_path / "{task_id}")},
            "ocr": {"engine": "tesseract"},
            "parse": {
                "mode": "table",
                "delimiters": ["|"],
                "column_mapping": {"序号": "id", "数据名称": "name", "发布时间": "publish_time"},
            },
        },
        "governance": {"sanitize": True, "dedup": "hash", "required_fields": ["name", "url"], "min_completeness": 0.8},
        "output": {"path": str(output_dir), "fields": ["id", "name", "publish_time", "url"], "filename_template": "ocr_{date}.json"},
    }
    rule_path.write_text(yaml.safe_dump(rule, allow_unicode=True), encoding="utf-8")
    engine = InfoCollectorEngine(dedup_db_path=":memory:", state_dir=str(output_dir))
    monkeypatch.setattr(engine.html_crawler, "fetch", lambda *args, **kwargs: html)

    result = engine.run(str(rule_path))

    assert result["status"] == "success"
    assert result["collected"] == 2
    with open(result["output_path"], encoding="utf-8") as f:
        payload = json.load(f)
    assert payload["meta"]["governance"]["item_count"] == 2
    assert payload["data"][0]["name"] == "企业登记数据集"
    assert payload["data"][0]["_governance"]["field_completeness"] == 1.0
    assert payload["data"][0]["source_img_path"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_integration.py::test_full_pipeline_outputs_ocr_records_with_governance -q`

Expected: FAIL，若前序任务未补齐 `url`、`raw_id` 或治理字段，测试会暴露具体缺口。

- [ ] **Step 3: 补齐记录字段**

在 `ImageExtractionRunner` 记录组装处确保：

```python
record.setdefault("url", page_url)
record.setdefault("source_url", page_url)
record["source_img_url"] = candidate["url"]
record["source_img_path"] = candidate["path"]
record["source_img_alt"] = candidate.get("alt", "")
record["ocr_engine"] = ocr_result.get("ocr_engine", "tesseract")
record["ocr_empty"] = bool(ocr_result.get("ocr_empty"))
record["semi_structured"] = bool(semi_structured)
record["manual_review_required"] = bool(ocr_result.get("manual_review_required") or semi_structured)
record["parse_errors"] = parse_errors
record.setdefault("raw_id", f"{candidate['hash']}_{row_index}")
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_integration.py::test_full_pipeline_outputs_ocr_records_with_governance -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/engine/engine/image_extraction.py APP/engine/tests/test_integration.py
git commit -m "打通图片 OCR 治理输出闭环"
```

### Task 7: Rule Center 试采展示

**Files:**
- Modify: `APP/dashboard/static/js/app.js`
- Test: `APP/dashboard/tests/test_rules_preview_api.py`

- [ ] **Step 1: 写失败测试**

在 `APP/dashboard/tests/test_rules_preview_api.py` 追加：

```python
def test_preview_rule_returns_image_extraction_summary(monkeypatch):
    """试采 API 返回图片采集摘要，供前端展示。"""
    from engine.engine import InfoCollectorEngine

    def fake_preview(self, rule_path, limit=5):
        return {
            "success": True,
            "status": "success",
            "total_collected": 1,
            "preview_count": 1,
            "items": [{"name": "企业登记数据集", "ocr_empty": False, "semi_structured": False, "manual_review_required": False}],
            "governance": {"item_count": 1},
            "image_extraction": {
                "enabled": True,
                "triggered": True,
                "candidate_count": 1,
                "download_success_count": 1,
                "download_failed_count": 0,
                "download_skipped_count": 0,
                "ocr_success_count": 1,
                "ocr_empty_count": 0,
                "ocr_unavailable_count": 0,
                "record_count": 1,
            },
        }

    monkeypatch.setattr(InfoCollectorEngine, "preview_rule", fake_preview)
    client = app.test_client()

    response = client.post("/api/rules/preview", json={"yaml": "name: x\nsource: {}\nlist: {}\n", "limit": 5})

    payload = response.get_json()
    assert payload["image_extraction"]["candidate_count"] == 1
    assert payload["image_extraction"]["ocr_success_count"] == 1
```

- [ ] **Step 2: 运行 API 测试确认通过或暴露缺口**

Run: `APP/engine/.venv/bin/python -m pytest APP/dashboard/tests/test_rules_preview_api.py -q`

Expected: PASS；若 API 过滤了字段，应修复为透传 `image_extraction`。

- [ ] **Step 3: 更新前端试采结果展示**

在 `RuleCenter` 预览模板的结果区域增加 OCR 摘要面板，展示：

```html
<div v-if="previewResult?.image_extraction?.enabled" class="preview-ocr-summary">
  <h3>图片 OCR</h3>
  <div class="metric-row">
    <span>触发：{{ previewResult.image_extraction.triggered ? '是' : '否' }}</span>
    <span>候选：{{ previewResult.image_extraction.candidate_count }}</span>
    <span>下载成功：{{ previewResult.image_extraction.download_success_count }}</span>
    <span>下载失败：{{ previewResult.image_extraction.download_failed_count }}</span>
    <span>OCR 成功：{{ previewResult.image_extraction.ocr_success_count }}</span>
    <span>OCR 空结果：{{ previewResult.image_extraction.ocr_empty_count }}</span>
    <span>需复核：{{ previewResult.items.filter(item => item.manual_review_required).length }}</span>
  </div>
</div>
```

在记录表格或 JSON 预览中保留 `ocr_empty`、`semi_structured`、`manual_review_required`、`source_img_url`、`ocr_engine` 字段，不做裁剪。

- [ ] **Step 4: 运行 Dashboard 静态测试**

Run: `APP/engine/.venv/bin/python -m pytest APP/dashboard/tests/test_rule_center_editor_static.py APP/dashboard/tests/test_rules_preview_api.py -q`

Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add APP/dashboard/static/js/app.js APP/dashboard/tests/test_rules_preview_api.py
git commit -m "展示规则试采图片 OCR 摘要"
```

### Task 8: 依赖、示例规则和最终验证

**Files:**
- Modify: `APP/engine/requirements.txt`
- Create: `APP/engine/rules/测试/image_ocr_demo.yaml`

- [ ] **Step 1: 创建示例规则**

创建 `APP/engine/rules/测试/image_ocr_demo.yaml`：

```yaml
rule_id: "image-ocr-demo"
source_id: "image-ocr-demo-source"
version: 1
status: TESTING
name: "图片 OCR 示例规则"
subject: "测试"
enabled: false
source:
  platform: "image_ocr_demo"
  type: "html"
  url: "https://example.com/page"
list:
  items_path: "css:.dataset-list"
extract:
  title:
    selector: ".dataset-title"
    type: "text"
image_extraction:
  enabled: true
  trigger:
    when_empty: true
    img_keywords:
      - "table"
      - "数据"
      - "附件"
      - "清单"
  images:
    selector: "img"
    src_attribute: "src"
    include_alt: true
    max_images: 10
  download:
    dir_template: "/tmp/scraper_imgs/{task_id}"
    retries: 3
    retry_interval_seconds: 2
    timeout_seconds: 15
    max_size_mb: 5
  ocr:
    engine: "tesseract"
    languages:
      - "chi_sim"
      - "eng"
    psm: 6
    preprocess:
      grayscale: true
      threshold: true
      resize_ratio: 2
  parse:
    mode: "table"
    delimiters:
      - "|"
      - "\t"
      - ","
    column_mapping:
      序号: "id"
      数据名称: "name"
      发布时间: "publish_time"
      发布部门: "department"
governance:
  sanitize: true
  dedup: hash
  required_fields:
    - "name"
    - "url"
  min_completeness: 0.8
output:
  fields:
    - "id"
    - "name"
    - "publish_time"
    - "department"
    - "url"
    - "source_img_url"
    - "source_img_path"
    - "ocr_engine"
    - "ocr_empty"
    - "semi_structured"
    - "manual_review_required"
  save_raw: false
  filename_template: "image_ocr_demo_{date}.json"
```

- [ ] **Step 2: 安装 Python 依赖**

Run: `cd APP/engine && .venv/bin/python -m pip install -r requirements.txt`

Expected: 安装 `Pillow` 与 `pytesseract` 成功。系统包 `tesseract-ocr`、`tesseract-ocr-chi-sim`、`tesseract-ocr-eng` 缺失时，代码仍通过人工复核降级测试。

- [ ] **Step 3: 运行完整测试**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_parser.py tests/test_image_extraction.py tests/test_rule_v2.py tests/test_rule_preview.py tests/test_integration.py -q`

Expected: PASS。

- [ ] **Step 4: 运行 Dashboard 测试**

Run: `APP/engine/.venv/bin/python -m pytest APP/dashboard/tests/test_rules_preview_api.py APP/dashboard/tests/test_rule_center_editor_static.py -q`

Expected: PASS。

- [ ] **Step 5: 验证无 AI/Crawl4AI 回归**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_ng_no_ai.py tests/test_crawl4ai_routing.py -q`

Expected: PASS，确认未恢复 AI 提取或 Crawl4AI。

- [ ] **Step 6: 最终提交**

```bash
git add APP/engine/requirements.txt APP/engine/rules/测试/image_ocr_demo.yaml
git commit -m "补充图片 OCR 示例规则和依赖"
```

---

## 验收清单

- [ ] Rule v2 可声明 `image_extraction`，且只允许 `tesseract` 本地 OCR。
- [ ] 标准 DOM 提取为空时，可按配置触发图片 OCR。
- [ ] 域名或图片关键词命中时，可补充 OCR 结果。
- [ ] 图片 URL 支持相对路径补全并缓存到 `/tmp/scraper_imgs/{task_id}` 或规则目录模板。
- [ ] OCR 不可用、OCR 为空、解析失败时均不阻塞任务，并输出人工复核字段。
- [ ] 表格 OCR 文本可按 `column_mapping` 展开为多条 `data` 记录。
- [ ] 键值 OCR 文本可按 `column_mapping` 输出顶层业务字段。
- [ ] 输出继续使用 `OutputManager` 的 `meta + data` 结构。
- [ ] OCR 结果进入 `GovernancePipeline`，每条记录包含 `_governance`。
- [ ] Rule Center 试采展示图片候选、下载、OCR 和人工复核状态。

## 自检

- 需求覆盖：已覆盖需求文档第 2、4、5、6、7、8、9、10、12、13、14、15、17 节；PaddleOCR、复杂版面恢复、旋转倾斜校正和人工复核入口属于后续阶段，首版不实现。
- 占位扫描：计划未使用未定项标记、待办标记或空泛的“以后实现”步骤；每个开发任务都包含测试、实现入口、验证命令和提交信息。
- 类型一致性：计划统一使用 `ImageExtractionRunner.extract()` 返回 `(records, summary)`，OCR 适配返回 `ocr_engine`、`ocr_text`、`ocr_status`、`ocr_empty`、`manual_review_required`，解析器返回 `(records, errors, semi_structured)`。
