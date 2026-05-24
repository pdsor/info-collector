# 图片 OCR 插件化执行链路实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有 `image_extraction` YAML 配置补齐真实执行链路，并把 OCR 做成可替换插件，让后续切换 PaddleOCR、其他本地 OCR 或更高质量组件时不改采集主链路。

**Architecture:** 图片采集链路拆为两层：`image_extraction.py` 负责页面图片发现、下载、插件调度和记录组装；`ocr_plugins` 包负责 OCR 插件协议、注册表和默认 Tesseract 插件。规则中优先读取 `image_extraction.ocr.plugin`，兼容既有 `image_extraction.ocr.engine`，默认插件为 `tesseract`。

**Tech Stack:** Python、pytest、requests、parsel、Pillow、pytesseract、现有 `InfoCollectorEngine`、`GovernancePipeline`、Rule v2 YAML。

---

## 插件边界

本计划中的“插件”是项目引擎内的 OCR 运行时插件，不是 Codex 插件脚手架。插件必须满足：

- 每个插件实现统一接口：`recognize(image_path: str, config: dict) -> OcrResult`。
- 插件只负责“图片转文本”，不负责下载图片、解析业务表格或写输出。
- 插件失败必须返回状态对象，不向上抛出导致整条采集失败的异常。
- `image_extraction` 只能通过注册表调用插件，不能直接依赖 Tesseract。
- 新增 OCR 组件时只需新增 `APP/engine/engine/ocr_plugins/<name>.py` 并注册。

---

## 文件结构

- Create: `APP/engine/engine/image_parser.py`
  - 解析 OCR 原始文本，支持 `table` 和 `key_value`。
- Create: `APP/engine/engine/ocr_plugins/__init__.py`
  - 暴露插件注册和查找入口。
- Create: `APP/engine/engine/ocr_plugins/base.py`
  - 定义 `OcrResult` 和 `OcrPlugin` 协议。
- Create: `APP/engine/engine/ocr_plugins/registry.py`
  - 管理 OCR 插件注册表，默认注册 `tesseract`。
- Create: `APP/engine/engine/ocr_plugins/tesseract.py`
  - 默认 Tesseract OCR 插件，内部处理 Pillow 预处理和 pytesseract 调用。
- Create: `APP/engine/engine/image_extraction.py`
  - 处理触发条件、图片发现、URL 补全、下载缓存、OCR 插件调度、解析结果合并。
- Modify: `APP/engine/engine/engine.py`
  - 在 `_crawl_html()` 与 `_crawl_browser()` 标准提取后追加 OCR 记录；`preview_rule()` 返回 `ocr_summary`。
- Modify: `APP/engine/engine/rule_parser.py`
  - 校验 `image_extraction.ocr.plugin/engine` 仅允许本地已注册插件，拒绝 AI、Agent、云 OCR 配置。
- Modify: `APP/engine/requirements.txt`
  - 增加默认 Tesseract 插件所需的 `Pillow` 和 `pytesseract`。
- Modify: `APP/dashboard/static/js/app.js`
  - 规则中心试采面板展示 OCR 摘要、插件名称、图片数量、OCR 状态和人工复核数量。
- Test: `APP/engine/tests/test_image_parser.py`
- Test: `APP/engine/tests/test_ocr_plugins.py`
- Test: `APP/engine/tests/test_image_extraction.py`
- Test: `APP/engine/tests/test_rule_v2.py`
- Test: `APP/engine/tests/test_rule_preview.py`
- Test: `APP/dashboard/tests/test_rules_preview_api.py`

---

### Task 1: OCR 文本解析模块

**Files:**
- Create: `APP/engine/engine/image_parser.py`
- Test: `APP/engine/tests/test_image_parser.py`

- [ ] **Step 1: 写失败测试**

创建 `APP/engine/tests/test_image_parser.py`：

```python
"""图片 OCR 文本解析测试。"""

from engine.image_parser import parse_ocr_text


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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_parser.py -q`

Expected: FAIL，提示 `ModuleNotFoundError: No module named 'engine.image_parser'`。

- [ ] **Step 3: 实现解析模块**

创建 `APP/engine/engine/image_parser.py`：

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


def _manual_record(text: str, error: str) -> tuple[list[dict], list[str], bool]:
    return [{"title": "OCR 半结构化结果", "ocr_text": text}], [error], True


def _parse_table(text: str, config: dict) -> tuple[list[dict], list[str], bool]:
    lines = _clean_lines(text)
    delimiters = config.get("delimiters") or ["|", "\t", ","]
    mapping = config.get("column_mapping") or {}
    for header_index, line in enumerate(lines):
        headers = _split_line(line, delimiters)
        if not any(mapping.get(header) for header in headers):
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
    return _manual_record(text, "未识别到表头或列数不一致")


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
    return _manual_record(text, "未识别到键值字段")


def parse_ocr_text(text: str, config: dict) -> tuple[list[dict], list[str], bool]:
    """把 OCR 原始文本解析为业务记录、错误列表和半结构化标记。"""
    mode = (config or {}).get("mode", "table")
    if mode == "key_value":
        return _parse_key_value(text, config or {})
    return _parse_table(text, config or {})
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_parser.py -q`

Expected: PASS，3 passed。

---

### Task 2: OCR 插件协议与注册表

**Files:**
- Create: `APP/engine/engine/ocr_plugins/__init__.py`
- Create: `APP/engine/engine/ocr_plugins/base.py`
- Create: `APP/engine/engine/ocr_plugins/registry.py`
- Test: `APP/engine/tests/test_ocr_plugins.py`

- [ ] **Step 1: 写失败测试**

创建 `APP/engine/tests/test_ocr_plugins.py`：

```python
"""OCR 插件注册表测试。"""

from engine.ocr_plugins import OcrResult, get_ocr_plugin, register_ocr_plugin, resolve_ocr_plugin_name


class FakeOcrPlugin:
    name = "fake"

    def recognize(self, image_path: str, config: dict) -> OcrResult:
        return OcrResult(
            plugin="fake",
            status="success",
            text="序号 | 数据名称\n1 | 企业登记数据集",
            error="",
            elapsed_seconds=0.01,
        )


def test_register_and_get_custom_ocr_plugin():
    """可注册并获取自定义 OCR 插件。"""
    register_ocr_plugin(FakeOcrPlugin())

    plugin = get_ocr_plugin("fake")
    result = plugin.recognize("/tmp/fake.png", {})

    assert plugin.name == "fake"
    assert result.to_item_fields() == {
        "ocr_plugin": "fake",
        "ocr_engine": "fake",
        "ocr_status": "success",
        "ocr_text": "序号 | 数据名称\n1 | 企业登记数据集",
        "ocr_error": "",
        "ocr_elapsed_seconds": 0.01,
        "ocr_empty": False,
        "manual_review_required": False,
    }


def test_resolve_ocr_plugin_name_prefers_plugin_and_keeps_engine_compatibility():
    """规则优先使用 plugin 字段，并兼容旧 engine 字段。"""
    assert resolve_ocr_plugin_name({"plugin": "fake", "engine": "tesseract"}) == "fake"
    assert resolve_ocr_plugin_name({"engine": "tesseract"}) == "tesseract"
    assert resolve_ocr_plugin_name({}) == "tesseract"


def test_unknown_ocr_plugin_raises_clear_error():
    """未知 OCR 插件返回明确错误。"""
    try:
        get_ocr_plugin("missing")
    except ValueError as exc:
        assert "未知 OCR 插件" in str(exc)
    else:
        raise AssertionError("未知 OCR 插件必须报错")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_ocr_plugins.py -q`

Expected: FAIL，提示 `ModuleNotFoundError: No module named 'engine.ocr_plugins'`。

- [ ] **Step 3: 实现插件协议**

创建 `APP/engine/engine/ocr_plugins/base.py`：

```python
"""OCR 插件协议。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class OcrResult:
    """OCR 插件统一结果。"""

    plugin: str
    status: str
    text: str = ""
    error: str = ""
    elapsed_seconds: float = 0.0

    @property
    def empty(self) -> bool:
        return self.text.strip() == ""

    @property
    def manual_review_required(self) -> bool:
        return self.status != "success" or self.empty

    def to_item_fields(self) -> dict:
        """转换为采集记录中的 OCR 字段。"""
        return {
            "ocr_plugin": self.plugin,
            "ocr_engine": self.plugin,
            "ocr_status": self.status,
            "ocr_text": self.text,
            "ocr_error": self.error,
            "ocr_elapsed_seconds": self.elapsed_seconds,
            "ocr_empty": self.empty,
            "manual_review_required": self.manual_review_required,
        }


class OcrPlugin(Protocol):
    """OCR 插件接口。"""

    name: str

    def recognize(self, image_path: str, config: dict) -> OcrResult:
        """识别图片并返回统一 OCR 结果。"""
```

- [ ] **Step 4: 实现注册表**

创建 `APP/engine/engine/ocr_plugins/registry.py`：

```python
"""OCR 插件注册表。"""

from __future__ import annotations

from .base import OcrPlugin


_PLUGINS: dict[str, OcrPlugin] = {}


def register_ocr_plugin(plugin: OcrPlugin):
    """注册 OCR 插件。"""
    name = getattr(plugin, "name", "").strip()
    if not name:
        raise ValueError("OCR 插件缺少 name")
    _PLUGINS[name] = plugin


def get_ocr_plugin(name: str) -> OcrPlugin:
    """获取 OCR 插件。"""
    plugin_name = name or "tesseract"
    plugin = _PLUGINS.get(plugin_name)
    if plugin is None:
        raise ValueError(f"未知 OCR 插件: {plugin_name}")
    return plugin


def list_ocr_plugins() -> list[str]:
    """列出已注册 OCR 插件名称。"""
    return sorted(_PLUGINS)


def resolve_ocr_plugin_name(config: dict) -> str:
    """从规则 OCR 配置解析插件名称，兼容 engine 字段。"""
    config = config or {}
    return config.get("plugin") or config.get("engine") or "tesseract"
```

- [ ] **Step 5: 实现包入口**

创建 `APP/engine/engine/ocr_plugins/__init__.py`：

```python
"""OCR 插件入口。"""

from .base import OcrPlugin, OcrResult
from .registry import get_ocr_plugin, list_ocr_plugins, register_ocr_plugin, resolve_ocr_plugin_name

__all__ = [
    "OcrPlugin",
    "OcrResult",
    "get_ocr_plugin",
    "list_ocr_plugins",
    "register_ocr_plugin",
    "resolve_ocr_plugin_name",
]
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_ocr_plugins.py -q`

Expected: PASS，3 passed。

---

### Task 3: 默认 Tesseract OCR 插件

**Files:**
- Create: `APP/engine/engine/ocr_plugins/tesseract.py`
- Modify: `APP/engine/engine/ocr_plugins/__init__.py`
- Modify: `APP/engine/requirements.txt`
- Test: `APP/engine/tests/test_ocr_plugins.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_ocr_plugins.py` 追加：

```python
def test_default_tesseract_plugin_is_registered():
    """默认 Tesseract 插件应自动注册。"""
    plugin = get_ocr_plugin("tesseract")

    assert plugin.name == "tesseract"


def test_tesseract_unavailable_returns_manual_review(monkeypatch, tmp_path):
    """Tesseract 不可用时插件返回人工复核状态。"""
    from engine.ocr_plugins.tesseract import TesseractOcrPlugin

    image_path = tmp_path / "table.png"
    image_path.write_bytes(b"not-a-real-image")

    def raise_missing(*args, **kwargs):
        raise RuntimeError("tesseract missing")

    monkeypatch.setattr("engine.ocr_plugins.tesseract._call_tesseract", raise_missing)

    result = TesseractOcrPlugin().recognize(
        str(image_path),
        {"languages": ["chi_sim", "eng"], "psm": 6, "preprocess": {"grayscale": True}},
    )

    assert result.plugin == "tesseract"
    assert result.status == "unavailable"
    assert result.text == ""
    assert result.manual_review_required is True
    assert "tesseract missing" in result.error


def test_tesseract_success_returns_text(monkeypatch, tmp_path):
    """Tesseract 插件成功时返回文本。"""
    from engine.ocr_plugins.tesseract import TesseractOcrPlugin

    image_path = tmp_path / "table.png"
    image_path.write_bytes(b"fake-image")
    monkeypatch.setattr("engine.ocr_plugins.tesseract._call_tesseract", lambda *args, **kwargs: "序号 | 数据名称\n1 | 企业登记数据集")

    result = TesseractOcrPlugin().recognize(str(image_path), {"languages": ["chi_sim", "eng"], "psm": 6})

    assert result.status == "success"
    assert result.text == "序号 | 数据名称\n1 | 企业登记数据集"
    assert result.manual_review_required is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_ocr_plugins.py::test_default_tesseract_plugin_is_registered tests/test_ocr_plugins.py::test_tesseract_unavailable_returns_manual_review tests/test_ocr_plugins.py::test_tesseract_success_returns_text -q`

Expected: FAIL，提示 `tesseract` 插件未注册或模块不存在。

- [ ] **Step 3: 实现 Tesseract 插件**

创建 `APP/engine/engine/ocr_plugins/tesseract.py`：

```python
"""Tesseract OCR 插件。"""

from __future__ import annotations

import time
from pathlib import Path

from .base import OcrResult


def _call_tesseract(image_path: str, languages: list[str], psm: int, preprocess: dict) -> str:
    """调用 pytesseract，把图片转换为文本。"""
    from PIL import Image
    import pytesseract

    image = Image.open(image_path)
    resize_ratio = float((preprocess or {}).get("resize_ratio") or 1)
    if resize_ratio > 1:
        image = image.resize((int(image.width * resize_ratio), int(image.height * resize_ratio)))
    if (preprocess or {}).get("grayscale"):
        image = image.convert("L")
    if (preprocess or {}).get("threshold"):
        image = image.point(lambda value: 255 if value > 180 else 0)

    lang = "+".join(languages or ["chi_sim", "eng"])
    config = f"--psm {int(psm or 6)}"
    return pytesseract.image_to_string(image, lang=lang, config=config)


class TesseractOcrPlugin:
    """本地 Tesseract OCR 插件。"""

    name = "tesseract"

    def recognize(self, image_path: str, config: dict) -> OcrResult:
        """识别图片，失败时返回人工复核状态。"""
        started_at = time.time()
        try:
            if not Path(image_path).exists():
                raise FileNotFoundError(f"图片文件不存在: {image_path}")
            text = _call_tesseract(
                image_path,
                (config or {}).get("languages") or ["chi_sim", "eng"],
                int((config or {}).get("psm") or 6),
                (config or {}).get("preprocess") or {},
            ).strip()
            status = "empty" if text == "" else "success"
            return OcrResult(
                plugin=self.name,
                status=status,
                text=text,
                error="",
                elapsed_seconds=round(time.time() - started_at, 4),
            )
        except Exception as exc:
            return OcrResult(
                plugin=self.name,
                status="unavailable",
                text="",
                error=str(exc),
                elapsed_seconds=round(time.time() - started_at, 4),
            )
```

- [ ] **Step 4: 默认注册 Tesseract 插件**

修改 `APP/engine/engine/ocr_plugins/__init__.py` 为：

```python
"""OCR 插件入口。"""

from .base import OcrPlugin, OcrResult
from .registry import get_ocr_plugin, list_ocr_plugins, register_ocr_plugin, resolve_ocr_plugin_name
from .tesseract import TesseractOcrPlugin

register_ocr_plugin(TesseractOcrPlugin())

__all__ = [
    "OcrPlugin",
    "OcrResult",
    "TesseractOcrPlugin",
    "get_ocr_plugin",
    "list_ocr_plugins",
    "register_ocr_plugin",
    "resolve_ocr_plugin_name",
]
```

- [ ] **Step 5: 增加 Python 依赖**

在 `APP/engine/requirements.txt` 的 `# Utils` 前增加：

```text
# OCR
Pillow>=10.0.0
pytesseract>=0.3.10
```

- [ ] **Step 6: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_ocr_plugins.py -q`

Expected: PASS。

---

### Task 4: 图片发现、下载和插件调度

**Files:**
- Create: `APP/engine/engine/image_extraction.py`
- Test: `APP/engine/tests/test_image_extraction.py`

- [ ] **Step 1: 写失败测试**

创建 `APP/engine/tests/test_image_extraction.py`：

```python
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


def _rule(tmp_path, plugin="fake_image_ocr"):
    return {
        "source": {"url": "https://www.hubei.gov.cn/path/article.shtml", "platform": "hubei_gov"},
        "image_extraction": {
            "enabled": True,
            "trigger": {"when_empty": False, "domains": ["hubei.gov.cn"], "img_keywords": ["数据", "png"]},
            "images": {"selector": ".hbgov-article-content img", "src_attribute": "src", "include_alt": True, "max_images": 5},
            "download": {"dir_template": str(tmp_path / "{task_id}"), "retries": 1, "timeout_seconds": 3, "max_size_mb": 1},
            "ocr": {"plugin": plugin, "languages": ["chi_sim", "eng"], "psm": 6},
            "parse": {"mode": "table", "delimiters": ["|"], "column_mapping": {"序号": "id", "数据名称": "name"}},
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_extraction.py -q`

Expected: FAIL，提示 `ModuleNotFoundError: No module named 'engine.image_extraction'`。

- [ ] **Step 3: 实现图片扩展模块**

创建 `APP/engine/engine/image_extraction.py`，核心代码必须通过注册表调用插件：

```python
"""图片 OCR 采集扩展。"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import parsel
import requests

from .image_parser import parse_ocr_text
from .ocr_plugins import get_ocr_plugin, resolve_ocr_plugin_name


class ImageExtractionRunner:
    """按 Rule v2 image_extraction 配置执行图片 OCR 补充采集。"""

    def __init__(self, rule: dict):
        self.rule = rule
        self.config = rule.get("image_extraction") or {}
        self.summary = {
            "enabled": bool(self.config.get("enabled")),
            "triggered": False,
            "plugin": resolve_ocr_plugin_name((self.config.get("ocr") or {})),
            "images_found": 0,
            "images_downloaded": 0,
            "ocr_success": 0,
            "manual_review_required": 0,
            "errors": [],
        }

    def should_run(self, html: str, current_items: list[dict], page_url: str) -> bool:
        """判断是否需要进入图片 OCR 链路。"""
        if not self.config.get("enabled"):
            return False
        trigger = self.config.get("trigger") or {}
        if trigger.get("when_empty") and not current_items:
            return True
        hostname = urlparse(page_url or self.rule.get("source", {}).get("url", "")).hostname or ""
        if any(domain in hostname for domain in trigger.get("domains") or []):
            return True
        return any(self._image_matches_keyword(candidate, trigger.get("img_keywords") or []) for candidate in self.discover_images(html, page_url))

    def discover_images(self, html: str, page_url: str) -> list[dict]:
        """从页面 HTML 中发现图片候选。"""
        images = self.config.get("images") or {}
        selector_text = images.get("selector") or "img"
        src_attribute = images.get("src_attribute") or "src"
        max_images = int(images.get("max_images") or 10)
        selector = parsel.Selector(text=html or "")
        candidates = []
        for node in selector.css(selector_text)[:max_images]:
            src = node.attrib.get(src_attribute, "").strip()
            if not src:
                continue
            alt = node.attrib.get("alt", "").strip() if images.get("include_alt", True) else ""
            candidates.append({"source_img_url": urljoin(page_url, src), "source_img_alt": alt, "raw_src": src})
        self.summary["images_found"] = len(candidates)
        return candidates

    def extract(self, html: str, current_items: list[dict], page_url: str | None = None) -> list[dict]:
        """执行图片 OCR 并返回补充记录。"""
        page_url = page_url or self.rule.get("source", {}).get("url", "")
        if not self.should_run(html, current_items, page_url):
            return []
        self.summary["triggered"] = True
        records = []
        for candidate in self.discover_images(html, page_url):
            if not self._image_matches_keyword(candidate, (self.config.get("trigger") or {}).get("img_keywords") or []):
                domains = (self.config.get("trigger") or {}).get("domains") or []
                hostname = urlparse(page_url).hostname or ""
                if not any(domain in hostname for domain in domains):
                    continue
            try:
                image_path = self.download_image(candidate["source_img_url"])
                self.summary["images_downloaded"] += 1
                ocr_config = self.config.get("ocr") or {}
                plugin = get_ocr_plugin(resolve_ocr_plugin_name(ocr_config))
                ocr_result = plugin.recognize(image_path, ocr_config)
                if ocr_result.status == "success":
                    self.summary["ocr_success"] += 1
                parsed_records, parse_errors, semi_structured = parse_ocr_text(ocr_result.text, self.config.get("parse") or {})
                if ocr_result.empty:
                    parsed_records = [{"title": "OCR 半结构化结果", "ocr_text": ""}]
                    parse_errors = parse_errors or ["OCR 结果为空"]
                    semi_structured = True
                for record in parsed_records:
                    merged = dict(record)
                    ocr_fields = ocr_result.to_item_fields()
                    if not merged.get("ocr_text"):
                        merged["ocr_text"] = ocr_fields["ocr_text"]
                    merged.update({
                        "source_url": page_url,
                        "source_img_url": candidate["source_img_url"],
                        "source_img_path": image_path,
                        "source_img_alt": candidate.get("source_img_alt", ""),
                        **ocr_fields,
                        "semi_structured": bool(semi_structured),
                        "manual_review_required": bool(ocr_fields["manual_review_required"] or semi_structured),
                        "parse_errors": parse_errors,
                    })
                    if merged["manual_review_required"]:
                        self.summary["manual_review_required"] += 1
                    records.append(merged)
            except Exception as exc:
                self.summary["errors"].append(str(exc))
        return records

    def download_image(self, url: str) -> str:
        """下载图片到规则配置的缓存目录。"""
        download = self.config.get("download") or {}
        task_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
        directory = Path((download.get("dir_template") or "/tmp/scraper_imgs/{task_id}").format(task_id=task_id))
        directory.mkdir(parents=True, exist_ok=True)
        ext = Path(urlparse(url).path).suffix.lower()
        if ext not in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}:
            ext = ".img"
        path = directory / f"{hashlib.sha256(url.encode('utf-8')).hexdigest()}{ext}"
        max_bytes = int(float(download.get("max_size_mb") or 5) * 1024 * 1024)
        retries = int(download.get("retries") or 3)
        timeout = int(download.get("timeout_seconds") or 15)
        interval = float(download.get("retry_interval_seconds") or 0)
        last_error = None
        for attempt in range(retries):
            try:
                response = requests.get(url, timeout=timeout)
                response.raise_for_status()
                content = response.content
                if len(content) > max_bytes:
                    raise ValueError(f"图片超过大小限制: {url}")
                path.write_bytes(content)
                return str(path)
            except Exception as exc:
                last_error = exc
                if attempt < retries - 1 and interval > 0:
                    time.sleep(interval)
        raise RuntimeError(f"图片下载失败: {url}: {last_error}")

    def _image_matches_keyword(self, candidate: dict, keywords: list[str]) -> bool:
        if not keywords:
            return True
        text = " ".join([candidate.get("source_img_url", ""), candidate.get("source_img_alt", "")]).lower()
        return any(str(keyword).lower() in text for keyword in keywords)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_parser.py tests/test_ocr_plugins.py tests/test_image_extraction.py -q`

Expected: PASS。

---

### Task 5: 接入 InfoCollectorEngine 与试采摘要

**Files:**
- Modify: `APP/engine/engine/engine.py`
- Test: `APP/engine/tests/test_rule_preview.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_rule_preview.py` 追加：

```python
def test_preview_rule_includes_ocr_summary_and_items(tmp_path, monkeypatch):
    """试采应走 OCR 插件链路并返回摘要。"""
    from engine.engine import InfoCollectorEngine
    from engine.ocr_plugins import OcrResult, register_ocr_plugin

    class PreviewOcrPlugin:
        name = "preview_ocr"

        def recognize(self, image_path: str, config: dict) -> OcrResult:
            return OcrResult(plugin=self.name, status="success", text="序号 | 数据名称\n1 | 企业登记数据集", error="", elapsed_seconds=0.01)

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
    monkeypatch.setattr("engine.image_extraction.ImageExtractionRunner.download_image", lambda *args, **kwargs: str(tmp_path / "table.png"))

    result = engine.preview_rule(str(rule_path), limit=10)

    assert result["ocr_summary"]["triggered"] is True
    assert result["ocr_summary"]["plugin"] == "preview_ocr"
    assert result["ocr_summary"]["images_found"] == 1
    assert any(item.get("ocr_plugin") == "preview_ocr" for item in result["items"])
    assert any(item.get("source_img_url") == "https://www.hubei.gov.cn/upload/table.png" for item in result["items"])

    engine.close()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_preview.py::test_preview_rule_includes_ocr_summary_and_items -q`

Expected: FAIL，提示 `ocr_summary` 不存在或没有 OCR 记录。

- [ ] **Step 3: 修改引擎接入 OCR**

在 `APP/engine/engine/engine.py` 顶部增加：

```python
from .image_extraction import ImageExtractionRunner
```

在 `InfoCollectorEngine.__init__()` 中增加：

```python
        self.last_ocr_summary = {}
```

新增方法：

```python
    def _append_image_extraction_items(self, html_content: str, items: list, rule: dict, page_url: str) -> list:
        """在标准网页采集结果后追加图片 OCR 记录。"""
        runner = ImageExtractionRunner(rule)
        ocr_items = runner.extract(html_content, items, page_url=page_url)
        self.last_ocr_summary = runner.summary
        if ocr_items:
            return items + ocr_items
        return items
```

修改 `_crawl_html()` 和 `_crawl_browser()`：所有网页提取分支都先得到 `items`，返回前统一调用：

```python
        return self._append_image_extraction_items(html_content, items, rule, url)
```

修改 `preview_rule()` 的 disabled 返回值和成功返回值，增加：

```python
            "ocr_summary": self.last_ocr_summary,
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_preview.py tests/test_image_parser.py tests/test_ocr_plugins.py tests/test_image_extraction.py -q`

Expected: PASS。

---

### Task 6: Rule v2 校验 OCR 插件边界

**Files:**
- Modify: `APP/engine/engine/rule_parser.py`
- Test: `APP/engine/tests/test_rule_v2.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_rule_v2.py` 追加：

```python
def test_rule_parser_accepts_local_registered_ocr_plugin():
    """Rule v2 允许本地已注册 OCR 插件配置。"""
    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "ocr-rule",
        "source_id": "ocr-source",
        "version": 1,
        "source": {"type": "html", "platform": "hubei_gov", "url": "https://www.hubei.gov.cn/a.shtml"},
        "list": {"items_path": "css:article"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "image_extraction": {
            "enabled": True,
            "images": {"selector": "img"},
            "ocr": {"plugin": "tesseract", "languages": ["chi_sim", "eng"]},
            "parse": {"mode": "table", "column_mapping": {"序号": "id"}},
        },
    }

    assert RuleParser().validate(rule) is True


def test_rule_parser_keeps_engine_field_compatibility_for_tesseract():
    """Rule v2 兼容旧 engine 字段指定 Tesseract。"""
    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "ocr-rule",
        "source_id": "ocr-source",
        "version": 1,
        "source": {"type": "html", "platform": "hubei_gov", "url": "https://www.hubei.gov.cn/a.shtml"},
        "list": {"items_path": "css:article"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "image_extraction": {"enabled": True, "ocr": {"engine": "tesseract"}},
    }

    assert RuleParser().validate(rule) is True


def test_rule_parser_rejects_cloud_or_ai_ocr_config():
    """Rule v2 禁止云 OCR 或 AI/视觉模型 OCR 配置。"""
    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "ocr-rule",
        "source_id": "ocr-source",
        "version": 1,
        "source": {"type": "html", "platform": "hubei_gov", "url": "https://www.hubei.gov.cn/a.shtml"},
        "list": {"items_path": "css:article"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "image_extraction": {"enabled": True, "ocr": {"plugin": "vision_model", "api_key": "secret"}},
    }

    try:
        RuleParser().validate(rule)
    except ValueError as exc:
        assert "image_extraction" in str(exc)
    else:
        raise AssertionError("AI 或云 OCR 配置必须校验失败")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_v2.py::test_rule_parser_rejects_cloud_or_ai_ocr_config -q`

Expected: FAIL，因为当前未校验 `image_extraction.ocr.plugin`。

- [ ] **Step 3: 实现规则校验**

在 `RuleParser` 中增加：

```python
    def _validate_image_extraction(self, rule: dict):
        """校验图片 OCR 配置只能使用本地已注册插件。"""
        config = rule.get("image_extraction")
        if not config:
            return
        if not isinstance(config, dict):
            raise ValueError("image_extraction must be an object")
        ocr = config.get("ocr") or {}
        blocked_keys = {"agent", "llm", "vision_model", "cloud_ocr", "api_key"}
        found = blocked_keys.intersection(set(ocr.keys()) | set(config.keys()))
        if found:
            raise ValueError(f"image_extraction 禁止 AI、Agent 或云 OCR 配置: {', '.join(sorted(found))}")
        from .ocr_plugins import list_ocr_plugins, resolve_ocr_plugin_name

        plugin_name = resolve_ocr_plugin_name(ocr)
        if plugin_name not in list_ocr_plugins():
            raise ValueError(f"image_extraction.ocr.plugin 未注册: {plugin_name}")
```

在 `_validate_rule_v2()` 和旧规则 `validate()` 路径中调用：

```python
        self._validate_image_extraction(rule)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_v2.py -q`

Expected: PASS。

---

### Task 7: 规则中心试采展示 OCR 插件摘要

**Files:**
- Modify: `APP/dashboard/static/js/app.js`
- Test: `APP/dashboard/tests/test_rules_preview_api.py`

- [ ] **Step 1: 写 API 回归测试**

在 `APP/dashboard/tests/test_rules_preview_api.py` 追加：

```python
def test_preview_rule_response_contains_ocr_summary(monkeypatch):
    """规则试采 API 返回 OCR 摘要字段。"""
    from engine import crawl_html

    class FakeResponse:
        text = "<article><h1>沙箱</h1></article>"
        apparent_encoding = "utf-8"
        encoding = "utf-8"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(crawl_html.requests, "get", lambda *args, **kwargs: FakeResponse())

    yaml_content = """
rule_id: "preview-api-rule"
source_id: "preview-api-source"
version: 1
status: DRAFT
source:
  platform: "preview-api"
  type: "html"
  url: "https://example.com"
list:
  items_path: "css:article"
extract:
  title: { selector: "h1", type: "text" }
output:
  fields: ["title"]
  save_raw: false
governance:
  sanitize: true
""".strip()
    client = app.test_client()

    response = client.post("/api/rules/preview", json={"yaml": yaml_content, "limit": 5})

    assert response.status_code == 200
    assert response.get_json()["ocr_summary"] == {}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest APP/dashboard/tests/test_rules_preview_api.py::test_preview_rule_response_contains_ocr_summary -q`

Expected: FAIL，如果 Task 5 尚未完成；Task 5 完成后应 PASS。

- [ ] **Step 3: 修改规则中心前端展示**

在 `APP/dashboard/static/js/app.js` 的试采结果面板中，将：

```html
        <p>总条数：{{ previewResult.total_collected }}，展示：{{ previewResult.preview_count }}</p>
        <pre>{{ prettyJson(previewResult.items || []) }}</pre>
```

替换为：

```html
        <p>总条数：{{ previewResult.total_collected }}，展示：{{ previewResult.preview_count }}</p>
        <p v-if="previewResult.ocr_summary && previewResult.ocr_summary.enabled">
          OCR 插件：{{ previewResult.ocr_summary.plugin || 'tesseract' }}，
          图片 {{ previewResult.ocr_summary.images_found || 0 }} 张，
          下载 {{ previewResult.ocr_summary.images_downloaded || 0 }} 张，
          识别成功 {{ previewResult.ocr_summary.ocr_success || 0 }} 张，
          人工复核 {{ previewResult.ocr_summary.manual_review_required || 0 }} 条
        </p>
        <pre>{{ prettyJson(previewResult.items || []) }}</pre>
```

- [ ] **Step 4: 运行 Dashboard 测试确认通过**

Run: `python -m pytest APP/dashboard/tests/test_rules_preview_api.py -q`

Expected: PASS。

---

### Task 8: 单次验证 hubei 采集规则

**Files:**
- No code changes.

- [ ] **Step 1: 运行 OCR 相关测试集合**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_image_parser.py tests/test_ocr_plugins.py tests/test_image_extraction.py tests/test_rule_v2.py tests/test_rule_preview.py -q`

Expected: PASS。

- [ ] **Step 2: 运行 Dashboard 试采 API 测试**

Run: `python -m pytest APP/dashboard/tests/test_rules_preview_api.py -q`

Expected: PASS。

- [ ] **Step 3: 检查本机 Tesseract 是否可用**

Run: `tesseract --version`

Expected:
- 若命令成功：继续 Step 4。
- 若返回 `command not found`：记录验证阻塞，说明插件链路已就绪但默认 `tesseract` 插件缺少系统依赖，需要安装 `tesseract-ocr`、`tesseract-ocr-chi-sim`、`tesseract-ocr-eng` 后才能完成真实 OCR。

- [ ] **Step 4: 单次执行 hubei 规则**

Run: `cd APP/engine && ./venv.sh run python engine_cli.py run-rule "rules/数据要素/hubei_gov_image_ocr_article.yaml" --format=json`

Expected:
- 命令退出码为 0。
- JSON 中 `success` 为 `true`，或当 OCR 环境缺失时输出失败原因包含 Tesseract 缺失。
- 若成功写出文件，打开最新 `APP/engine/output/数据要素/hubei_gov_image_ocr_article_*.json`，确认 `data` 中至少存在 `source_img_url`、`ocr_plugin`、`ocr_text`、`manual_review_required` 字段。

- [ ] **Step 5: 汇总验证结果**

在最终回复中说明：
- 已运行哪些测试，结果如何。
- hubei 单次验证是否成功。
- 若 Tesseract 未安装，明确列出缺失系统依赖和下一步命令建议，不声称 OCR 实际完成。

---

## 后续更换 OCR 组件方式

以后新增更好的 OCR 组件时，只需：

1. 新增 `APP/engine/engine/ocr_plugins/paddle.py` 或其他插件文件。
2. 实现 `name` 和 `recognize(image_path, config)`。
3. 在 `ocr_plugins/__init__.py` 注册插件。
4. 将 YAML 改为：

```yaml
image_extraction:
  ocr:
    plugin: "paddle"
```

主引擎、图片下载、OCR 文本解析、输出字段和规则中心预览都不需要改。

---

## 自检

- 需求覆盖：计划覆盖图片发现、相对 URL 补全、下载、OCR 插件调用、文本解析、`ocr_plugin`、`ocr_text`、`source_img_url`、`manual_review_required`、规则预览和 hubei 单次验证。
- 插件化覆盖：OCR 调用被隔离在 `ocr_plugins` 包中，`image_extraction` 只依赖注册表。
- 边界覆盖：默认只实现本地 Tesseract 插件，不引入 Agent、云 OCR、视觉模型或 Crawl4AI。
- TDD 覆盖：每个生产代码任务都有失败测试、失败确认、实现和通过确认步骤。
- 风险说明：真实 hubei OCR 验证依赖系统级 `tesseract` 和中文语言包；如果本机未安装，只能验证代码链路和人工复核降级状态。
