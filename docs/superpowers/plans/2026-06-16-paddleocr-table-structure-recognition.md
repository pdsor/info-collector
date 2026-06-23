# PaddleOCR 表格结构识别 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不做针对单张图片硬修的前提下，评估并接入 PaddleOCR 3.6.0 的表格结构识别能力，解决整图 OCR 对窄序号列漏检导致表格行中断的问题。

**Architecture:** 先新增离线诊断 runner，对同一图片输出普通 OCR、表格结构识别、结构化单元格和诊断摘要，不影响生产任务。验证稳定后，在 `PaddleOcrPlugin` 中增加可配置的 `table_structure` 模式，把结构识别结果作为 `structured_data.table_structure` 和优先 Markdown 输出；失败时回退当前普通 OCR 文本链路。

**Tech Stack:** Python、pytest、PaddleOCR 3.6.0、TableRecognitionPipelineV2、PostgreSQL 已存 OCR 资产、JSON 诊断产物。

---

### Task 1: 新增表格结构识别诊断 runner

**Files:**
- Create: `APP/engine/run_paddleocr_table_structure_test.py`
- Test: `APP/engine/tests/test_paddleocr_table_structure_runner.py`

- [ ] **Step 1: 写 runner 单元测试**

新增 `APP/engine/tests/test_paddleocr_table_structure_runner.py`，覆盖纯解析函数，不直接加载大模型：

```python
"""PaddleOCR 表格结构 runner 测试。"""

from run_paddleocr_table_structure_test import (
    _extract_table_markdown,
    _json_safe,
    _normalize_pipeline_result,
)


def test_json_safe_converts_unknown_objects():
    class Value:
        def __str__(self):
            return "value-object"

    assert _json_safe({"a": Value()}) == {"a": "value-object"}


def test_normalize_pipeline_result_accepts_json_property():
    class Result:
        json = {"res": {"html": "<table></table>", "markdown": "| A |"}}

    payload = _normalize_pipeline_result(Result())

    assert payload["res"]["html"] == "<table></table>"
    assert payload["res"]["markdown"] == "| A |"


def test_extract_table_markdown_prefers_markdown_then_html():
    markdown_payload = {"res": {"markdown": "| 序号 |"}}
    html_payload = {"res": {"html": "<table><tr><td>序号</td></tr></table>"}}

    assert _extract_table_markdown([markdown_payload]) == "| 序号 |"
    assert _extract_table_markdown([html_payload]).startswith("<table>")
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd APP/engine
./venv.sh run python -m pytest tests/test_paddleocr_table_structure_runner.py -q
```

Expected: FAIL，提示 `run_paddleocr_table_structure_test` 不存在。

- [ ] **Step 3: 新增 runner**

新增 `APP/engine/run_paddleocr_table_structure_test.py`：

```python
#!/usr/bin/env python3
"""PaddleOCR 表格结构识别诊断工具。"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image


DEFAULT_OUTPUT = Path("/tmp/paddleocr_table_structure_result.json")
DEFAULT_HOME = Path("/tmp/paddleocr-home")


def _prepare_runtime(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    os.environ["HOME"] = str(home)
    os.environ["XDG_CACHE_HOME"] = str(home / ".cache")
    os.environ["PADDLE_PDX_CACHE_HOME"] = str(home / ".paddlex")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


def _image_info(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "format": image.format,
            "mode": image.mode,
            "width": image.width,
            "height": image.height,
            "pixels": image.width * image.height,
        }


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _normalize_pipeline_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "json"):
        try:
            payload = result.json
            if isinstance(payload, dict):
                return _json_safe(payload)
        except Exception:
            pass
    if hasattr(result, "to_dict"):
        try:
            return _json_safe(result.to_dict())
        except Exception:
            pass
    if isinstance(result, dict):
        return _json_safe(result)
    return {"raw": _json_safe(result)}


def _extract_table_markdown(payloads: list[dict[str, Any]]) -> str:
    for payload in payloads:
        res = payload.get("res") if isinstance(payload.get("res"), dict) else payload
        for key in ("markdown", "table_markdown", "md"):
            value = res.get(key)
            if isinstance(value, str) and value.strip():
                return value
        for key in ("html", "table_html"):
            value = res.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="PaddleOCR 表格结构识别诊断")
    parser.add_argument("image", help="真实图片路径")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="JSON 输出路径")
    parser.add_argument("--home", default=str(DEFAULT_HOME), help="PaddleOCR/PaddleX 可写 HOME 缓存目录")
    parser.add_argument("--limit-side-len", type=int, default=960, help="文本检测输入长边限制")
    parser.add_argument("--preview-chars", type=int, default=2000, help="控制台预览字符数")
    args = parser.parse_args()

    image_path = Path(args.image).expanduser()
    output_path = Path(args.output).expanduser()
    markdown_path = output_path.with_suffix(".md")
    home = Path(args.home).expanduser()
    _prepare_runtime(home)

    if not image_path.exists():
        print(f"图片不存在: {image_path}")
        return 2

    from paddleocr import TableRecognitionPipelineV2

    started_at = datetime.now().isoformat()
    started = time.time()
    pipeline = TableRecognitionPipelineV2(
        text_det_limit_side_len=args.limit_side_len,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_layout_detection=False,
        use_ocr_model=True,
    )
    raw_results = pipeline.predict(str(image_path))
    payloads = [
        _normalize_pipeline_result(item)
        for item in (raw_results if isinstance(raw_results, list) else [raw_results])
    ]
    markdown = _extract_table_markdown(payloads)
    payload = {
        "started_at": started_at,
        "finished_at": datetime.now().isoformat(),
        "wall_seconds": round(time.time() - started, 2),
        "image": _image_info(image_path),
        "config": {
            "pipeline": "TableRecognitionPipelineV2",
            "text_det_limit_side_len": args.limit_side_len,
            "use_layout_detection": False,
            "use_ocr_model": True,
            "home": str(home),
        },
        "table_markdown": markdown,
        "raw_results": payloads,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")
    print(f"wall_seconds: {payload['wall_seconds']}")
    print((markdown or json.dumps(payloads, ensure_ascii=False))[: max(args.preview_chars, 0)])
    print(f"完整 JSON 已写入: {output_path}")
    print(f"Markdown 已写入: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd APP/engine
./venv.sh run python -m pytest tests/test_paddleocr_table_structure_runner.py -q
```

Expected: PASS。

### Task 2: 用医疗健康赛道图片做离线对照

**Files:**
- No production changes.
- Output: `/tmp/nda_medical_table_structure.json`

- [ ] **Step 1: 找到目标图片路径**

Run:

```bash
cd APP/engine
./venv.sh run python - <<'PY'
from sqlalchemy import create_engine, text
from engine.config import get_pg_dsn

title = "2025年“数据要素×”大赛全国总决赛获奖项目案例集——医疗健康赛道"
engine = create_engine(get_pg_dsn())
with engine.connect() as conn:
    row = conn.execute(text("""
        select a.storage_uri
        from archive_pages p
        join archive_assets a on a.page_id = p.id
        where p.title = :title
        order by a.id
        limit 1
    """), {"title": title}).first()
    print(row[0] if row else "")
PY
```

Expected: 输出 `/tmp/scraper_imgs/...jpg`。

- [ ] **Step 2: 运行表格结构识别**

Run:

```bash
cd /home/sor/code/info-collector
APP/engine/.venv-paddleocr/bin/python APP/engine/run_paddleocr_table_structure_test.py \
  /tmp/scraper_imgs/529271f22073/529271f22073d219b7383a90d0c4ce5ec2d1b53ad15d6a19d5c5319545520ad9.jpg \
  --output /tmp/nda_medical_table_structure.json \
  --home /tmp/paddleocr-home \
  --limit-side-len 960 \
  --preview-chars 2000
```

Expected: 命令完成并写出 JSON；如果模型需要下载，记录下载耗时和模型缓存位置。

- [ ] **Step 3: 检查序号连续性**

Run:

```bash
cd APP/engine
./venv.sh run python - <<'PY'
import json
import re
from pathlib import Path

payload = json.loads(Path("/tmp/nda_medical_table_structure.json").read_text(encoding="utf-8"))
text = payload.get("table_markdown") or json.dumps(payload.get("raw_results"), ensure_ascii=False)
nums = [int(item) for item in re.findall(r"(?:^|\|)\s*(\d{1,2})\s*(?:\||<)", text, flags=re.M)]
print(nums)
if nums:
    print([n for n in range(min(nums), max(nums) + 1) if n not in nums])
PY
```

Expected: 如果缺失序号为空，表格结构识别可作为候选生产方案；如果仍缺失，记录为模型能力不足，进入 Task 3 做模型和参数对照。

### Task 3: 模型和参数对照

**Files:**
- No production changes.

- [ ] **Step 1: 尝试启用版面检测**

Run:

```bash
cd /home/sor/code/info-collector
APP/engine/.venv-paddleocr/bin/python - <<'PY'
from pathlib import Path
from runpy import run_path

# 手动用 TableRecognitionPipelineV2(use_layout_detection=True) 做一次对照；
# 如果当前环境缺模型或下载失败，记录错误，不进入生产。
PY
```

Expected: 记录是否可运行、耗时、序号连续性。

- [ ] **Step 2: 尝试 PPStructureV3**

Run:

```bash
HOME=/tmp XDG_CONFIG_HOME=/tmp XDG_CACHE_HOME=/tmp APP/engine/.venv-paddleocr/bin/python - <<'PY'
from paddleocr import PPStructureV3
print(PPStructureV3)
PY
```

Expected: 能 import。后续若初始化模型失败，记录具体模型缺失或下载错误。

- [ ] **Step 3: 形成对照表**

记录以下结果：

```text
方案 | 耗时 | 是否识别 1-13 连续序号 | 是否输出单元格结构 | 是否适合生产
普通 OCR 960 | 约 15s | 否，缺 4/6/7 | 否 | 否
普通 OCR 1600 | 约 122s | 否，缺 4/5/6/7 | 否 | 否
左列裁剪 OCR | 约 18s | 是 | 否 | 只能作为诊断/辅助
TableRecognitionPipelineV2 | 待测 | 待测 | 待测 | 待定
PPStructureV3 | 待测 | 待测 | 待测 | 待定
```

### Task 4: 可配置接入生产链路

**Files:**
- Modify: `APP/engine/engine/ocr_plugins/paddleocr.py`
- Modify: `APP/engine/run_paddleocr_image_test.py`
- Modify: `APP/engine/tests/test_ocr_plugins.py`
- Modify: `APP/engine/rules/数据要素/nda_gov_data_element_cases.yaml`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_ocr_plugins.py` 增加测试，模拟 runner payload 带 `table_structure_markdown`：

```python
def test_paddleocr_prefers_table_structure_markdown(monkeypatch, tmp_path):
    """启用表格结构识别时应优先使用结构化表格 Markdown。"""
    from engine.ocr_plugins.paddleocr import PaddleOcrPlugin

    image_path = tmp_path / "table.png"
    image_path.write_bytes(b"fake-image")
    python_path = tmp_path / "python"
    runner_path = tmp_path / "runner.py"
    python_path.write_text("", encoding="utf-8")
    runner_path.write_text("", encoding="utf-8")

    def fake_run(command, check, capture_output, text, timeout):
        output_path = command[command.index("--output") + 1]
        from pathlib import Path
        from subprocess import CompletedProcess
        import json

        Path(output_path).write_text(json.dumps({
            "text": "普通文本",
            "table_markdown": "| 普通 |",
            "table_structure_markdown": "| 序号 | 案例名称 |\\n| --- | --- |\\n| 1 | 测试 |",
            "table_structure": {"source": "TableRecognitionPipelineV2"},
            "lines": [{"text": "普通文本"}],
            "image": {"width": 100, "height": 50},
            "config": {"table_recognition": True},
        }, ensure_ascii=False), encoding="utf-8")
        return CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("engine.ocr_plugins.paddleocr.subprocess.run", fake_run)

    result = PaddleOcrPlugin().recognize(str(image_path), {
        "python": str(python_path),
        "runner": str(runner_path),
        "table_recognition": True,
    })

    assert result.text.startswith("| 序号 | 案例名称 |")
    assert result.structured_data["table_structure"]["source"] == "TableRecognitionPipelineV2"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd APP/engine
./venv.sh run python -m pytest tests/test_ocr_plugins.py::test_paddleocr_prefers_table_structure_markdown -q
```

Expected: FAIL，因为插件尚未读取 `table_structure_markdown`。

- [ ] **Step 3: 更新 runner 输出结构**

在 `APP/engine/run_paddleocr_image_test.py` 中，当传入 `--table-recognition` 时调用 `TableRecognitionPipelineV2`，并在 payload 增加：

```python
"table_structure_markdown": table_structure_markdown,
"table_structure": {
    "pipeline": "TableRecognitionPipelineV2",
    "raw_results": table_structure_payloads,
}
```

- [ ] **Step 4: 更新插件读取逻辑**

在 `APP/engine/engine/ocr_plugins/paddleocr.py` 中把文本优先级改为：

```python
table_structure_markdown = payload.get("table_structure_markdown") or ""
markdown = payload.get("table_markdown") or ""
raw_text = payload.get("text") or ""
text = table_structure_markdown or markdown or raw_text
```

`structured_data` 增加：

```python
"table_structure": payload.get("table_structure") or {},
```

- [ ] **Step 5: 更新规则配置**

在 `APP/engine/rules/数据要素/nda_gov_data_element_cases.yaml` 的 `archive.image_ocr.ocr` 增加：

```yaml
      table_recognition: true
      table_recognition_pipeline: "TableRecognitionPipelineV2"
```

- [ ] **Step 6: 验证单元测试**

Run:

```bash
cd APP/engine
./venv.sh run python -m pytest tests/test_ocr_plugins.py tests/test_paddleocr_table_structure_runner.py -q
```

Expected: PASS。

### Task 5: 端到端验证和发布判断

**Files:**
- No additional code changes.

- [ ] **Step 1: 清理目标页历史归档**

Run:

```bash
cd APP/engine
./venv.sh run python - <<'PY'
from sqlalchemy import create_engine, text
from engine.config import get_pg_dsn

title = "2025年“数据要素×”大赛全国总决赛获奖项目案例集——医疗健康赛道"
engine = create_engine(get_pg_dsn())
with engine.begin() as conn:
    page_ids = [row[0] for row in conn.execute(text("select id from archive_pages where title = :title"), {"title": title})]
    if page_ids:
        conn.execute(text("delete from structured_records where page_id = any(:ids)"), {"ids": page_ids})
        conn.execute(text("delete from ocr_results where page_id = any(:ids)"), {"ids": page_ids})
        conn.execute(text("delete from archive_assets where page_id = any(:ids)"), {"ids": page_ids})
        conn.execute(text("delete from archive_blocks where page_id = any(:ids)"), {"ids": page_ids})
        conn.execute(text("delete from archive_pages where id = any(:ids)"), {"ids": page_ids})
    print(len(page_ids))
PY
```

Expected: 输出删除页数量。

- [ ] **Step 2: 手动或 CLI 重跑规则**

Run:

```bash
cd APP/engine
./venv.sh run python engine_cli.py run-rule rules/数据要素/nda_gov_data_element_cases.yaml --format=json
```

Expected: 医疗健康赛道页面重新 OCR 写入。

- [ ] **Step 3: 检查目标页序号连续性**

Run:

```bash
cd APP/engine
./venv.sh run python - <<'PY'
import re
from sqlalchemy import create_engine, text
from engine.config import get_pg_dsn

title = "2025年“数据要素×”大赛全国总决赛获奖项目案例集——医疗健康赛道"
engine = create_engine(get_pg_dsn())
with engine.connect() as conn:
    text_value = conn.execute(text("""
        select r.ocr_text
        from archive_pages p
        join ocr_results r on r.page_id = p.id
        where p.title = :title
        order by r.id desc
        limit 1
    """), {"title": title}).scalar_one()

nums = [int(m.group(1)) for m in re.finditer(r"^\|\s*(\d+)\s*\|", text_value, flags=re.M)]
print(nums)
print([n for n in range(min(nums), max(nums) + 1) if n not in nums] if nums else [])
PY
```

Expected: 若缺失为空，进入发布候选；若仍缺序号，保留诊断输出，不启用生产配置。

- [ ] **Step 4: 全量验证**

Run:

```bash
cd APP/engine
./venv.sh run python -m pytest tests -q
APP/engine/venv.sh run python -m pytest APP/dashboard/tests -q
cd APP/dashboard/web
npm run build
```

Expected: 后端和构建通过。

---

## Self-Review

- Spec coverage: 覆盖用户选择的“表格结构识别模型”，先诊断、再可配置接入、最后端到端验证。
- Placeholder scan: 无待填占位符；模型类名来自本地 PaddleOCR 3.6.0 导出：`TableRecognitionPipelineV2`、`PPStructureV3`。
- Type consistency: runner 输出 `table_structure_markdown` 与插件读取字段一致，结构化数据统一进入 `structured_data.table_structure`。
