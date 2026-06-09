"""普通采集结果 PostgreSQL 写入测试。"""

from datetime import datetime, timezone


class _Tx:
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class _Conn:
    def __init__(self):
        self.tx = _Tx()
        self.calls = []
        self.closed = False
        self.next_id = 0

    def begin(self):
        return self.tx

    def execute(self, statement):
        self.calls.append(statement)
        self.next_id += 1
        current = self.next_id

        class _Result:
            def scalar_one(self_inner):
                return f"id-{current}"

        return _Result()

    def close(self):
        self.closed = True


def test_save_run_items_writes_run_items_and_governance():
    from engine.collection_store import CollectionStore

    conn = _Conn()
    store = CollectionStore(dsn="postgresql://test/test", connection_factory=lambda: conn)
    rule = {
        "name": "测试规则",
        "subject": "数据要素",
        "source": {"platform": "nda_gov"},
    }
    items = [
        {
            "title": "文章一",
            "url": "https://example.com/a",
            "raw_id": "a",
            "_governance": {
                "content_hash": "hash-a",
                "field_completeness": 1.0,
                "injection_risk": False,
            },
        }
    ]
    summary = {
        "item_count": 1,
        "duplicate_count": 0,
        "injection_risk_count": 0,
        "field_completeness": 1.0,
        "quality_score": 1.0,
        "status": "SUCCESS",
    }

    result = store.save_run_items(
        rule=rule,
        rule_path="rules/a.yaml",
        items=items,
        governance_summary=summary,
        total_collected=1,
        dedup_filtered=0,
        output_path="/tmp/a.json",
        status="success",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        duration_seconds=0.1,
    )

    assert result["run_id"] == "id-1"
    assert result["item_ids"] == ["id-2"]
    assert result["run_item_ids"] == ["id-3"]
    assert result["governance_record_id"] == "id-4"
    assert conn.tx.committed is True
    assert conn.closed is True
    assert len(conn.calls) == 4
