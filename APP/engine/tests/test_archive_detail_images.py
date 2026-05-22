"""详情页归档的图片资产与 OCR 块测试。"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from engine.engine import InfoCollectorEngine


LIST_HTML = """
<html><body>
  <ul class="news-list">
    <li><a href="/detail/1.shtml">高质量数据集名单公示</a></li>
  </ul>
</body></html>
"""

DETAIL_HTML = """
<html><body>
  <h1 class="title">高质量数据集名单公示</h1>
  <div class="content">
    <p>正文段落一</p>
    <img src="/assets/img1.png" alt="名单1">
    <img src="https://cdn.example.com/img2.png" alt="名单2">
  </div>
</body></html>
"""


def _write_rule(tmp_path: Path, *, image_ocr: bool) -> str:
    rule = {
        "name": "detail-image-ocr",
        "subject": "数据要素",
        "source": {
            "type": "html",
            "platform": "hubei_gov",
            "url": "https://www.hubei.gov.cn/list.shtml",
            "client": "desktop",
        },
        "list": {
            "items_path": "css:.news-list li",
            "fields": [
                {"name": "title", "type": "element_text"},
                {"name": "url", "type": "element_href"},
            ],
        },
        "discovery": {
            "enabled": True,
            "list": {
                "items_path": "css:.news-list li",
                "title": {"selector": "a", "type": "text"},
                "detail_url": {"selector": "a", "type": "attribute", "attribute": "href"},
            },
        },
        "archive": {"enabled": True, "mode": "page_markdown"},
        "dedup": {"incremental": False},
    }
    if image_ocr:
        rule["archive"]["image_ocr"] = {
            "enabled": True,
            "images": {"selector": ".content img"},
            "ocr": {"plugin": "tesseract", "languages": ["chi_sim"]},
        }
    path = tmp_path / "rule.yaml"
    path.write_text(yaml.safe_dump(rule, allow_unicode=True), encoding="utf-8")
    return str(path)


class _RecordingStore:
    def __init__(self):
        self.saved = []

    def save_archive_page(self, archive_page):
        self.saved.append(archive_page)
        return {
            "page_id": "page-uuid-1",
            "block_ids": {},
            "asset_ids": {},
            "ocr_result_ids": [],
            "counts": {"pages": 1, "blocks": len(archive_page.get("blocks", [])), "assets": len(archive_page.get("assets", [])), "ocr_results": 0},
        }


@dataclass
class _FakeOcrResult:
    plugin: str = "tesseract"
    status: str = "success"
    text: str = "OCR 文本"
    error: str = ""
    elapsed_seconds: float = 0.0
    structured_data: dict | None = None

    @property
    def empty(self) -> bool:
        return self.text.strip() == ""

    @property
    def manual_review_required(self) -> bool:
        return self.status != "success" or self.empty


class _FakePlugin:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def recognize(self, image_path, config):
        self.calls.append((image_path, config))
        return self.result


def _stub_html(monkeypatch, engine, *, list_html=LIST_HTML, detail_html=DETAIL_HTML):
    def fake_fetch(url, **kwargs):
        if url.endswith("/list.shtml"):
            return list_html
        return detail_html

    monkeypatch.setattr(engine.html_crawler, "fetch", fake_fetch)


def _bind_store(monkeypatch, store):
    monkeypatch.setattr(
        "engine.engine.ArchiveStore.from_rule",
        classmethod(lambda cls, rule: store),
    )


def _bind_save_pkg(monkeypatch, engine, tmp_path):
    monkeypatch.setattr(
        engine.output_mgr, "save_archive_package", lambda page, rule: str(tmp_path / "pkg")
    )


def _bind_download(monkeypatch, tmp_path, *, fail_urls=()):
    downloaded = []

    def fake_download(url, cfg):
        if url in fail_urls:
            raise RuntimeError(f"download failed: {url}")
        path = tmp_path / f"img_{len(downloaded)}.png"
        path.write_bytes(b"\x89PNG")
        downloaded.append(url)
        return str(path)

    monkeypatch.setattr("engine.engine._download_image_for_archive", fake_download)
    return downloaded


def _bind_plugin(monkeypatch, plugin):
    monkeypatch.setattr("engine.engine.get_ocr_plugin", lambda name: plugin)


def test_image_ocr_disabled_skips_image_blocks(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, image_ocr=False)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    result = engine.run(rule_path)

    assert result["archive_page_id"] == "page-uuid-1"
    archived = store.saved[0]
    assert all(b.get("block_type") != "image" for b in archived["blocks"])
    assert all(b.get("block_type") != "ocr" for b in archived["blocks"])
    assert archived["assets"] == []


def test_image_ocr_enabled_emits_image_and_ocr_blocks(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, image_ocr=True)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    downloaded = _bind_download(monkeypatch, tmp_path)
    _bind_plugin(monkeypatch, _FakePlugin(_FakeOcrResult(text="第三批名单 序号 1 数据集 A")))
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    result = engine.run(rule_path)

    assert result["archive_page_id"] == "page-uuid-1"
    archived = store.saved[0]
    image_blocks = [b for b in archived["blocks"] if b.get("block_type") == "image"]
    ocr_blocks = [b for b in archived["blocks"] if b.get("block_type") == "ocr"]
    assert len(image_blocks) == 2
    assert len(ocr_blocks) == 2
    assert all(o.get("parent_block_id") for o in ocr_blocks)
    parent_ids = {b["id"] for b in image_blocks}
    assert all(o["parent_block_id"] in parent_ids for o in ocr_blocks)
    assert len(archived["assets"]) == 2
    asset = archived["assets"][0]
    assert asset["asset_type"] == "image"
    assert asset["storage_uri"]
    assert asset["source_url"].startswith("http")
    assert archived["meta"]["contains_ocr"] is True
    assert len(downloaded) == 2


def test_image_ocr_download_failure_skips_image_but_succeeds(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, image_ocr=True)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    _bind_download(
        monkeypatch,
        tmp_path,
        fail_urls=("https://www.hubei.gov.cn/assets/img1.png",),
    )
    _bind_plugin(monkeypatch, _FakePlugin(_FakeOcrResult(text="ok")))
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    result = engine.run(rule_path)

    assert result["status"] in {"success", "partial_success"}
    archived = store.saved[0]
    image_blocks = [b for b in archived["blocks"] if b.get("block_type") == "image"]
    assert len(image_blocks) == 1
    assert len(archived["assets"]) == 1


def test_image_ocr_empty_text_marks_manual_review(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, image_ocr=True)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_html(monkeypatch, engine)
    _bind_save_pkg(monkeypatch, engine, tmp_path)
    _bind_download(monkeypatch, tmp_path)
    _bind_plugin(monkeypatch, _FakePlugin(_FakeOcrResult(text="")))
    store = _RecordingStore()
    _bind_store(monkeypatch, store)

    engine.run(rule_path)

    archived = store.saved[0]
    ocr_blocks = [b for b in archived["blocks"] if b.get("block_type") == "ocr"]
    assert len(ocr_blocks) == 2
    assert all(b.get("ocr_text") == "" for b in ocr_blocks)
    assert all(b.get("manual_review_required") is True for b in ocr_blocks)
