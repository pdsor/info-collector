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
        return _json_safe(value.tolist())
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
    normalized_payloads = [
        payload.get("res") if isinstance(payload.get("res"), dict) else payload
        for payload in payloads
    ]
    table_payloads = []
    for res in normalized_payloads:
        table_payloads.append(res)
        table_res_list = res.get("table_res_list")
        if isinstance(table_res_list, list):
            table_payloads.extend(item for item in table_res_list if isinstance(item, dict))
    for res in table_payloads:
        for key in ("markdown", "table_markdown", "md"):
            value = res.get(key)
            if isinstance(value, str) and value.strip():
                return value
    for res in table_payloads:
        for key in ("html", "table_html", "pred_html"):
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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")
    print(f"wall_seconds: {payload['wall_seconds']}")
    print((markdown or json.dumps(payloads, ensure_ascii=False))[: max(args.preview_chars, 0)])
    print(f"完整 JSON 已写入: {output_path}")
    print(f"Markdown 已写入: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
