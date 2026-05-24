# OCR 精抽 → structured_records 切片

**目标：** 当规则配置 `structuring.enabled=true` 时，采集引擎在页面归档后把 OCR 块文本按策略解析为结构化行，追加到 `archive_page["structured_records"]`，并由 `ArchiveStore.save_archive_page` 一并写入 `structured_records` 表。

**架构：** 新增 `structuring.py` 纯函数模块 `run_structuring(blocks, cfg)`，在 `_maybe_archive_page` 中调用。`archive_store.py` 补充 `STRUCTURED_RECORDS` SQLAlchemy 表定义与写入循环。`engine.py` 只在已构建 `archive_page` 后调用 `run_structuring` 并注入结果。

## 范围

**必须做：**
- `structuring.py`：`run_structuring(blocks, cfg) -> list[dict]`，支持 `ocr_table` 策略（按列/关键词拆分 OCR 行 → rows）。
- `archive_store.py`：新增 `STRUCTURED_RECORDS` 表 + `save_archive_page` 写入循环 + 返回计数。
- `engine.py`：`_maybe_archive_page` 在调用 `store.save_archive_page` 前把 `structured_records` 注入 `archive_page`。
- 单条策略失败不崩（跳过该策略）。

**不做：**
- Dashboard 查看界面。
- 精抽结果搜索 / 全文索引。
- 翻页 / 多入口。
- 连真实 PostgreSQL。

## 文件

- 新增：`APP/engine/engine/structuring.py`
- 修改：`APP/engine/engine/archive_store.py`（STRUCTURED_RECORDS 表 + 写入循环）
- 修改：`APP/engine/engine/engine.py`（调用 run_structuring）
- 新增：`APP/engine/tests/test_archive_structuring.py`
- 新增：`docs/superpowers/plans/2026-05-26-ocr-structuring.md`（本文件）

## 策略 DSL（最小版）

```yaml
structuring:
  enabled: true
  strategies:
    - record_type: "dataset_row"
      applies_to:
        block_types: ["ocr"]
        keywords: ["数据集名称", "申报单位"]
```

`applies_to.keywords`：在 OCR 文本中找到包含任意关键词的行作为 header，其后每行拆分为 `raw_columns`，与 header 列对齐后存入 `data`。无关键词命中时不产出记录（跳过而非报错）。

## 验收

- `structuring` 未启用 → archive_page 无 structured_records 字段（或空列表）。
- 启用 + OCR 块含表格文本 → structured_records 包含预期行数和字段。
- OCR 块文本不含策略关键词 → 该块跳过，不产出记录。
- ArchiveStore mock 收到的 archive_page 包含 structured_records 列表。
