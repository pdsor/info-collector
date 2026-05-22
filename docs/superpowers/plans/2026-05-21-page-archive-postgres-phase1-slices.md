# 页面归档 PostgreSQL 第一阶段切片计划

> **面向代理工作者：** 执行本计划时必须按切片逐个完成。每个切片都是一次可以独立交付、独立验证、独立提交的任务。开始任一切片前先阅读 `DOCS/PageArchiveCollectionRedesign.md`、`docs/superpowers/plans/2026-05-21-page-archive-postgres.md` 和本文件。

**目标：** 第一阶段只建立页面归档 MVP 的领域对象、存储接口、文件包输出和最小规则兼容，不大面积重构 `engine.py`。

**架构：** PostgreSQL 是页面、块、资产、OCR 和后续精抽结果的主事实源。第一阶段先用稳定接口和可测试对象固定数据契约，文件系统只作为调试包和资产缓存。真实 PostgreSQL 写入放到独立切片中接入，避免和归档对象组装混在一个任务里。

**技术栈：** Python、pytest、现有 `engine` 包、现有 `OutputManager`、环境变量 `ARCHIVE_PG_DSN`、后续 PostgreSQL/SQLAlchemy。

---

## 总体上下文

- 主需求来源：`DOCS/PageArchiveCollectionRedesign.md`
- 总体计划来源：`docs/superpowers/plans/2026-05-21-page-archive-postgres.md`
- 本文件只拆第一阶段小任务。
- 每个切片完成后都要运行对应测试并提交中文 commit message。
- 没有 PostgreSQL 连接串时，代码必须明确报错或显式跳过入库，不能静默失败。
- 大二进制资产不入库，PostgreSQL 只保存资产元数据和 `storage_uri`。

## 切片 1：归档存储接口契约

**目标：** 新增 `ArchiveStore` 最小接口，固定 `save_page()`、`save_block()`、`save_asset()` 的输入输出契约。

**文件范围：**

- 新建：`APP/engine/engine/archive_store.py`
- 新建或修改：`APP/engine/tests/test_archive_store.py`

**前置上下文：**

- 暂不连接真实 PostgreSQL。
- 可以用内存列表保存测试数据。
- `dsn` 不能为空；为空时抛出明确异常。

**测试命令：**

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_store.py -q
```

**验收标准：**

- 页面、块、资产都能生成非空 ID。
- 块记录包含 `page_id`。
- 资产记录能关联图片块 `block_id`。
- 缺少 `dsn` 时明确失败。

**提交：**

```bash
git add APP/engine/engine/archive_store.py APP/engine/tests/test_archive_store.py
git commit -m "增加归档存储接口"
```

## 切片 2：页面归档对象组装

**目标：** 新增 `build_archive_page()`，把详情页组装成统一归档对象。

**文件范围：**

- 新建：`APP/engine/engine/archive.py`
- 新建或修改：`APP/engine/tests/test_archive.py`

**前置上下文：**

- 每个页面必须有 `source_url`、`domain`、`title`、`fetched_at`、`content_hash`。
- 输入块可使用旧字段 `type/order/block_id`，函数输出要规范为 `block_type/block_order/id`。
- `content_hash` 由 HTML、Markdown、URL 等确定性内容生成，不依赖随机值。

**测试命令：**

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive.py::test_build_archive_page_generates_meta_content_blocks_and_assets -q
```

**验收标准：**

- 返回对象包含 `meta`、`content`、`blocks`、`assets`、`paths`。
- `meta.content_hash` 是 64 位哈希。
- `contains_ocr`、`contains_table`、`requires_structuring` 可由块类型推导。
- 不接入 AI、不接入云 OCR。

**提交：**

```bash
git add APP/engine/engine/archive.py APP/engine/tests/test_archive.py
git commit -m "补充页面归档对象"
```

## 切片 3：归档调试包落盘

**目标：** 扩展 `OutputManager`，支持保存页面归档调试包。

**文件范围：**

- 修改：`APP/engine/engine/output.py`
- 修改：`APP/engine/tests/test_archive.py`

**前置上下文：**

- 文件包不是主事实源，只用于调试、人工复核和资产缓存。
- 推荐目录为 `{base_path}/{subject}/{platform}/archives/{content_hash}/`。

**测试命令：**

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive.py::test_output_manager_saves_archive_package_structure -q
```

**验收标准：**

- 生成 `page.json`、`page.html`、`page.md`、`blocks.json`。
- 生成 `assets/manifest.json`。
- `page.json` 包含归档元数据、块和资产摘要。
- 不影响现有 JSON 输出测试。

**提交：**

```bash
git add APP/engine/engine/output.py APP/engine/tests/test_archive.py
git commit -m "增加页面归档调试包输出"
```

## 切片 4：OCR 结果与图片资产关联契约

**目标：** 固定 OCR 块、图片块、图片资产之间的关联字段，为后续 PostgreSQL 入库做准备。

**文件范围：**

- 修改：`APP/engine/engine/archive.py`
- 修改：`APP/engine/tests/test_archive.py`

**前置上下文：**

- OCR 块必须能通过 `parent_block_id` 或 `asset_id` 回溯到图片资产。
- 本切片只做对象契约，不改图片下载和 OCR 执行链路。

**测试命令：**

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive.py -q
```

**验收标准：**

- 图片块包含可追溯 `asset_id` 或可由资产清单反查。
- OCR 块包含 `parent_block_id`。
- OCR 结果可形成未来 `ocr_results` 的 `page_id/asset_id/block_id/ocr_text/structured_data` 入库对象。

**提交：**

```bash
git add APP/engine/engine/archive.py APP/engine/tests/test_archive.py
git commit -m "关联OCR块和图片资产"
```

## 切片 5：规则 DSL 归档配置兼容

**目标：** 让 `RuleParser` 接受 `discovery`、`archive`、`structuring` 配置块。

**文件范围：**

- 修改：`APP/engine/engine/rule_parser.py`
- 修改：`APP/engine/tests/test_rule_v2.py`

**前置上下文：**

- 只做基础校验，不实现复杂翻页和详情页批量归档。
- `archive.enabled=true` 时允许 `archive.markdown` 和 `archive.image_ocr`。
- `structuring` 先允许关闭或声明策略，不执行精抽。

**测试命令：**

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_rule_v2.py -q
```

**验收标准：**

- Rule v2 可通过 `discovery/archive/structuring` 配置校验。
- 仍拒绝 AI、Agent、云 OCR 和 `crawl4ai` 配置。
- 现有 Rule v2 测试不回归。

**提交：**

```bash
git add APP/engine/engine/rule_parser.py APP/engine/tests/test_rule_v2.py
git commit -m "兼容页面归档规则配置"
```

## 切片 6：PostgreSQL 表结构迁移草案

**目标：** 新增 PostgreSQL 建表 SQL，定义 `archive_pages`、`archive_blocks`、`archive_assets`、`ocr_results`、`structured_records`。

**文件范围：**

- 新建：`migrations/20260521_archive_postgres.sql`
- 新建或修改：`APP/engine/tests/test_archive_store.py`

**前置上下文：**

- 只定义 SQL，不要求本地有 PostgreSQL 实例。
- 大二进制不入库。
- JSON 字段使用 `jsonb`。

**测试命令：**

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_store.py -q
```

**验收标准：**

- SQL 包含五张表。
- 表字段覆盖主文档第 7.3 节。
- 索引覆盖页面哈希、域名、平台主题、块顺序、资产页面、OCR 页面、结构化记录类型。

**提交：**

```bash
git add migrations/20260521_archive_postgres.sql APP/engine/tests/test_archive_store.py
git commit -m "定义页面归档PostgreSQL表结构"
```

## 切片 7：PostgreSQL 写入适配器

**目标：** 在 `ArchiveStore` 中增加 PostgreSQL 写入路径和连接串解析。

**文件范围：**

- 修改：`APP/engine/engine/archive_store.py`
- 修改：`APP/engine/tests/test_archive_store.py`
- 如需要修改：`APP/engine/requirements.txt`

**前置上下文：**

- 优先读取 `ARCHIVE_PG_DSN`。
- 后续可支持规则里的 `archive_store.dsn`。
- 没有连接串时明确失败或显式跳过，不能静默失败。

**测试命令：**

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive_store.py -q
```

**验收标准：**

- 能构建 `archive_pages`、`archive_blocks`、`archive_assets`、`ocr_results`、`structured_records` 写入 payload。
- 测试不依赖真实 PostgreSQL 服务。
- 真实连接写入逻辑和 payload 构造分离。

**提交：**

```bash
git add APP/engine/engine/archive_store.py APP/engine/tests/test_archive_store.py APP/engine/requirements.txt
git commit -m "接入页面归档主库配置"
```

## 切片 8：第一阶段回归验证

**目标：** 汇总验证页面归档 MVP 的第一阶段能力，确保现有 OCR 相关测试不回归。

**文件范围：**

- 按需修改：`DOCS/PageArchiveCollectionRedesign.md`
- 按需修改：`docs/superpowers/plans/2026-05-21-page-archive-postgres.md`
- 修改：本文件任务状态

**测试命令：**

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_archive.py tests/test_archive_store.py tests/test_rule_v2.py tests/test_image_parser.py tests/test_ocr_plugins.py tests/test_image_extraction.py -q
```

**验收标准：**

- 页面归档对象测试通过。
- 存储接口测试通过。
- Rule v2 兼容测试通过。
- OCR 相关测试不回归。
- 文档说明第一阶段已完成项和未完成项。

**提交：**

```bash
git add DOCS/PageArchiveCollectionRedesign.md docs/superpowers/plans/2026-05-21-page-archive-postgres.md docs/superpowers/plans/2026-05-21-page-archive-postgres-phase1-slices.md
git commit -m "整理页面归档第一阶段切片计划"
```

## 交接格式

每次完成一个切片后，交接说明必须包含：

- 已完成切片编号和名称。
- 修改文件列表。
- 运行过的测试命令和结果。
- 下一切片入口。
- 当前未解决问题或显式跳过项。

## 第一阶段执行状态

截至 2026-05-22，切片 1 到切片 7 已完成并提交：

- 切片 1：新增 `ArchiveStore` 存储接口契约。
- 切片 2：新增 `build_archive_page()` 页面归档对象组装。
- 切片 3：新增 `OutputManager.save_archive_package()` 归档调试包输出。
- 切片 4：固定图片资产、图片块和 OCR 块关联契约。
- 切片 5：兼容 `discovery`、`archive`、`structuring` 规则配置。
- 切片 6：新增 PostgreSQL 页面归档表结构迁移草案。
- 切片 7：新增 `ARCHIVE_PG_DSN`、规则连接串读取和主库 payload 构造。

本阶段仍显式暂不完成：

- 不接入真实 PostgreSQL 服务写入执行。
- 不接入 Elasticsearch。
- 不做复杂翻页、多模板精抽和 Dashboard。
- 不接入 AI、云 OCR 或视觉模型。
- 不把图片、附件、截图等大二进制资产直接写入 PostgreSQL。
