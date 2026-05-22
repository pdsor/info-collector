"""归档接入采集执行链路测试。"""

from pathlib import Path

import yaml

from engine.engine import InfoCollectorEngine


def _write_rule(tmp_path: Path, archive_block):
    rule = {
        "name": "归档接入回归",
        "subject": "数据要素",
        "source": {
            "type": "html",
            "platform": "hubei_gov",
            "url": "https://www.hubei.gov.cn/a.shtml",
            "client": "desktop",
        },
        "list": {
            "items_path": "css:.news-list li",
            "fields": [
                {"name": "title", "type": "element_text"},
                {"name": "url", "type": "element_href"},
            ],
        },
        "dedup": {"incremental": False},
    }
    if archive_block is not None:
        rule["archive"] = archive_block

    path = tmp_path / "rule.yaml"
    path.write_text(yaml.safe_dump(rule, allow_unicode=True), encoding="utf-8")
    return str(path)


def _stub_pipeline(monkeypatch, engine, items):
    monkeypatch.setattr(engine, "crawl", lambda rule: list(items))
    monkeypatch.setattr(engine, "save_output", lambda *args, **kwargs: "")


def test_archive_not_enabled_does_not_trigger_archive(tmp_path, monkeypatch):
    rule_path = _write_rule(tmp_path, archive_block=None)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_pipeline(monkeypatch, engine, items=[{"title": "x", "url": "https://x"}])

    call_count = {"n": 0}

    def _fail(*args, **kwargs):
        call_count["n"] += 1
        raise AssertionError("不应调用 save_archive_package")

    monkeypatch.setattr(engine.output_mgr, "save_archive_package", _fail)

    result = engine.run(rule_path)

    assert result["status"] in {"success", "partial_success"}
    assert "archive_page_id" not in result
    assert "archive_package_path" not in result
    assert call_count["n"] == 0


def test_archive_enabled_writes_package_and_main_store(tmp_path, monkeypatch):
    rule_path = _write_rule(
        tmp_path,
        archive_block={
            "enabled": True,
            "mode": "page_markdown",
            "markdown": {"enabled": True},
        },
    )
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_pipeline(
        monkeypatch,
        engine,
        items=[{"title": "归档样例", "url": "https://www.hubei.gov.cn/a.shtml"}],
    )

    package_path = str(tmp_path / "fake-package")
    monkeypatch.setattr(
        engine.output_mgr,
        "save_archive_package",
        lambda archive_page, rule: package_path,
    )

    class FakeStore:
        def __init__(self):
            self.saved = []

        def save_archive_page(self, archive_page):
            self.saved.append(archive_page)
            return {
                "page_id": "page-uuid-1",
                "block_ids": {},
                "asset_ids": {},
                "ocr_result_ids": [],
                "counts": {"pages": 1, "blocks": 0, "assets": 0, "ocr_results": 0},
            }

    fake_store = FakeStore()
    monkeypatch.setattr(
        "engine.engine.ArchiveStore.from_rule",
        classmethod(lambda cls, rule: fake_store),
    )

    result = engine.run(rule_path)

    assert result["status"] in {"success", "partial_success"}
    assert result["archive_page_id"] == "page-uuid-1"
    assert result["archive_package_path"] == package_path
    assert len(fake_store.saved) == 1
    assert "meta" in fake_store.saved[0]


def test_archive_store_failure_marks_task_failed(tmp_path, monkeypatch):
    rule_path = _write_rule(
        tmp_path,
        archive_block={"enabled": True, "mode": "page_markdown"},
    )
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    _stub_pipeline(
        monkeypatch,
        engine,
        items=[{"title": "归档样例", "url": "https://www.hubei.gov.cn/a.shtml"}],
    )
    monkeypatch.setattr(
        engine.output_mgr,
        "save_archive_package",
        lambda archive_page, rule: str(tmp_path / "fake-package"),
    )

    class BrokenStore:
        def save_archive_page(self, archive_page):
            raise RuntimeError("模拟主库写入失败")

    monkeypatch.setattr(
        "engine.engine.ArchiveStore.from_rule",
        classmethod(lambda cls, rule: BrokenStore()),
    )

    result = engine.run(rule_path)

    assert result["status"] == "failed"
    assert "模拟主库写入失败" in result.get("error", "")
