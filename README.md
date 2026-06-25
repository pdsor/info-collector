# info-collector

Info Collector NG 本地 MVP 是一个规则驱动的互联网公开信息采集、页面归档与数据治理系统。当前项目目标以 `DOCS/LatestRequirementDocument.md` v2.2 为准：系统内不调用 LLM、不集成 Agent、不使用 Crawl4AI，采集、提取、治理、归档、OCR 和发布均由人工维护的 YAML 规则与本地确定性流程完成。

最近代码已合并 PaddleOCR 表格结构识别能力，主线能力包括页面归档、图片 OCR、PaddleOCR `PPStructureV3` 表格结构识别、规则健康检测、DOM 漂移基线、Source 信任分自动更新、PostgreSQL 主库写入和本地归档包审计。

## 项目结构

```text
APP/
  dashboard/       # 本地管理控制台，Flask + Vue 3/Vite + SQLite 元数据
    apis/          # REST API 蓝图
    migrations/    # 控制台 SQLite 迁移
    static/dist/   # 前端构建产物，由 Flask 托管
    web/           # 控制台前端工程
  engine/          # YAML 规则驱动采集引擎
    config.yaml    # 项目级 PostgreSQL 配置，本地需自行创建
    config.example.yaml
    engine_cli.py  # CLI 入口，需通过 .venv 运行
    engine/        # 核心采集、解析、治理、归档、OCR 插件
    output/        # 本地 JSON 输出、归档包、状态文件
    rules/         # 当前真实 YAML 规则目录
    tests/         # pytest 测试
    run_paddleocr_image_test.py
    run_paddleocr_table_structure_test.py
DOCS/              # 需求、设计和历史说明
docs/superpowers/  # 实施计划、专项设计和规则手册
migrations/        # PostgreSQL 全量迁移脚本
```

## 文档位置

- `DOCS/LatestRequirementDocument.md`：当前唯一权威需求来源，版本为 v2.2。
- `DOCS/README.md`：文档入口与有效文档说明。
- `DOCS/ImageOcrCollectionRequirementUpdate.md`：图片 OCR 能力需求补充。
- `DOCS/PageArchiveCollectionRedesign.md`：页面归档能力设计补充。
- `docs/superpowers/manuals/yaml-rule-writing-handbook.md`：YAML 规则编写手册。
- `docs/superpowers/plans/2026-06-16-paddleocr-table-structure-recognition.md`：PaddleOCR 表格结构识别实施计划。
- `docs/superpowers/plans/2026-06-09-release-readiness-cleanup.md`：发布就绪清理记录。
- `docs/superpowers/specs/`：专项设计文档。

## 当前功能

- Source Center：从 `APP/engine/rules` 下的 YAML 规则同步来源注册表，展示来源状态、分类、域名、信任分、解析策略和生命周期；有历史治理数据时，按历史质量分混合更新信任分。
- Rule Center：管理人工编写的 YAML 规则，支持读取、保存、启停、沙箱预览、OCR 摘要、选择器健康检测和 DOM 漂移基线。
- Task Center：通过 Flask 后台线程调用 `engine_cli.py`，支持单规则或全量规则执行、JSONL 事件流、SSE 进度推送、任务历史和任务日志。
- Governance Center：从本地输出读取治理摘要，展示字段完整率、去重数量、注入风险、质量评分和最近采集文件。
- Archive Center：从 `APP/engine/output/<主题>/<平台>/archives/<content_hash>/page.json` 读取本地归档包，展示 heading、paragraph、image、ocr 等块和结构化记录。
- Engine：支持 HTTP、API、Playwright 浏览器渲染，基于 parsel/lxml 和 YAML 选择器做确定性结构化提取。
- 页面归档：支持列表页发现详情页，抓取详情正文，拆分文本块，下载图片资产，执行 OCR，并写入本地归档包与 PostgreSQL 归档表。
- 图片 OCR：支持 `image_extraction` 补充采集和 `archive.image_ocr` 页面归档 OCR；默认本地插件包括 `tesseract` 与 `paddleocr`。
- PaddleOCR 表格结构识别：`paddleocr` 插件支持 `table_recognition`，可通过 `PPStructureV3` 输出 `table_structure_markdown`、`table_structure_html`、原始 OCR 行、质量状态和人工复核标记。
- PostgreSQL 主库：普通采集结果写入 `collection_*` 表，页面归档写入 `archive_*`、`ocr_results`、`structured_records` 表。
- 本地审计输出：JSON 数据、归档包、OCR 文本、Markdown 表格、状态文件和去重库保留在 `APP/engine/output` 与 `APP/engine/dedup.db`，用于调试和控制台展示。

## 明确不包含

- 不调用 LLM。
- 不集成 AI Agent。
- 不使用 Crawl4AI。
- 不自动生成或自动修复规则。
- 不调用云端 OCR 或视觉大模型。
- 不自动绕过验证码或人机验证。
- 不内置 Celery、MinIO、Elasticsearch、Milvus；这些属于后续生产化替换目标。
- MVP 阶段为本地单用户部署，不提供复杂多租户权限。

## 快速开始

除特别说明外，下面的命令默认在仓库根目录执行。

### 1. 创建引擎虚拟环境

```bash
cd APP/engine
./venv.sh create
```

`engine_cli.py` 有虚拟环境保护，推荐统一使用：

```bash
cd APP/engine
./venv.sh run python engine_cli.py --help
```

如需浏览器渲染，安装 Playwright Chromium：

```bash
cd APP/engine
.venv/bin/python -m playwright install chromium
```

### 2. 配置 PostgreSQL

采集主事实源为 PostgreSQL。项目只读取 `APP/engine/config.yaml`，不从环境变量读取主库连接串。可从示例复制：

```bash
cp APP/engine/config.example.yaml APP/engine/config.yaml
```

配置内容：

```yaml
database:
  pg_dsn: "postgresql://postgres:<password>@<host>:5432/info_collector"
```

初始化表结构：

```bash
psql "postgresql://postgres:<password>@<host>:5432/info_collector" -f migrations/20260521_archive_postgres.sql
psql "postgresql://postgres:<password>@<host>:5432/info_collector" -f migrations/20260604_collection_postgres.sql
```

普通采集结果写入 `collection_runs`、`collection_items`、`collection_run_items`、`collection_governance_records`。页面归档写入 `archive_pages`、`archive_blocks`、`archive_assets`、`ocr_results`、`structured_records`。本地 JSON 和归档包继续保留为调试、审计和控制台展示来源。

### 3. 构建并启动控制台

控制台前端位于 `APP/dashboard/web`，Flask 服务托管 `APP/dashboard/static/dist`。首次启动或前端代码变更后，需要安装依赖并构建前端：

```bash
cd APP/dashboard
../engine/.venv/bin/python -m pip install -r requirements.txt

cd web
npm install
npm run build

cd ..
../engine/.venv/bin/python server.py
```

访问地址：

```text
http://localhost:5000
```

前端页面：

- `/source/index`：来源中心
- `/rule/index`：规则中心
- `/task/index`：任务中心
- `/governance/index`：治理中心
- `/archive/index`：归档中心

主要 API 前缀：

- `/api/sources`
- `/api/rules`
- `/api/tasks`
- `/api/cron`
- `/api/data`
- `/api/governance`
- `/api/archives`
- `/api/health`

### 4. 执行采集

当前真实规则目录：

```text
APP/engine/rules/数据要素/nda_gov_data_element_cases.yaml
```

列出规则：

```bash
cd APP/engine
./venv.sh run python engine_cli.py list-rules --format=json
```

执行全部启用规则：

```bash
cd APP/engine
./venv.sh run python engine_cli.py run-all
```

执行单条规则：

```bash
cd APP/engine
./venv.sh run python engine_cli.py run-rule rules/数据要素/nda_gov_data_element_cases.yaml --format=json
```

输出采集明细：

```bash
cd APP/engine
./venv.sh run python engine_cli.py run-rule rules/数据要素/nda_gov_data_element_cases.yaml --format=json --print-data=both
```

查看状态和日志：

```bash
cd APP/engine
./venv.sh run python engine_cli.py state
./venv.sh run python engine_cli.py list-logs --format=json
./venv.sh run python engine_cli.py read-log <log_name> --lines=100 --format=json
```

## 当前规则说明

当前内置规则为国家数据局“数据要素×”典型案例采集：

```text
APP/engine/rules/数据要素/nda_gov_data_element_cases.yaml
```

规则要点：

- `source.client: desktop`，使用桌面 UA 抓取 HTML。
- `list.pagination.type: url_template`，从国家数据局列表页翻页，当前 `max_pages: 5`。
- `extract` 提取 `title`、`url`、`publish_time`。
- `dedup.incremental: true`，通过 `url_to_id_pattern` 从详情 URL 提取 `raw_id` 做增量去重。
- `discovery.enabled: true`，列表采集后继续发现详情页候选。
- `archive.enabled: true`，详情页进入页面归档链路。
- `archive.image_ocr.enabled: true`，详情页图片下载后执行 OCR。
- `archive.image_ocr.ocr.plugin: paddleocr`，启用本地 PaddleOCR 子进程插件。
- `table_recognition: true` 与 `table_recognition_pipeline: PPStructureV3`，启用表格结构识别。
- `timeout_seconds: 7200`，PaddleOCR 首次下载或加载模型可能耗时较长。

Rule v2 推荐最小结构：

```yaml
rule_id: "3fa85f64-5717-4562-b3fc-2c963f66afa6"
source_id: "example-source"
version: 1
status: PRODUCTION
source:
  platform: "example"
  type: "html"
  client: "desktop"
  url: "https://example.com"
list:
  items_path: "css:article"
extract:
  title: { selector: "h1", type: "text" }
  url: { selector: "a", type: "attribute", attribute: "href" }
output:
  fields: ["title", "url"]
  save_raw: false
governance:
  sanitize: true
  dedup: hash
```

禁止使用：

```yaml
source:
  client: "crawl4ai"
  extraction:
    enabled: true
ocr:
  cloud_ocr: true
  vision_model: "..."
  api_key: "..."
agent:
  enabled: true
llm:
  provider: "..."
```

## 图片 OCR 与表格结构识别

主引擎环境 `APP/engine/.venv` 包含 Tesseract Python 包装依赖。系统级 Tesseract 需要在宿主机安装：

```text
tesseract-ocr
tesseract-ocr-chi-sim
tesseract-ocr-eng
```

PaddleOCR 依赖较重，默认通过独立环境隔离。`paddleocr` 插件默认调用 `APP/engine/.venv-paddleocr/bin/python`，也可以通过规则中的 `archive.image_ocr.ocr.python` 或环境变量 `PADDLEOCR_PYTHON` 覆盖。

PaddleOCR 环境只要求目标 Python 可以 `import paddleocr`，建议按 PaddleOCR 官方 CPU 版说明安装 `paddlepaddle` 与 `paddleocr`。安装后检查：

```bash
cd APP/engine
.venv-paddleocr/bin/python -c "import paddleocr; print(paddleocr.__version__)"
```

单图 OCR 诊断，支持普通 OCR 和表格结构识别：

```bash
cd APP/engine
.venv-paddleocr/bin/python run_paddleocr_image_test.py /path/to/table.png \
  --table-recognition \
  --table-recognition-pipeline PPStructureV3 \
  --output /tmp/paddleocr_image_result.json
```

独立表格结构诊断工具当前固定使用 `TableRecognitionPipelineV2`，用于离线对照：

```bash
cd APP/engine
.venv-paddleocr/bin/python run_paddleocr_table_structure_test.py /path/to/table.png \
  --limit-side-len 960 \
  --output /tmp/paddleocr_table_structure_result.json
```

当前数据要素规则的归档 OCR 配置示例：

```yaml
archive:
  image_ocr:
    enabled: true
    images:
      selector: ".detail .article img"
      src_attribute: "src"
      include_alt: true
      max_images: 20
    download:
      dir_template: "/tmp/scraper_imgs/{task_id}"
      retries: 3
      retry_interval_seconds: 2
      timeout_seconds: 20
      max_size_mb: 8
    ocr:
      plugin: "paddleocr"
      lang: "ch"
      text_detection_model_name: "PP-OCRv5_mobile_det"
      text_recognition_model_name: "PP-OCRv5_mobile_rec"
      text_det_limit_side_len: 960
      table_recognition: true
      table_recognition_pipeline: "PPStructureV3"
      home: "/tmp/paddleocr-home"
      timeout_seconds: 7200
```

OCR 输出会保留：

- `ocr_plugin`、`ocr_engine`、`ocr_status`、`ocr_text`、`ocr_error`
- `ocr_elapsed_seconds`、`ocr_empty`
- `ocr_quality_status`、`ocr_quality_reasons`
- `manual_review_required`
- `structured_data.raw_text`
- `structured_data.markdown`
- `structured_data.table_structure_markdown`
- `structured_data.table_structure_html`
- `structured_data.table_structure`
- `structured_data.lines`
- `structured_data.corrections`

## 输出与存储

- `APP/engine/output/<主题>/<平台>/data_<date>.json`：普通采集结果。
- `APP/engine/output/<主题>/combined_latest.json`：主题级合并结果。
- `APP/engine/output/<主题>/<平台>/archives/<content_hash>/page.json`：页面归档摘要。
- `APP/engine/output/<主题>/<平台>/archives/<content_hash>/page.html`：详情页 HTML。
- `APP/engine/output/<主题>/<平台>/archives/<content_hash>/page.md`：详情页 Markdown。
- `APP/engine/output/<主题>/<平台>/archives/<content_hash>/blocks.json`：归档块列表。
- `APP/engine/output/<主题>/<平台>/archives/<content_hash>/assets/manifest.json`：图片资产清单。
- `APP/engine/output/state.json`：采集状态。
- `APP/engine/dedup.db`：增量去重 SQLite 库。
- `APP/dashboard/dashboard.db`：控制台元数据、任务历史和定时任务。
- `APP/dashboard/dashboard.log`：控制台日志。

说明：PostgreSQL 是普通采集和页面归档的主库；本地输出仍用于调试、审计和当前控制台的数据预览、治理中心、归档中心展示。

## 常用 CLI

```bash
cd APP/engine

# 查看帮助
./venv.sh run python engine_cli.py --help

# 扫描规则并注册到 state.json
./venv.sh run python engine_cli.py scan

# 列出规则
./venv.sh run python engine_cli.py rules
./venv.sh run python engine_cli.py list-rules --format=json

# 读取规则
./venv.sh run python engine_cli.py get-rule rules/数据要素/nda_gov_data_element_cases.yaml --format=json

# 启停规则
./venv.sh run python engine_cli.py enable-rule rules/数据要素/nda_gov_data_element_cases.yaml --enable=true
./venv.sh run python engine_cli.py enable-rule rules/数据要素/nda_gov_data_element_cases.yaml --enable=false

# 执行规则
./venv.sh run python engine_cli.py run-all
./venv.sh run python engine_cli.py run-all --format=jsonl
./venv.sh run python engine_cli.py run-rule rules/数据要素/nda_gov_data_element_cases.yaml --format=json
./venv.sh run python engine_cli.py run-rule rules/数据要素/nda_gov_data_element_cases.yaml --format=jsonl

# 查看状态和日志
./venv.sh run python engine_cli.py state
./venv.sh run python engine_cli.py list-logs --format=json
```

## 验证

轻量验证：

```bash
cd APP/engine
./venv.sh run python -m pytest tests/test_ocr_plugins.py tests/test_paddleocr_table_markdown.py tests/test_paddleocr_table_structure_runner.py -q

cd ../dashboard
../engine/.venv/bin/python -m pytest tests -q
../engine/.venv/bin/python -m py_compile server.py apis/*.py

cd web
npm run build
```

完整引擎测试：

```bash
cd APP/engine
./venv.sh run python -m pytest tests -q
```

PaddleOCR 真模型诊断会加载本地模型和缓存，耗时明显高于单元测试；没有准备 `.venv-paddleocr` 或模型缓存时，不纳入默认轻量验证。

## 排查提示

- 运行 `engine_cli.py` 时提示虚拟环境错误：使用 `cd APP/engine && ./venv.sh run python engine_cli.py ...`。
- 提示缺少 `APP/engine/config.yaml`：从 `config.example.yaml` 复制并填写 `database.pg_dsn`。
- 控制台首页返回前端构建缺失：进入 `APP/dashboard/web` 执行 `npm install && npm run build`。
- 归档中心无数据：先执行启用 `archive.enabled` 的规则，并确认本地存在 `APP/engine/output/<主题>/<平台>/archives/*/page.json`。
- PaddleOCR 插件不可用：确认 `.venv-paddleocr/bin/python` 存在，且可以 `import paddleocr`；必要时在规则中显式配置 `archive.image_ocr.ocr.python`。
- 首次 PaddleOCR 很慢：模型下载和缓存初始化属于预期现象，可检查 `home: "/tmp/paddleocr-home"` 是否可写。
