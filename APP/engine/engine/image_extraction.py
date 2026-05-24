"""图片 OCR 采集扩展。"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import parsel
import requests

from .image_parser import parse_ocr_result
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
        return any(
            self._image_matches_keyword(candidate, trigger.get("img_keywords") or [])
            for candidate in self.discover_images(html, page_url)
        )

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
        next_row_id = 1
        for candidate in self.discover_images(html, page_url):
            if not self._should_process_candidate(candidate, page_url):
                continue
            try:
                image_path = self.download_image(candidate["source_img_url"])
                self.summary["images_downloaded"] += 1
                ocr_config = self.config.get("ocr") or {}
                plugin = get_ocr_plugin(resolve_ocr_plugin_name(ocr_config))
                ocr_result = plugin.recognize(image_path, ocr_config)
                if ocr_result.status == "success":
                    self.summary["ocr_success"] += 1
                parsed_records, parse_errors, semi_structured = parse_ocr_result(
                    ocr_result,
                    self.config.get("parse") or {},
                )
                if (self.config.get("parse") or {}).get("renumber_rows"):
                    for record in parsed_records:
                        if record.get("id"):
                            record["id"] = str(next_row_id)
                            row_text = record.get("ocr_text") or ""
                            parts = row_text.split(" ", 1)
                            if parts:
                                parts[0] = record["id"]
                                record["ocr_text"] = " ".join(parts).strip()
                            next_row_id += 1
                has_structured_words = bool(((getattr(ocr_result, "structured_data", None) or {}).get("words") or []))
                if ocr_result.empty and not has_structured_words:
                    parsed_records = [{"title": "OCR 半结构化结果", "ocr_text": ""}]
                    parse_errors = ["OCR 结果为空"]
                    semi_structured = True
                records.extend(
                    self._merge_records(
                        parsed_records,
                        parse_errors,
                        semi_structured,
                        ocr_result,
                        candidate,
                        image_path,
                        page_url,
                    )
                )
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

    def _merge_records(
        self,
        parsed_records: list[dict],
        parse_errors: list[str],
        semi_structured: bool,
        ocr_result,
        candidate: dict,
        image_path: str,
        page_url: str,
    ) -> list[dict]:
        records = []
        for record in parsed_records:
            merged = dict(record)
            ocr_fields = ocr_result.to_item_fields()
            merged.update({
                "source_url": page_url,
                "source_img_url": candidate["source_img_url"],
                "source_img_path": image_path,
                "source_img_alt": candidate.get("source_img_alt", ""),
                **ocr_fields,
                "semi_structured": bool(semi_structured),
                "manual_review_required": bool(ocr_fields["manual_review_required"] or semi_structured or parse_errors),
                "parse_errors": parse_errors,
            })
            if record.get("ocr_text"):
                merged["ocr_text"] = record["ocr_text"]
            if merged["manual_review_required"]:
                self.summary["manual_review_required"] += 1
            records.append(merged)
        return records

    def _should_process_candidate(self, candidate: dict, page_url: str) -> bool:
        trigger = self.config.get("trigger") or {}
        if self._image_matches_keyword(candidate, trigger.get("img_keywords") or []):
            return True
        hostname = urlparse(page_url).hostname or ""
        return any(domain in hostname for domain in trigger.get("domains") or [])

    def _image_matches_keyword(self, candidate: dict, keywords: list[str]) -> bool:
        if not keywords:
            return True
        text = " ".join([candidate.get("source_img_url", ""), candidate.get("source_img_alt", "")]).lower()
        return any(str(keyword).lower() in text for keyword in keywords)
