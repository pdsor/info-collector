# info-collector

Info Collector NG 本地 MVP 是一个规则驱动的互联网公开信息采集与治理系统。当前版本以 `DOCS/LatestRequirementDocument.md` v2.2 为准，系统内不调用 AI、不集成 Agent、不使用 Crawl4AI，采集、提取、治理和发布均由确定性规则完成。

## 项目结构

```text
APP/
  dashboard/       # 本地管理控制台，Flask + Vue 3 CDN + SQLite
    apis/          # REST API
    migrations/    # SQLite 迁移
    static/        # 前端页面、脚本和样式
  engine/          # YAML 规则驱动采集引擎
    engine_cli.py  # CLI 入口
    engine/        # 核心采集、解析、治理、输出模块
    rules/         # YAML 规则文件
    tests/         # pytest 测试
DOCS/              # 需求和设计文档
docs/              # 实施计划与操作手册
```

## 当前能力

- Source Center：从 YAML 规则派生来源注册表，展示来源状态、分类、域名、信任分和解析策略。
- Rule Center：管理人工编写的 YAML DSL 规则，支持旧规则和 Rule v2 最小结构。
- Task Center：通过后台线程执行采集任务，任务状态映射到 NG 状态机。
- Governance Center：展示字段完整率、去重、注入风险和质量评分。
- Engine：支持 HTTP、API、Playwright 浏览器渲染和基于 parsel/lxml 的确定性结构化提取。

## 明确不包含

- 不调用 LLM。
- 不集成 AI Agent。
- 不使用 Crawl4AI。
- 不自动生成或自动修复规则。
- MVP 阶段不内置 PostgreSQL、Celery、MinIO、Elasticsearch、Milvus；这些属于后续生产化替换目标。

## 快速开始

### 1. 创建引擎虚拟环境

```bash
cd APP/engine
./venv.sh create
```

如需浏览器渲染：

```bash
./venv.sh run playwright install chromium
```

### 2. 启动控制台

```bash
cd APP/dashboard
../engine/.venv/bin/python server.py
```

访问：

```text
http://localhost:5000
```

### 3. 执行采集

```bash
cd APP/engine
.venv/bin/python engine_cli.py run-all
.venv/bin/python engine_cli.py run-rule rules/数据要素/tmtpost_data_articles.yaml --format=json
```

## 规则约束

旧规则仍可运行，但推荐逐步迁移到 Rule v2：

```yaml
rule_id: "3fa85f64-5717-4562-b3fc-2c963f66afa6"
source_id: "example-source"
version: 1
status: PRODUCTION
source:
  platform: "example"
  type: "html"
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
```

## 验证

```bash
cd APP/engine
.venv/bin/python -m pytest tests -q

cd ../../
APP/engine/.venv/bin/python -m py_compile APP/dashboard/server.py APP/dashboard/apis/*.py
node --check APP/dashboard/static/js/app.js
```
