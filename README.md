# info-collector

数据要素价值化线索追踪系统 — 信息收集模块。

## 项目结构

```
info-collector/
├── APP/
│   ├── engine/          # 采集引擎（Python）
│   │   ├── engine/
│   │   │   ├── engine.py       # 核心引擎
│   │   │   ├── rule_parser.py  # YAML 规则解析
│   │   │   ├── dedup.py        # SQLite 全局去重
│   │   │   ├── state.py        # 状态管理（state.json）
│   │   │   ├── output.py       # JSON 输出管理
│   │   │   ├── crawl_api.py    # API 采集
│   │   │   ├── crawl_html.py   # HTML 采集
│   │   │   └── crawl_browser.py # 浏览器渲染采集（Playwright）
│   │   ├── rules/              # YAML 采集规则
│   │   ├── output/             # 采集输出（JSON + state.json）
│   │   ├── tests/
│   │   └── requirements.txt
│   └── dashboard/       # 数据看板（纯 HTML/CSS/JS）
│       └── index.html
├── DOCS/
│   └── manual.md        # 操作手册
└── .gitignore
```

## 快速开始

### 1. 安装依赖

```bash
cd APP/engine
pip install -r requirements.txt
playwright install chromium  # 仅首次，浏览器渲染模式需要
```

### 2. 配置规则

在 `rules/` 目录下创建 YAML 文件，参考现有规则格式。

### 3. 运行采集

```bash
python -c "from engine.engine import InfoCollectorEngine; e = InfoCollectorEngine(); e.run_all('./rules')"
```

### 4. 查看看板

直接用浏览器打开 `APP/dashboard/index.html`（需通过 HTTP 服务，或浏览器允许 file:// 访问）。

## 核心设计

- **规则驱动**：所有采集逻辑写在 YAML 规则文件中，与引擎解耦
- **增量采集**：SQLite 全局去重表，同一来源第二次只采新数据
- **状态持久化**：`output/state.json` 记录规则配置、执行历史、错误日志
- **多源采集**：支持 API / HTML / 浏览器渲染（Playwright）三种模式
- **凭证管理**：API Key 等凭证写入 `APP/engine/credentials.yaml`，不碰环境变量

## 线索类型

数据要素价值化线索分为 5 类：
- **政策**（policy）：政府/部门发布的数据要素相关政策
- **项目**（project）：招标/中标/建设数据要素相关项目
- **交易**（transaction）：数据产品挂牌/成交
- **登记**（registration）：数据资产登记/知识产权登记
- **投资**（investment）：数据要素相关投融资事件
