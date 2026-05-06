# info-collector

数据要素价值化线索追踪系统 — 信息收集模块。

## 项目结构

```
info-collector/
├── APP/
│   ├── engine/                      # 采集引擎（Python）
│   │   ├── engine_cli.py            # CLI 入口（强制 venv 检查）
│   │   ├── venv.sh                  # 虚拟环境管理脚本
│   │   ├── requirements.txt         # 依赖清单
│   │   ├── dedup.db                 # SQLite 去重数据库（自动生成）
│   │   ├── engine/                  # 核心代码包
│   │   │   ├── engine.py            # 核心引擎
│   │   │   ├── rule_parser.py       # YAML 规则解析
│   │   │   ├── dedup.py             # SQLite 全局去重
│   │   │   ├── state.py             # 状态管理
│   │   │   ├── output.py            # JSON 输出管理
│   │   │   ├── crawl_api.py         # API 采集（jsonpath-ng）
│   │   │   ├── crawl_html.py        # HTML 采集（parsel + lxml）
│   │   │   ├── crawl_browser.py    # 浏览器渲染采集（Playwright）
│   │   │   └── parsers/             # 统一解析层（HTMLParser / JSONParser / UA）
│   │   ├── rules/                   # YAML 采集规则
│   │   ├── output/                  # 采集输出（JSON）
│   │   ├── credentials.yaml          # API 凭证配置
│   │   └── tests/                   # 单元测试
│   └── dashboard/                   # 数据看板（Flask + Vue 3 CDN）
│       ├── server.py               # Flask 服务（端口 5000）
│       ├── index.html              # 看板前端
│       ├── apis/                   # REST API 蓝图
│       │   ├── rules_api.py        # 规则管理（CRUD）
│       │   ├── logs_api.py         # 实时日志流（SSE）
│       │   ├── tasks_api.py        # 手动触发采集
│       │   └── data_api.py         # 数据预览
│       └── dashboard.db            # 看板数据库（cron 调度 + 任务历史）
├── DOCS/
│   └── manual.md                    # 操作手册
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
source .venv/bin/activate        # Linux/macOS
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium       # 仅首次，browser 模式需要
```

> ⚠️ **必须使用虚拟环境**。直接用系统 Python 安装会导致依赖冲突。`engine_cli.py` 内置 venv 检查。

### 2. 启动看板（方式一：Flask 服务）

```bash
# 安装看板依赖
cd APP/dashboard
pip install -r requirements.txt

# 启动看板服务
python server.py
# 访问 http://localhost:5000
```

### 2. 启动看板（方式二：Docker）

```bash
cd APP/dashboard
docker build -t info-collector-dashboard .
docker run -p 5000:5000 info-collector-dashboard
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

## 看板功能

- **实时日志流**：SSE 推送采集进度，日志样式参考硬件监控窗口
- **规则管理**：表单向导 + YAML 编辑器，启用/禁用规则
- **Cron 调度**：在看板中配置定时采集，无需手动运行
- **数据预览**：表格 + JSON 展开，支持按 subject/platform 筛选
- **任务历史**：记录每次采集的执行结果

## 核心设计

- **规则驱动**：所有采集逻辑写在 YAML 规则文件中，与引擎解耦
- **增量采集**：SQLite 全局去重表，同一来源第二次只采新数据
- **状态持久化**：`output/state.json` 记录规则配置、执行历史、错误日志
- **多源采集**：支持 API / HTML / 浏览器渲染（Playwright）三种模式
- **UA 策略**：`source.client` 支持 `auto`（自动降级）/ `mobile` / `desktop` / `browser`
- **凭证管理**：API Key 等凭证写入 `credentials.yaml`，不碰环境变量

## 线索类型

数据要素价值化线索分为 5 类：
- **政策**（policy）：政府/部门发布的数据要素相关政策
- **项目**（project）：招标/中标/建设数据要素相关项目
- **交易**（transaction）：数据产品挂牌/成交
- **登记**（registration）：数据资产登记/知识产权登记
- **投资**（investment）：数据要素相关投融资事件
