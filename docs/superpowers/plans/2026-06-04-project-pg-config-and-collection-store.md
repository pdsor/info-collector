# 项目级 PostgreSQL 配置与采集结果入库实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 PostgreSQL 连接串从规则配置迁移到项目级配置，并让普通采集结果与页面归档结果都写入 PostgreSQL。

**Architecture:** 新增项目配置读取模块，只读取 `APP/engine/config.yaml`，不读取环境变量。页面归档继续使用现有 `ArchiveStore` 和归档表；普通采集结果新增 `CollectionStore` 和 `collection_runs`、`collection_items`、`collection_governance_records` 表。`InfoCollectorEngine.run()` 在治理完成后先写普通采集结果，再按现有链路写页面归档，任一 PostgreSQL 写入失败都让任务失败。

**Tech Stack:** Python、pytest、PyYAML、SQLAlchemy Core、PostgreSQL、现有 `InfoCollectorEngine`、`GovernancePipeline`、`ArchiveStore`。

---

## 文件结构

- 新建：`APP/engine/config.yaml`
  - 项目级配置文件，保存 PostgreSQL DSN。
- 新建：`APP/engine/engine/config.py`
  - 负责读取 `APP/engine/config.yaml`，提供 `load_project_config()` 和 `get_pg_dsn()`。
- 新建：`APP/engine/engine/collection_store.py`
  - 负责普通采集结果、运行记录和治理摘要写入 PostgreSQL。
- 新建：`migrations/20260604_collection_postgres.sql`
  - 定义普通采集数据入库表。
- 修改：`APP/engine/engine/archive_store.py`
  - `ArchiveStore.from_rule()` 改为读取项目级 DSN，不再读取环境变量或规则内 DSN。
- 修改：`APP/engine/engine/engine.py`
  - 在治理完成后调用 `CollectionStore.save_run_items()`。
- 修改：`APP/engine/tests/test_archive_store.py`
  - 更新归档存储配置来源测试。
- 新建：`APP/engine/tests/test_project_config.py`
  - 覆盖项目配置读取。
- 新建：`APP/engine/tests/test_collection_store.py`
  - 覆盖普通采集结果入库 payload 与事务写入。
- 修改或新建：`APP/engine/tests/test_engine_collection_pg.py`
  - 覆盖 `InfoCollectorEngine.run()` 会写普通采集数据，失败时任务失败。
- 修改：`README.md`
  - 更新 PostgreSQL 项目级配置说明。

## 项目配置格式

`APP/engine/config.yaml` 内容：

```yaml
database:
  pg_dsn: "postgresql://<user>:<password>@<host>:5432/info_collector"
```

规则文件中不再配置：

```yaml
archive_store:
  dsn: "postgresql://..."
```

## 数据库表设计

新增迁移 `migrations/20260604_collection_postgres.sql`：

```sql
create extension if not exists pgcrypto;

create table if not exists collection_runs (
    id uuid primary key default gen_random_uuid(),
    rule_name text not null,
    rule_path text not null,
    subject text not null,
    platform text not null,
    status text not null,
    total_collected integer not null default 0,
    saved_count integer not null default 0,
    dedup_filtered integer not null default 0,
    output_path text,
    started_at timestamp with time zone not null,
    finished_at timestamp with time zone not null,
    duration_seconds numeric,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamp with time zone not null default now()
);

create table if not exists collection_items (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references collection_runs(id) on delete cascade,
    rule_name text not null,
    rule_path text not null,
    subject text not null,
    platform text not null,
    raw_id text,
    url text,
    title text,
    content_hash text,
    field_completeness numeric,
    injection_risk boolean not null default false,
    data jsonb not null default '{}'::jsonb,
    governance jsonb not null default '{}'::jsonb,
    collected_at timestamp with time zone not null,
    created_at timestamp with time zone not null default now()
);

create table if not exists collection_governance_records (
    id uuid primary key default gen_random_uuid(),
    run_id uuid not null references collection_runs(id) on delete cascade,
    subject text not null,
    platform text not null,
    item_count integer not null default 0,
    duplicate_count integer not null default 0,
    injection_risk_count integer not null default 0,
    field_completeness numeric not null default 1,
    quality_score numeric not null default 1,
    status text not null,
    summary jsonb not null default '{}'::jsonb,
    created_at timestamp with time zone not null default now()
);

create index if not exists collection_items_run_idx on collection_items (run_id);
create index if not exists collection_items_subject_platform_idx on collection_items (subject, platform);
create index if not exists collection_items_url_idx on collection_items (url);
create index if not exists collection_items_content_hash_idx on collection_items (content_hash);
create index if not exists collection_items_data_gin_idx on collection_items using gin (data);
create index if not exists collection_governance_subject_platform_idx on collection_governance_records (subject, platform);
```

## Task 1: 项目配置读取

**Files:**
- Create: `APP/engine/tests/test_project_config.py`
- Create: `APP/engine/engine/config.py`
- Create: `APP/engine/config.yaml`

- [ ] **Step 1: 写失败测试**

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_project_config.py -q
```

Expected: FAIL，原因是 `engine.config` 不存在。

- [ ] **Step 3: 实现配置读取**

`APP/engine/engine/config.py`：

```python
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
```

`APP/engine/config.yaml`：

```yaml
database:
  pg_dsn: "postgresql://<user>:<password>@<host>:5432/info_collector"
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_project_config.py -q
```

Expected: PASS。

## Task 2: 普通采集数据 PostgreSQL 写入层

**Files:**
- Create: `migrations/20260604_collection_postgres.sql`
- Create: `APP/engine/tests/test_collection_store.py`
- Create: `APP/engine/engine/collection_store.py`

- [ ] **Step 1: 新增迁移文件**

按“数据库表设计”章节创建 `migrations/20260604_collection_postgres.sql`。

- [ ] **Step 2: 写失败测试**

`APP/engine/tests/test_collection_store.py`：

```python
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
    assert result["governance_record_id"] == "id-3"
    assert conn.tx.committed is True
    assert conn.closed is True
    assert len(conn.calls) == 3
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_collection_store.py -q
```

Expected: FAIL，原因是 `engine.collection_store` 不存在。

- [ ] **Step 4: 实现 `CollectionStore`**

`APP/engine/engine/collection_store.py` 需要定义：
- `COLLECTION_RUNS`
- `COLLECTION_ITEMS`
- `COLLECTION_GOVERNANCE_RECORDS`
- `CollectionStore.__init__(dsn, connection_factory=None)`
- `CollectionStore.from_project_config()`
- `CollectionStore.save_run_items(...)`

核心行为：
- 使用 `get_pg_dsn()` 获取 DSN。
- 一个事务内写入 run、items、governance。
- item 的 `_governance` 同时拆出常用列，并完整保存在 `governance` JSONB。
- 写入失败时 rollback 并抛出异常。

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_collection_store.py -q
```

Expected: PASS。

## Task 3: 归档存储改为项目级 DSN

**Files:**
- Modify: `APP/engine/tests/test_archive_store.py`
- Modify: `APP/engine/engine/archive_store.py`

- [ ] **Step 1: 写失败测试**

在 `APP/engine/tests/test_archive_store.py` 中替换旧环境变量/规则 DSN 测试，新增：

```python
def test_archive_store_from_rule_reads_project_config(monkeypatch):
    """归档存储只从项目配置读取 PostgreSQL DSN。"""
    from engine.archive_store import ArchiveStore

    monkeypatch.setattr("engine.archive_store.get_pg_dsn", lambda: "postgresql://project/test")

    store = ArchiveStore.from_rule({"archive_store": {"dsn": "postgresql://rule/ignored"}})

    assert store.dsn == "postgresql://project/test"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_store.py::test_archive_store_from_rule_reads_project_config -q
```

Expected: FAIL，当前实现仍可能读取规则 DSN 或环境变量。

- [ ] **Step 3: 修改 `ArchiveStore.from_rule()`**

在 `APP/engine/engine/archive_store.py` 中导入：

```python
from .config import get_pg_dsn
```

修改：

```python
@classmethod
def from_rule(cls, rule):
    """从项目级配置读取归档主库连接串。"""
    return cls(dsn=get_pg_dsn())
```

`from_env()` 可删除或保留但不在主链路使用。若保留，需改名或注释为测试兼容方法，避免文档继续推荐环境变量。

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_store.py::test_archive_store_from_rule_reads_project_config -q
```

Expected: PASS。

## Task 4: 引擎运行时写普通采集数据

**Files:**
- Create: `APP/engine/tests/test_engine_collection_pg.py`
- Modify: `APP/engine/engine/engine.py`

- [ ] **Step 1: 写失败测试**

`APP/engine/tests/test_engine_collection_pg.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_engine_collection_pg.py -q
```

Expected: FAIL，原因是 `CollectionStore` 未接入 `engine.py`。

- [ ] **Step 3: 修改 `engine.py`**

导入：

```python
from .collection_store import CollectionStore
```

在 `run()` 中：
- `start` 已有。
- 治理完成后，保存 JSON 后，调用：

```python
finished_for_store = datetime.now(timezone.utc)
collection_write = CollectionStore.from_project_config().save_run_items(
    rule=rule,
    rule_path=rule_path,
    items=items,
    governance_summary=governance_result.summary,
    total_collected=total_collected,
    dedup_filtered=dedup_filtered,
    output_path=output_path,
    status="partial_success" if governance_result.status == "PARTIAL_SUCCESS" else "success",
    started_at=datetime.fromtimestamp(start, tz=timezone.utc),
    finished_at=finished_for_store,
    duration_seconds=time.time() - start,
)
```

在返回结果中追加：

```python
"collection_run_id": collection_write["run_id"],
"collection_item_count": len(collection_write["item_ids"]),
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_engine_collection_pg.py -q
```

Expected: PASS。

## Task 5: 文档更新与回归验证

**Files:**
- Modify: `README.md`
- Optionally Modify: `DOCS/PageArchiveCollectionRedesign.md`

- [ ] **Step 1: 更新 README PostgreSQL 配置说明**

将“不内置 PostgreSQL”改为说明：
- 当前系统要求 `APP/engine/config.yaml` 提供 PostgreSQL DSN。
- 普通采集数据写入 `collection_*` 表。
- 页面归档数据写入 `archive_*`、`ocr_results`、`structured_records` 表。
- JSON 文件仅保留为调试与兼容输出。

- [ ] **Step 2: 运行目标测试**

Run:

```bash
cd APP/engine && .venv/bin/python -m pytest \
  tests/test_project_config.py \
  tests/test_collection_store.py \
  tests/test_archive_store.py::test_archive_store_from_rule_reads_project_config \
  tests/test_engine_collection_pg.py \
  -q
```

Expected: PASS。

- [ ] **Step 3: 运行归档链路回归**

Run:

```bash
cd APP/engine && .venv/bin/python -m pytest \
  tests/test_archive_batch_details.py \
  tests/test_archive_pagination.py \
  tests/test_archive_detail_images.py \
  -q
```

Expected: PASS。

## 自检

- 需求覆盖：项目级 DSN、普通采集结果入库、归档入库配置迁移、入库失败即任务失败均已覆盖。
- 占位扫描：未发现空泛占位或未定义实现步骤。
- 范围控制：本计划不做 Dashboard 查询 PostgreSQL 改造；Dashboard 当前仍可继续读文件归档包。后续如需控制台直接查 PostgreSQL，应单独计划。
