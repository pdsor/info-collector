"""Source 信任分自动更新测试。"""
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../engine")))


def _make_db(tmp_path: str) -> str:
    """创建包含 governance_records + sources 表的临时数据库。"""
    db_path = os.path.join(tmp_path, "dashboard.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            domain TEXT NOT NULL DEFAULT '',
            type TEXT NOT NULL DEFAULT 'website',
            category TEXT NOT NULL DEFAULT '',
            trust_score REAL NOT NULL DEFAULT 0.5,
            update_frequency INTEGER NOT NULL DEFAULT 3600,
            anti_crawl_level TEXT NOT NULL DEFAULT 'low',
            parser_strategy TEXT NOT NULL DEFAULT '',
            auth_required INTEGER NOT NULL DEFAULT 0,
            language TEXT NOT NULL DEFAULT 'zh-CN',
            tags TEXT NOT NULL DEFAULT '[]',
            enabled INTEGER NOT NULL DEFAULT 1,
            lifecycle_status TEXT NOT NULL DEFAULT 'ACTIVE',
            rule_path TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS governance_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL DEFAULT '',
            source_file TEXT NOT NULL DEFAULT '',
            item_count INTEGER NOT NULL DEFAULT 0,
            duplicate_count INTEGER NOT NULL DEFAULT 0,
            injection_risk_count INTEGER NOT NULL DEFAULT 0,
            field_completeness REAL NOT NULL DEFAULT 1.0,
            quality_score REAL NOT NULL DEFAULT 1.0,
            status TEXT NOT NULL DEFAULT 'SUCCESS',
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        );
    """)
    conn.commit()
    conn.close()
    return db_path


def test_quality_trust_score_returns_none_when_no_history():
    from APP.dashboard.apis.source_api import _quality_trust_score
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        assert _quality_trust_score("unknown_platform", conn) is None
        conn.close()


def test_quality_trust_score_averages_recent_runs():
    from APP.dashboard.apis.source_api import _quality_trust_score
    with tempfile.TemporaryDirectory() as tmp:
        db = _make_db(tmp)
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        conn.executemany(
            "INSERT INTO governance_records (platform, quality_score) VALUES (?, ?)",
            [("hubei_gov", 0.9), ("hubei_gov", 0.8), ("hubei_gov", 1.0)],
        )
        conn.commit()
        score = _quality_trust_score("hubei_gov", conn)
        conn.close()
        assert score == round((0.9 + 0.8 + 1.0) / 3, 4)


def test_sync_sources_blends_historical_quality(monkeypatch, tmp_path):
    """有历史质量数据时，信任分应混合基准分与质量分。"""
    import yaml
    from APP.dashboard.apis import source_api as sa

    # 写一条规则文件
    rules_dir = tmp_path / "rules" / "数据要素"
    rules_dir.mkdir(parents=True)
    rule_file = rules_dir / "hubei_gov_test.yaml"
    rule_file.write_text(yaml.dump({
        "name": "测试规则", "subject": "数据要素",
        "source": {"type": "html", "platform": "hubei_gov", "url": "https://hubei.gov.cn/list"},
        "list": {"items_path": "css:li"},
        "extract": {"title": {"selector": "a"}},
    }, allow_unicode=True), encoding="utf-8")

    db_path = str(tmp_path / "dashboard.db")
    db = _make_db(str(tmp_path))
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    # 插入 3 条质量记录
    conn.executemany(
        "INSERT INTO governance_records (platform, quality_score) VALUES (?, ?)",
        [("hubei_gov_test", 0.7), ("hubei_gov_test", 0.8), ("hubei_gov_test", 0.9)],
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(sa, "RULES_DIR", str(rules_dir))
    monkeypatch.setattr(sa, "DB_PATH", db_path)

    records = sa.sync_sources_from_rules()
    assert len(records) == 1
    # 历史质量分 avg = 0.8；trust = 0.6*0.8 + 0.4*0.85 = 0.82
    assert abs(records[0]["trust_score"] - (0.6 * 0.8 + 0.4 * 0.85)) < 0.001


def test_sync_sources_uses_default_when_no_history(monkeypatch, tmp_path):
    """无历史数据时信任分使用默认值 0.85。"""
    import yaml
    from APP.dashboard.apis import source_api as sa

    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    (rules_dir / "new_source.yaml").write_text(yaml.dump({
        "name": "新来源", "source": {"type": "html", "url": "https://new.example.com"},
    }, allow_unicode=True), encoding="utf-8")

    db_path = str(tmp_path / "dashboard.db")
    _make_db(str(tmp_path))

    monkeypatch.setattr(sa, "RULES_DIR", str(rules_dir))
    monkeypatch.setattr(sa, "DB_PATH", db_path)

    records = sa.sync_sources_from_rules()
    assert len(records) == 1
    assert records[0]["trust_score"] == 0.85
