"""项目级配置读取。"""

from pathlib import Path

import yaml


ENGINE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_CONFIG_PATH = ENGINE_ROOT / "config.yaml"


def load_project_config() -> dict:
    """读取 APP/engine/config.yaml 项目配置。"""
    if not PROJECT_CONFIG_PATH.exists():
        raise ValueError("缺少项目配置文件 APP/engine/config.yaml")
    with PROJECT_CONFIG_PATH.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError("APP/engine/config.yaml 必须是 YAML 对象")
    return data


def get_pg_dsn() -> str:
    """读取项目级 PostgreSQL DSN；不读取环境变量。"""
    cfg = load_project_config()
    dsn = ((cfg.get("database") or {}).get("pg_dsn") or "").strip()
    if not dsn:
        raise ValueError("APP/engine/config.yaml 缺少 database.pg_dsn")
    return dsn
