# 页面归档 PostgreSQL 写入执行层实现计划

> **面向代理工作者：** 执行本计划时必须使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`。步骤使用复选框（`- [ ]`）跟踪进度。

**目标：** 基于现有 `ArchiveStore` payload 契约，新增一次性写入页面、块、资产和 OCR 结果的 PostgreSQL 执行层。

**架构：** 本切片只处理存储层，不接入采集执行链路，也不做列表页发现。`ArchiveStore` 继续保留内存契约测试，同时增加可注入连接对象的 SQLAlchemy 写入路径，`save_archive_page()` 在一个事务内按 page、blocks、assets、ocr_results 顺序写入，并返回可审计的保存摘要。

**技术栈：** Python、pytest、SQLAlchemy Core、PostgreSQL、现有 `engine.archive_store.ArchiveStore`、环境变量 `ARCHIVE_PG_DSN`。

---

## 文件结构

- 修改：`APP/engine/engine/archive_store.py`
  - 保留现有 `save_page()`、`save_block()`、`save_asset()` 内存方法。
  - 新增 SQLAlchemy 表定义或轻量表引用。
  - 新增 `save_archive_page()`，一次事务写入 `archive_pages`、`archive_blocks`、`archive_assets`、`ocr_results`。
  - 新增连接工厂注入参数，测试可传伪连接，不依赖真实 PostgreSQL。
- 修改：`APP/engine/tests/test_archive_store.py`
  - 增加伪连接和伪事务测试。
  - 验证写入顺序、表名、payload、ID 映射、OCR 关联、事务提交与回滚。
- 不修改：`APP/engine/engine/engine.py`
  - 本切片不接入采集执行链路。
- 不修改：`migrations/20260521_archive_postgres.sql`
  - 本切片使用既有表结构，不扩表。

## 任务 1：为一次性写入定义失败测试

**文件：**
- 修改：`APP/engine/tests/test_archive_store.py`

- [ ] **步骤 1：写入伪连接测试**

在 `APP/engine/tests/test_archive_store.py` 末尾增加以下测试辅助类和测试：

```python
class FakeInsertResult:
    """模拟 SQLAlchemy insert returning 的返回值。"""

    def __init__(self, inserted_id):
        self.inserted_id = inserted_id

    def scalar_one(self):
        return self.inserted_id


class FakeTransaction:
    """记录事务提交和回滚状态。"""

    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeConnection:
    """记录写入调用，避免依赖真实 PostgreSQL。"""

    def __init__(self, fail_on_call=None):
        self.calls = []
        self.transaction = FakeTransaction()
        self.fail_on_call = fail_on_call

    def begin(self):
        return self.transaction

    def execute(self, statement):
        call_number = len(self.calls) + 1
        if self.fail_on_call == call_number:
            raise RuntimeError("模拟写入失败")
        table_name = statement.table.name
        values = statement.compile().params
        inserted_id = values.get("id") or f"{table_name}-{call_number}"
        self.calls.append({"table": table_name, "values": values})
        return FakeInsertResult(inserted_id)


def test_save_archive_page_writes_page_blocks_assets_and_ocr_in_one_transaction():
    """一次性保存应按页面、块、资产、OCR 顺序写入并提交事务。"""
    from engine.archive_store import ArchiveStore

    fake_connection = FakeConnection()
    store = ArchiveStore(
        dsn="postgresql://test/test",
        connection_factory=lambda: fake_connection,
    )
    archive_page = {
        "meta": {
            "source_url": "https://www.hubei.gov.cn/a.shtml",
            "entry_url": "https://www.hubei.gov.cn/list.shtml",
            "final_url": "https://www.hubei.gov.cn/a.shtml",
            "domain": "www.hubei.gov.cn",
            "platform": "hubei_gov",
            "subject": "数据要素",
            "title": "图片 OCR 公示",
            "source_name": "湖北省数据局",
            "publish_time": "2026-01-05T09:00:00+08:00",
            "fetched_at": "2026-05-21T15:30:00+08:00",
            "content_hash": "0" * 64,
            "contains_ocr": True,
            "contains_table": False,
            "requires_structuring": True,
        },
        "content": {
            "html": "<html><body><img src='/img.png'></body></html>",
            "markdown": "![名单图片](https://www.hubei.gov.cn/img.png)",
        },
        "blocks": [
            {
                "id": "img-001",
                "block_order": 1,
                "block_type": "image",
                "source_url": "https://www.hubei.gov.cn/img.png",
                "storage_uri": "/tmp/scraper_imgs/x.png",
            },
            {
                "id": "ocr-001",
                "block_order": 2,
                "block_type": "ocr",
                "parent_block_id": "img-001",
                "asset_id": "asset-img-001",
                "ocr_text": "高质量数据集名单",
            },
        ],
        "assets": [
            {
                "id": "asset-img-001",
                "block_id": "img-001",
                "asset_type": "image",
                "source_url": "https://www.hubei.gov.cn/img.png",
                "storage_uri": "/tmp/scraper_imgs/x.png",
                "file_name": "x.png",
                "extension": ".png",
                "mime_type": "image/png",
                "size_bytes": 12345,
                "content_hash": "abc",
                "downloaded": True,
                "metadata": {},
            }
        ],
        "ocr_results": [
            {
                "asset_id": "asset-img-001",
                "block_id": "ocr-001",
                "ocr_text": "高质量数据集名单",
                "structured_data": {"rows": []},
            }
        ],
    }

    result = store.save_archive_page(archive_page)

    assert result == {
        "page_id": "archive_pages-1",
        "block_ids": {"img-001": "archive_blocks-2", "ocr-001": "archive_blocks-3"},
        "asset_ids": {"asset-img-001": "archive_assets-4"},
        "ocr_result_ids": ["ocr_results-5"],
        "counts": {"pages": 1, "blocks": 2, "assets": 1, "ocr_results": 1},
    }
    assert [call["table"] for call in fake_connection.calls] == [
        "archive_pages",
        "archive_blocks",
        "archive_blocks",
        "archive_assets",
        "ocr_results",
    ]
    assert fake_connection.calls[1]["values"]["page_id"] == "archive_pages-1"
    assert fake_connection.calls[2]["values"]["parent_block_id"] == "archive_blocks-2"
    assert fake_connection.calls[3]["values"]["block_id"] == "archive_blocks-2"
    assert fake_connection.calls[4]["values"]["asset_id"] == "archive_assets-4"
    assert fake_connection.calls[4]["values"]["block_id"] == "archive_blocks-3"
    assert fake_connection.transaction.committed is True
    assert fake_connection.transaction.rolled_back is False


def test_save_archive_page_rolls_back_when_insert_fails():
    """任一写入失败时应回滚事务并抛出原始异常。"""
    from engine.archive_store import ArchiveStore

    fake_connection = FakeConnection(fail_on_call=3)
    store = ArchiveStore(
        dsn="postgresql://test/test",
        connection_factory=lambda: fake_connection,
    )

    archive_page = {
        "meta": {
            "source_url": "https://www.hubei.gov.cn/a.shtml",
            "domain": "www.hubei.gov.cn",
            "title": "失败样例",
            "fetched_at": "2026-05-21T15:30:00+08:00",
            "content_hash": "1" * 64,
        },
        "content": {"html": "<html></html>", "markdown": "# 失败样例"},
        "blocks": [
            {"id": "b1", "block_order": 1, "block_type": "heading", "text": "标题"},
            {"id": "b2", "block_order": 2, "block_type": "paragraph", "text": "正文"},
        ],
        "assets": [],
        "ocr_results": [],
    }

    with pytest.raises(RuntimeError, match="模拟写入失败"):
        store.save_archive_page(archive_page)

    assert fake_connection.transaction.committed is False
    assert fake_connection.transaction.rolled_back is True
```

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_store.py::test_save_archive_page_writes_page_blocks_assets_and_ocr_in_one_transaction tests/test_archive_store.py::test_save_archive_page_rolls_back_when_insert_fails -q
```

预期：失败，错误包含 `AttributeError: 'ArchiveStore' object has no attribute 'save_archive_page'` 或 `TypeError: __init__() got an unexpected keyword argument 'connection_factory'`。

## 任务 2：实现 SQLAlchemy 表引用和连接工厂

**文件：**
- 修改：`APP/engine/engine/archive_store.py`

- [ ] **步骤 1：增加 SQLAlchemy 导入和表定义**

在 `APP/engine/engine/archive_store.py` 顶部导入 SQLAlchemy，并在类外定义表元数据：

```python
from sqlalchemy import (
    Boolean,
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    create_engine,
    insert,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID


ARCHIVE_METADATA = MetaData()

ARCHIVE_PAGES = Table(
    "archive_pages",
    ARCHIVE_METADATA,
    Column("id", UUID(as_uuid=False)),
    Column("source_url", Text),
    Column("entry_url", Text),
    Column("final_url", Text),
    Column("domain", Text),
    Column("platform", Text),
    Column("subject", Text),
    Column("title", Text),
    Column("source_name", Text),
    Column("publish_time", DateTime(timezone=True)),
    Column("html", Text),
    Column("markdown", Text),
    Column("metadata", JSONB),
    Column("content_hash", Text),
    Column("contains_ocr", Boolean),
    Column("contains_table", Boolean),
    Column("requires_structuring", Boolean),
    Column("fetched_at", DateTime(timezone=True)),
)

ARCHIVE_BLOCKS = Table(
    "archive_blocks",
    ARCHIVE_METADATA,
    Column("id", UUID(as_uuid=False)),
    Column("page_id", UUID(as_uuid=False)),
    Column("block_order", Integer),
    Column("block_type", Text),
    Column("parent_block_id", UUID(as_uuid=False)),
    Column("text", Text),
    Column("html", Text),
    Column("metadata", JSONB),
)

ARCHIVE_ASSETS = Table(
    "archive_assets",
    ARCHIVE_METADATA,
    Column("id", UUID(as_uuid=False)),
    Column("page_id", UUID(as_uuid=False)),
    Column("block_id", UUID(as_uuid=False)),
    Column("asset_type", Text),
    Column("source_url", Text),
    Column("storage_uri", Text),
    Column("file_name", Text),
    Column("extension", Text),
    Column("mime_type", Text),
    Column("size_bytes", BigInteger),
    Column("content_hash", Text),
    Column("downloaded", Boolean),
    Column("metadata", JSONB),
)

OCR_RESULTS = Table(
    "ocr_results",
    ARCHIVE_METADATA,
    Column("id", UUID(as_uuid=False)),
    Column("page_id", UUID(as_uuid=False)),
    Column("asset_id", UUID(as_uuid=False)),
    Column("block_id", UUID(as_uuid=False)),
    Column("engine", Text),
    Column("status", Text),
    Column("ocr_text", Text),
    Column("structured_data", JSONB),
    Column("elapsed_seconds", Numeric),
    Column("error", Text),
    Column("manual_review_required", Boolean),
)
```

- [ ] **步骤 2：扩展 `ArchiveStore.__init__()`**

将构造函数改为支持连接工厂：

```python
def __init__(self, dsn, connection_factory=None):
    if not dsn:
        raise ValueError("archive store dsn is required")

    self.dsn = dsn
    self.connection_factory = connection_factory
    self._engine = None
    self.pages = []
    self.blocks = []
    self.assets = []
```

新增连接获取方法：

```python
def _connect(self):
    """获取 PostgreSQL 连接；测试可注入 fake connection。"""
    if self.connection_factory:
        return self.connection_factory()
    if self._engine is None:
        self._engine = create_engine(self.dsn)
    return self._engine.connect()
```

- [ ] **步骤 3：运行既有测试确认未破坏内存契约**

运行：

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_store.py::test_archive_store_persists_page_block_and_asset tests/test_archive_store.py::test_archive_store_rejects_empty_dsn -q
```

预期：通过。

## 任务 3：实现 `save_archive_page()` 事务写入

**文件：**
- 修改：`APP/engine/engine/archive_store.py`

- [ ] **步骤 1：新增归档对象 payload 转换方法**

在 `ArchiveStore` 内新增：

```python
@staticmethod
def build_archive_page_payload(archive_page):
    """从归档对象构建 archive_pages payload。"""
    meta = deepcopy(archive_page.get("meta", {}) or {})
    content = deepcopy(archive_page.get("content", {}) or {})
    payload = ArchiveStore.build_page_payload(
        {
            **meta,
            "html": content.get("html", ""),
            "markdown": content.get("markdown", ""),
            "metadata": meta.get("metadata", {}),
        }
    )
    payload["contains_ocr"] = bool(meta.get("contains_ocr", False))
    payload["contains_table"] = bool(meta.get("contains_table", False))
    payload["requires_structuring"] = bool(meta.get("requires_structuring", False))
    return payload
```

- [ ] **步骤 2：新增插入辅助方法**

在 `ArchiveStore` 内新增：

```python
def _insert_returning_id(self, connection, table, payload):
    """插入记录并返回数据库生成的 ID。"""
    statement = insert(table).values(**payload).returning(table.c.id)
    return connection.execute(statement).scalar_one()
```

- [ ] **步骤 3：实现 `save_archive_page()`**

在 `ArchiveStore` 内新增：

```python
def save_archive_page(self, archive_page):
    """在一个事务内保存页面、块、资产和 OCR 结果。"""
    connection = self._connect()
    transaction = connection.begin()
    block_id_map = {}
    asset_id_map = {}
    ocr_result_ids = []
    try:
        page_payload = self.build_archive_page_payload(archive_page)
        page_id = self._insert_returning_id(connection, ARCHIVE_PAGES, page_payload)

        for block in archive_page.get("blocks", []) or []:
            original_block_id = block.get("id")
            block_payload = self.build_block_payload(page_id, block)
            parent_block_id = block_payload.get("parent_block_id")
            if parent_block_id in block_id_map:
                block_payload["parent_block_id"] = block_id_map[parent_block_id]
            block_id = self._insert_returning_id(connection, ARCHIVE_BLOCKS, block_payload)
            if original_block_id:
                block_id_map[original_block_id] = block_id

        for asset in archive_page.get("assets", []) or []:
            original_asset_id = asset.get("id")
            asset_payload = self.build_asset_payload(page_id, asset)
            block_id = asset_payload.get("block_id")
            if block_id in block_id_map:
                asset_payload["block_id"] = block_id_map[block_id]
            asset_id = self._insert_returning_id(connection, ARCHIVE_ASSETS, asset_payload)
            if original_asset_id:
                asset_id_map[original_asset_id] = asset_id

        for ocr_result in archive_page.get("ocr_results", []) or []:
            ocr_payload = self.build_ocr_payload(page_id, ocr_result)
            asset_id = ocr_payload.get("asset_id")
            block_id = ocr_payload.get("block_id")
            if asset_id in asset_id_map:
                ocr_payload["asset_id"] = asset_id_map[asset_id]
            if block_id in block_id_map:
                ocr_payload["block_id"] = block_id_map[block_id]
            ocr_result_ids.append(
                self._insert_returning_id(connection, OCR_RESULTS, ocr_payload)
            )

        transaction.commit()
        return {
            "page_id": page_id,
            "block_ids": block_id_map,
            "asset_ids": asset_id_map,
            "ocr_result_ids": ocr_result_ids,
            "counts": {
                "pages": 1,
                "blocks": len(block_id_map),
                "assets": len(asset_id_map),
                "ocr_results": len(ocr_result_ids),
            },
        }
    except Exception:
        transaction.rollback()
        raise
    finally:
        close = getattr(connection, "close", None)
        if close:
            close()
```

- [ ] **步骤 4：运行本任务测试**

运行：

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_store.py::test_save_archive_page_writes_page_blocks_assets_and_ocr_in_one_transaction tests/test_archive_store.py::test_save_archive_page_rolls_back_when_insert_fails -q
```

预期：通过。

## 任务 4：补齐 payload 字段兼容和全量归档存储回归

**文件：**
- 修改：`APP/engine/engine/archive_store.py`
- 修改：`APP/engine/tests/test_archive_store.py`

- [ ] **步骤 1：增加可选字段测试**

新增测试：

```python
def test_build_archive_page_payload_carries_archive_flags():
    """归档页面 payload 应携带归档状态标志。"""
    from engine.archive_store import ArchiveStore

    payload = ArchiveStore.build_archive_page_payload(
        {
            "meta": {
                "source_url": "https://www.hubei.gov.cn/a.shtml",
                "domain": "www.hubei.gov.cn",
                "title": "归档标志样例",
                "fetched_at": "2026-05-21T15:30:00+08:00",
                "content_hash": "2" * 64,
                "contains_ocr": True,
                "contains_table": True,
                "requires_structuring": True,
            },
            "content": {"html": "<html></html>", "markdown": "# 归档标志样例"},
        }
    )

    assert payload["contains_ocr"] is True
    assert payload["contains_table"] is True
    assert payload["requires_structuring"] is True
    assert payload["html"] == "<html></html>"
    assert payload["markdown"] == "# 归档标志样例"
```

- [ ] **步骤 2：运行全量归档存储测试**

运行：

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_store.py -q
```

预期：通过，保持现有迁移字段测试、payload 构造测试和内存契约测试全部通过。

## 任务 5：本切片验证和提交

**文件：**
- 修改：`APP/engine/engine/archive_store.py`
- 修改：`APP/engine/tests/test_archive_store.py`

- [ ] **步骤 1：运行页面归档相关回归**

运行：

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive.py tests/test_archive_store.py -q
```

预期：通过。

- [ ] **步骤 2：运行输出/治理相关回归**

运行：

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_output.py tests/test_output_directory.py tests/test_governance.py tests/test_ng_no_ai.py -q
```

预期：通过。

- [ ] **步骤 3：检查工作树只包含本切片变更**

运行：

```bash
git status --short
```

预期：至少包含 `APP/engine/engine/archive_store.py`、`APP/engine/tests/test_archive_store.py` 和本计划文件。仓库中已有大量非本任务改动，提交前只暂存本切片相关文件。

- [ ] **步骤 4：提交**

运行：

```bash
git add APP/engine/engine/archive_store.py APP/engine/tests/test_archive_store.py docs/superpowers/plans/2026-05-22-page-archive-postgres-write-layer.md
git commit -m "实现页面归档PostgreSQL写入层"
```

预期：生成一个中文 commit message 的提交。

## 后续切片边界

- 下一切片：采集执行链路接入归档，只在 `archive.enabled=true` 时组装 archive package 和主库 payload。
- 再下一切片：列表页 discovery 到详情页 archive 的单页最小闭环。
- 最后切片：使用 `ARCHIVE_PG_DSN` 做真实 PostgreSQL 集成验证，跑迁移并写入一条样例。

## 自检

- 需求覆盖：本计划只覆盖“真实 PostgreSQL 写入执行层”，没有把执行链路、列表发现和真实库集成验证混入同一提交。
- 占位检查：无未完成标记、泛化描述或留空步骤。
- 类型一致性：测试和实现统一使用 `save_archive_page()`、`connection_factory`、`build_archive_page_payload()`、`block_ids`、`asset_ids`、`ocr_result_ids`。
