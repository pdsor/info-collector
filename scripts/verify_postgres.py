#!/usr/bin/env python3
"""验证 PostgreSQL 连接，并创建项目数据库。"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from psycopg import sql


ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"


def load_env(path: Path) -> None:
    """加载简单的 .env 键值配置。"""
    if not path.exists():
        raise FileNotFoundError(f"未找到环境配置文件：{path}")

    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def conninfo(database: str) -> str:
    return (
        f"host={os.environ['PGHOST']} "
        f"port={os.environ.get('PGPORT', '5432')} "
        f"user={os.environ['PGUSER']} "
        f"password={os.environ['PGPASSWORD']} "
        f"dbname={database}"
    )


def database_exists(conn: psycopg.Connection, database: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
        return cur.fetchone() is not None


def create_database_if_missing(conn: psycopg.Connection, database: str) -> bool:
    if database_exists(conn, database):
        return False

    with conn.cursor() as cur:
        cur.execute(
            sql.SQL("CREATE DATABASE {} ENCODING 'UTF8'").format(
                sql.Identifier(database)
            )
        )
    return True


def verify_project_database(database: str) -> tuple[str, str, str, int]:
    with psycopg.connect(conninfo(database)) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    current_database(),
                    current_user,
                    COALESCE(inet_server_addr()::text, 'local'),
                    inet_server_port()
                """
            )
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("PostgreSQL 未返回连接验证结果")
            return row


def main() -> None:
    load_env(ENV_PATH)

    target_database = os.environ["PGDATABASE"]
    admin_database = os.environ.get("PGADMIN_DATABASE", "postgres")

    with psycopg.connect(conninfo(admin_database), autocommit=True) as conn:
        created = create_database_if_missing(conn, target_database)

    current_database, current_user, server_addr, server_port = verify_project_database(
        target_database
    )
    action = "已创建" if created else "已存在"
    print(f"数据库 {target_database} {action}")
    print(
        "连接验证通过："
        f"database={current_database}, user={current_user}, "
        f"server={server_addr}:{server_port}"
    )


if __name__ == "__main__":
    main()
