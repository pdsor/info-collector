# 列表多候选批量详情归档切片

**目标：** 让 discovery 分支不再只挑「第一条」候选，而是按 `discovery.max_details`（默认 1，保持现有行为）顺序遍历候选列表，逐条详情抓取 → 组装 → 落盘 → 写主库；同时在同一次 run 内做两层去重：
1. 同 detail_url 重复 → 跳过；
2. 同 content_hash（由 `build_archive_page` 计算）重复 → 跳过。

**架构：** 把 `_discover_first_detail` 改为 `_discover_candidates`，返回最多 `max_details` 条命中（且 URL 去重）。`_archive_after_pipeline` 遍历候选，对每条调用现有 `_extract_detail_blocks`+`_extract_detail_assets_and_ocr`+`_maybe_archive_page` 流水。引入 module 级 helper / 局部 set 跟踪 content_hash。结果聚合策略：保留 `archive_page_id`/`archive_package_path` 指向首条成功归档（向后兼容），新增 `archive_pages: [{page_id, package_path, source_url, content_hash}, ...]` 列表。

## 范围

**必须做：**
- `discovery.max_details`（int，默认 1）控制单次 run 归档的候选数。
- 候选 URL 在同一次 run 内去重（保留首次出现）。
- 归档对象 `content_hash` 在同一次 run 内去重（首条入库，重复跳过）。
- `run()` 返回新增 `archive_pages` 列表（包含每条归档的 `page_id`/`package_path`/`source_url`/`content_hash`）。
- 单条详情失败不影响后续候选（捕获记入跳过计数，不抛到 run）。

**不做：**
- 翻页 / 多入口 entry。
- 跨 run 持久化的 content_hash 去重（依旧只在本 run 内）。
- Dashboard / 真实 PG 集成。

## 文件

- 修改：`APP/engine/engine/engine.py`
  - `_discover_first_detail` → `_discover_candidates(rule, list_html) -> list[dict]`，内部 URL 去重 + 截断 `max_details`。
  - `_archive_after_pipeline`：遍历候选，按 content_hash 去重，聚合到 `archive_pages`。
  - `_maybe_archive_page` 增加可选 `seen_hashes: set[str]` 参数；命中则返回 `{}`。
- 新增：`APP/engine/tests/test_archive_batch_details.py`（4 用例）。
- 新增：`docs/superpowers/plans/2026-05-26-batch-detail-archive.md`（本文件）。

## 验收

- 旧测试不回归（默认 `max_details=1`）。
- `max_details=3` 且列表有 5 条命中 → 写 3 次。
- 列表含重复 URL → 只归档一次。
- 两条不同 URL 但 detail_html 内容完全一致 → 仅一条入库（content_hash 去重）。
