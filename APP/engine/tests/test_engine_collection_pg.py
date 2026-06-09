"""采集引擎普通结果入库测试。"""

from pathlib import Path

import yaml


def _write_rule(tmp_path: Path) -> str:
    rule = {
        "name": "普通采集入库",
        "subject": "数据要素",
        "source": {
            "type": "html",
            "platform": "example",
            "url": "https://example.com/list.html",
            "client": "desktop",
        },
        "list": {
            "items_path": "css:li",
            "fields": [
                {"name": "title", "type": "element_text"},
                {"name": "url", "type": "element_href"},
            ],
        },
        "dedup": {"incremental": False},
        "output": {"filename_template": "example_{date}.json"},
    }
    path = tmp_path / "rule.yaml"
    path.write_text(yaml.safe_dump(rule, allow_unicode=True), encoding="utf-8")
    return str(path)


class _RecordingCollectionStore:
    def __init__(self):
        self.calls = []

    def save_run_items(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "run_id": "run-1",
            "item_ids": ["item-1"],
            "governance_record_id": "gov-1",
        }


def test_engine_run_writes_governed_items_to_collection_store(tmp_path, monkeypatch):
    from engine.engine import InfoCollectorEngine

    rule_path = _write_rule(tmp_path)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    monkeypatch.setattr(
        engine.html_crawler,
        "fetch",
        lambda *args, **kwargs: '<ul><li><a href="https://example.com/a">文章一</a></li></ul>',
    )
    store = _RecordingCollectionStore()
    monkeypatch.setattr(
        "engine.engine.CollectionStore.from_project_config",
        classmethod(lambda cls: store),
    )

    result = engine.run(rule_path)

    assert result["status"] == "success"
    assert result["collection_run_id"] == "run-1"
    assert store.calls[0]["rule_path"] == rule_path
    assert store.calls[0]["items"][0]["title"] == "文章一"
    assert store.calls[0]["governance_summary"]["item_count"] == 1


def test_engine_run_fails_when_collection_store_write_fails(tmp_path, monkeypatch):
    from engine.engine import InfoCollectorEngine

    rule_path = _write_rule(tmp_path)
    engine = InfoCollectorEngine(
        dedup_db_path=str(tmp_path / "dedup.db"),
        state_dir=str(tmp_path / "state"),
    )
    monkeypatch.setattr(
        engine.html_crawler,
        "fetch",
        lambda *args, **kwargs: '<ul><li><a href="https://example.com/a">文章一</a></li></ul>',
    )

    class _FailingStore:
        def save_run_items(self, **kwargs):
            raise RuntimeError("PG 写入失败")

    monkeypatch.setattr(
        "engine.engine.CollectionStore.from_project_config",
        classmethod(lambda cls: _FailingStore()),
    )

    result = engine.run(rule_path)

    assert result["status"] == "failed"
    assert "PG 写入失败" in result["error"]
