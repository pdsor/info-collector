"""项目级配置读取测试。"""

from pathlib import Path

import pytest


def test_get_pg_dsn_reads_project_config(tmp_path, monkeypatch):
    from engine.config import get_pg_dsn

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        'database:\n  pg_dsn: "postgresql://project/test"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr("engine.config.PROJECT_CONFIG_PATH", config_path)

    assert get_pg_dsn() == "postgresql://project/test"


def test_get_pg_dsn_rejects_missing_project_config(tmp_path, monkeypatch):
    from engine.config import get_pg_dsn

    monkeypatch.setattr("engine.config.PROJECT_CONFIG_PATH", tmp_path / "missing.yaml")

    with pytest.raises(ValueError, match="APP/engine/config.yaml"):
        get_pg_dsn()


def test_get_pg_dsn_does_not_read_environment(tmp_path, monkeypatch):
    from engine.config import get_pg_dsn

    monkeypatch.setenv("INFO_COLLECTOR_PG_DSN", "postgresql://env/ignored")
    monkeypatch.setenv("ARCHIVE_PG_DSN", "postgresql://archive-env/ignored")
    monkeypatch.setattr("engine.config.PROJECT_CONFIG_PATH", tmp_path / "missing.yaml")

    with pytest.raises(ValueError, match="APP/engine/config.yaml"):
        get_pg_dsn()
