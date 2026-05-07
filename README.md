# info-collector

数据要素价值化线索追踪系统 — 信息收集模块。

## 项目结构

```
info-collector/
├── APP/
│   ├── engine/                      # 采集引擎（Python）
│   │   ├── engine_cli.py             # CLI 入口（强制 venv 检查）
│   │   ├── requirements.txt         # 依赖清单
│   │   ├── credentials.yaml           # API 凭证配置（不提交）
│   │   ├── dedup.db                  # SQLite 去重数据库（自动生成）
│   │   ├── output/                   # 采集输出目录
│   │   ├── rules/                    # YAML 采集规则
│   │   ├── data/                     # 运行时数据（state.json 等）
│   │   ├── engine/                   # 核心代码包
│   │   │   ├── engine.py             # 主引擎（任务队列 + 调度）
│   │   │   ├── rule_parser.py        # YAML 规则解析（Pydantic schema）
│   │   │   ├── crawl_api.py          # API 采集（jsonpath-ng）
│   │   │   ├── crawl_html.py         # HTML 采集（parsel + lxml）
│   │   │   ├── crawl_browser.py      # 浏览器渲染（Playwright）
│   │   │   ├── crawlers/             # 爬虫实现
│   │   │   │   ├── playwright_crawler.py  # Playwright 封装
│   │   │   │   └── crawl4ai_crawler.py    # Crawl4AI LLM 提取
│   │   │   ├── parsers/              # 统一解析层（HTMLParser / JSONParser / UA）
│   │   │   ├── dedup.py              # SQLite 全局去重
│   │   │   ├── output.py             # JSON/CSV/JSONL 输出
│   │   │   ├── state.py              # 状态管理
│   │   │   └── events.py             # 事件总线
│   │   └── tests/                    # 单元测试
│   └── dashboard/                     # 数据看板（Flask + Vue 3 CDN）
│       ├── server.py                 # Flask 服务（端口 5000）
│       ├── requirements.txt          # 看板依赖
│       ├── dashboard.db              # SQLite（cron 调度 + 任务历史）
│       ├── index.html                # 入口页面
│       ├── static/                   # 前端静态资源
│       │   ├── css/style.css         # HUD 风格样式
│       │   └── js/
│       │       ├── app.js            # Vue 3 单文件应用（1300+ 行）
│       │       └── api.js            # REST API 调用封装
│       ├── apis/                     # REST API 蓝图
│       │   ├── rules_api.py          # 规则管理（CRUD）
│       │   ├── tasks_api.py          # 手动触发采集
│       │   ├── logs_api.py           # 实时日志流（SSE）
│       │   ├── data_api.py           # 数据预览
│       │   └── cron_api.py           # Cron 调度管理
│       ├── migrations/               # 数据库迁移脚本
│       └── tests/                    # Dashboard 单元测试
├── docs/superpowers/manuals/         # 操作手册
│   └── yaml-rule-writing-handbook.md # YAML 规则编写手册
├── AGENTS.md                         # 项目编码约束
└── .gitignore
```

## 快速开始

### 1. 创建虚拟环境并安装依赖

```bash
cd APP/engine

# 方式一（推荐）：使用 venv 管理脚本
./venv.sh create

# 方式二：手动操作
python3 -m venv .venv
source .venv/bin/activate  # Linux/macOS
pip install --upgrade pip
pip install -r requirements.txt

# 安装浏览器（Playwright + Crawl4AI 需要）
playwright install chromium
```

### 2. 启动看板

```bash
cd APP/dashboard
pip install -r requirements.txt
python server.py
# 访问 http://localhost:5000
```

### 3. 运行采集

```bash
cd APP/engine
source .venv/bin/activate

# 运行所有已启用的规则
python engine_cli.py run-all

# 运行指定规则
python engine_cli.py run baidu_search

# 查看所有规则
python engine_cli.py list-rules

deactivate
```

## 核心功能

### 采集模式

| 模式 | 说明 | 依赖 |
|------|------|------|
| `api` | HTTP API 请求，JSONPath 提取 | requests, jsonpath-ng |
| `html` | HTML 页面，CSS Selector / XPath 提取 | parsel, lxml |
| `browser` | 浏览器渲染，支持 JS 渲染页面 | playwright |
| `crawl4ai` | LLM 辅助提取，可从复杂页面提取结构化数据 | crawl4ai |

### 客户端策略

`source.client` 支持四种策略：

- `auto` — 根据响应自动降级（HTML → browser → crawl4ai）
- `mobile` — 移动端 UA
- `desktop` — 桌面端 UA
- `browser` — 无头浏览器（Playwright）
- `crawl4ai` — Crawl4AI LLM 提取

### 去重机制

全局 SQLite 去重表，基于 `dedup.url_to_id_pattern` 从 URL 提取 ID，同一来源第二次只采集新数据。

### 输出格式

支持 `json`、`csv`、`jsonl`，文件路径支持 `{date}` / `{time}` 模板。

## 看板功能

- **7 步规则创建向导** — 表单填写 + YAML 直接编辑双模式
- **实时日志流** — SSE 推送采集进度，硬件监控窗口风格
- **Cron 调度** — 在看板中配置定时采集任务
- **数据预览** — 表格 + JSON 展开，按 subject / platform 筛选
- **任务历史** — 记录每次采集的执行结果

## 凭证管理

API Key 等敏感信息写入 `APP/engine/credentials.yaml`，不使用环境变量。

## 开发约束

- 收到编码任务必须先 `brainstorming` 澄清需求，再 `writing-plans` 输出计划
- 代码修改必须由 Claude Code 执行（禁止直接改代码）
- 完成后必须 `verification-before-completion` 验证
- 安装新依赖必须更新 README 和 requirements.txt
