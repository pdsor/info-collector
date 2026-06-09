"""PaddleOCR 子进程插件。"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from .base import OcrResult


def _engine_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_python() -> Path:
    return _engine_root() / ".venv-paddleocr" / "bin" / "python"


def _default_runner() -> Path:
    return _engine_root() / "run_paddleocr_image_test.py"


def _default_home() -> Path:
    return Path("/tmp/paddleocr-home")


def _build_command(image_path: str, config: dict, output_path: Path) -> list[str]:
    """构建 PaddleOCR 测试脚本命令，避免在主引擎虚拟环境内直接 import。"""
    config = config or {}
    python_path = Path(config.get("python") or os.getenv("PADDLEOCR_PYTHON") or _default_python())
    runner_path = Path(config.get("runner") or _default_runner())
    home = Path(config.get("home") or _default_home())
    det_model = config.get("text_detection_model_name") or config.get("det_model") or "PP-OCRv5_mobile_det"
    rec_model = config.get("text_recognition_model_name") or config.get("rec_model") or "PP-OCRv5_mobile_rec"
    limit_side_len = str(int(config.get("text_det_limit_side_len") or config.get("limit_side_len") or 960))
    lang = config.get("lang") or "ch"

    return [
        str(python_path),
        str(runner_path),
        image_path,
        "--output",
        str(output_path),
        "--home",
        str(home),
        "--lang",
        lang,
        "--det-model",
        det_model,
        "--rec-model",
        rec_model,
        "--limit-side-len",
        limit_side_len,
    ]


def _load_payload(output_path: Path) -> dict:
    if not output_path.exists():
        raise FileNotFoundError(f"PaddleOCR 结果文件不存在: {output_path}")
    return json.loads(output_path.read_text(encoding="utf-8"))


def _read_quality_thresholds(config: dict) -> tuple[int, int, int]:
    """读取 OCR 通用质量阈值。"""
    return (
        int(config.get("min_text_length") or 20),
        int(config.get("min_line_count") or 2),
        int(config.get("large_image_pixels") or 200000),
    )


def _image_pixels(image_info: dict) -> int:
    """计算图片像素数量。"""
    width = int(image_info.get("width") or 0)
    height = int(image_info.get("height") or 0)
    return width * height


def _evaluate_quality(text: str, payload: dict, config: dict) -> tuple[str, str, list[str]]:
    """根据通用 OCR 指标评估质量状态。"""
    stripped = text.strip()
    min_text_length, min_line_count, large_image_pixels = _read_quality_thresholds(config)
    lines = payload.get("lines") or []
    line_count = len(lines)
    image_pixels = _image_pixels(payload.get("image") or {})

    if not stripped:
        return "empty", "empty", ["empty_text"]
    if len(stripped) < min_text_length:
        return "success_low_confidence", "manual_review_required", ["text_too_short"]
    if line_count < min_line_count and image_pixels >= large_image_pixels:
        return "success_low_confidence", "manual_review_required", ["large_image_too_few_lines"]
    return "success", "usable", []


class PaddleOcrPlugin:
    """通过独立 PaddleOCR 虚拟环境识别图片。"""

    name = "paddleocr"

    def recognize(self, image_path: str, config: dict) -> OcrResult:
        """识别图片，返回 Markdown 优先的 OCR 文本和可审计结构化数据。"""
        started_at = time.time()
        output_path = None
        try:
            if not Path(image_path).exists():
                raise FileNotFoundError(f"图片文件不存在: {image_path}")

            with tempfile.NamedTemporaryFile(prefix="paddleocr_", suffix=".json", delete=False) as output_file:
                output_path = Path(output_file.name)

            config = config or {}
            timeout_seconds = int(config.get("timeout_seconds") or 7200)
            command = _build_command(image_path, config, output_path)
            python_path = Path(command[0])
            runner_path = Path(command[1])
            if not python_path.exists():
                raise FileNotFoundError(f"PaddleOCR Python 不存在: {python_path}")
            if not runner_path.exists():
                raise FileNotFoundError(f"PaddleOCR runner 不存在: {runner_path}")

            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            if completed.returncode != 0:
                stderr = (completed.stderr or "").strip()
                stdout = (completed.stdout or "").strip()
                raise RuntimeError(stderr or stdout or f"PaddleOCR 退出码: {completed.returncode}")

            payload = _load_payload(output_path)
            markdown = payload.get("table_markdown") or ""
            raw_text = payload.get("text") or ""
            text = markdown or raw_text
            status, quality_status, quality_reasons = _evaluate_quality(text, payload, config)
            structured_data = {
                "raw_text": raw_text,
                "markdown": markdown,
                "corrections": payload.get("corrections") or [],
                "lines": payload.get("lines") or [],
                "image": payload.get("image") or {},
                "config": payload.get("config") or {},
                "runner_wall_seconds": payload.get("wall_seconds"),
            }
            return OcrResult(
                plugin=self.name,
                status=status,
                text=text,
                error="",
                elapsed_seconds=round(time.time() - started_at, 4),
                structured_data=structured_data,
                quality_status=quality_status,
                quality_reasons=quality_reasons,
            )
        except subprocess.TimeoutExpired as exc:
            return OcrResult(
                plugin=self.name,
                status="timeout",
                text="",
                error=f"PaddleOCR 超时: {exc.timeout}s",
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
        finally:
            if output_path and output_path.exists():
                try:
                    output_path.unlink()
                except OSError:
                    pass
