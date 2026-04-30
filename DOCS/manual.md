# info-collector 使用手册

## 目录

1. [快速开始](#1-快速开始)
2. [项目结构](#2-项目结构)
3. [虚拟环境与依赖](#3-虚拟环境与依赖)
4. [引擎使用指南](#4-引擎使用指南)
5. [CLI 命令行工具](#5-cli-命令行工具)
6. [YAML 规则配置详解](#6-yaml-规则配置详解)
7. [数据输出说明](#7-数据输出说明)
8. [状态管理（state.json）](#8-状态管理statejson)
9. [Dashboard 使用说明](#9-dashboard-使用说明)
10. [测试与调试](#10-测试与调试)
11. [注意事项与常见问题](#11-注意事项与常见问题)

---

## 1. 快速开始

### 1.1 环境要求

| 组件 | 要求 |
|------|------|
| Python | ≥ 3.10 |
| 内存 | ≥ 4GB（启用浏览器渲染时建议 8GB） |
| 网络 | 可访问外网 |

### 1.2 一步启动

```bash
cd /root/info-collector/APP/engine

# 首次：创建虚拟环境 + 安装依赖
./venv.sh create

# 查看所有可用命令
./venv.sh run python engine_cli.py --help

# 执行全部规则
./venv.sh run python engine_cli.py --run-all

# 查看采集状态
./venv.sh run python engine_cli.py --state
```

### 1.3 打开看板

```bash
# 用浏览器直接打开（或起一个 HTTP 服务）
firefox /root/info-collector/APP/dashboard/index.html
```

---

## 2. 项目结构

```
info-collector/
├── APP/
│   ├── engine/                      # 采集引擎
│   │   ├── engine_cli.py            # CLI 入口（强制 venv 检查）
│   │   ├── venv.sh                  # 虚拟环境管理脚本
│   │   ├── requirements.txt         # 依赖清单
│   │   ├── dedup.db                 # SQLite 全局去重数据库（自动生成）
│   │   ├── engine/
│   │   │   ├── engine.py            # 核心引擎（run / run_all）
│   │   │   ├── state.py             # 状态管理器（state.json）
│   │   │   ├── rule_parser.py       # YAML 规则解析
│   │   │   ├── dedup.py            # SQLite 全局去重
│   │   │   ├── output.py            # JSON 输出管理
│   │   │   ├── crawl_api.py         # API 采集
│   │   │   ├── crawl_html.py        # HTML 采集
│   │   │   └── crawl_browser.py     # 浏览器渲染采集（Playwright）
│   │   ├── rules/                   # YAML 采集规则
│   │   ├── output/                  # JSON 输出文件 + state.json
│   │   └── tests/                   # 单元测试
│   └── dashboard/
│       └── index.html               # 数据看板（纯 HTML/CSS/JS）
├── DOCS/
│   └── manual.md                    # 本手册
└── README.md
```

---

## 3. 虚拟环境与依赖

### 3.1 venv.sh 使用方法

```bash
./venv.sh create   # 创建虚拟环境 + 安装所有依赖（首次必选）
./venv.sh install  # 仅安装依赖（虚拟环境已存在时）
./venv.sh update   # 更新依赖（根据 requirements.txt）
./venv.sh clean    # 删除虚拟环境
./venv.sh run python engine_cli.py ...   # 在虚拟环境中执行命令
```

### 3.2 手动激活虚拟环境

```bash
source .venv/bin/activate   # 激活
deactivate                   # 退出
```

### 3.3 重要：必须使用虚拟环境

`engine_cli.py` 内置 venv 检查，非虚拟环境运行时会报错并提示正确用法：

```
ERROR: 请使用虚拟环境运行此脚本。
正确方式: ./venv.sh run python engine_cli.py [...]
```

### 3.4 依赖说明

| 依赖 | 用途 |
|------|------|
| `requests` / `httpx` | HTTP 请求 |
| `playwright` | 浏览器渲染采集 |
| `pyyaml` | YAML 规则解析 |
| `sqlalchemy` | SQLite 去重数据库 |
| `pytest*` | 测试框架 |

### 3.5 Playwright 浏览器安装

```bash
./venv.sh run python -m playwright install chromium
```

---

## 4. 引擎使用指南

### 4.1 基本架构

```
YAML 规则文件
     ↓ load_rule()
规则字典
     ↓ crawl()        ← APICrawler / HTMLCrawler / BrowserCrawler
原始数据列表
     ↓ deduplicate()  ← SQLite 全局去重
去重后数据
     ↓ save_output()   ← JSON 文件写入
output/*.json
     ↓
state.json 更新执行记录
```

### 4.2 Python API

```python
from engine.engine import InfoCollectorEngine

# 初始化（自动创建 .venv 之外的 dedup.db 和 output/）
engine = InfoCollectorEngine(
    dedup_db_path="./dedup.db",   # SQLite 去重数据库路径
    state_dir="./output",          # state.json 和 JSON 输出所在目录
)

# 方式一：一键运行（加载→采集→去重→输出，全自动）
result = engine.run("rules/tmtpost_data_articles.yaml")
# 返回:
# {
#   "status": "success",        # success | failed | skipped
#   "rule": "钛媒体 - 数据要素相关文章",
#   "collected": 13,
#   "dedup_filtered": 2,
#   "output_path": "./output/tmtpost/tmtpost_data_articles_20260501.json"
# }

# 方式二：批量运行（自动扫描 rules/ 目录执行所有已启用规则）
results = engine.run_all("./rules")

# 方式三：分步控制
rule = engine.load_rule("rules/cninfo_data_value_search.yaml")
items = engine.crawl(rule)
items, filtered = engine.deduplicate(items, rule)
output_path = engine.save_output(items, rule, filtered)
```

### 4.3 引擎类 API

```python
class InfoCollectorEngine:
    def __init__(self, dedup_db_path: str = "./dedup.db", state_dir: str = "./output")

    def load_rule(self, rule_path: str) -> dict
        """加载并验证 YAML 规则文件"""

    def crawl(self, rule: dict) -> list[dict]
        """根据 source.type 执行对应爬虫（api/html/browser）"""

    def deduplicate(self, items: list, rule: dict) -> tuple[list, int]
        """去重，返回 (过滤后列表, 被过滤数量)"""

    def save_output(self, items: list, rule: dict, dedup_filtered: int = 0) -> str
        """保存为 JSON，返回文件路径"""

    def run(self, rule_path: str) -> dict
        """完整流水线：加载→采集→去重→输出，同时更新 state.json"""

    def run_all(self, rules_dir: str = "./rules") -> list[dict]
        """扫描目录执行所有已启用 YAML 规则，返回结果列表"""
```

---

## 5. CLI 命令行工具

所有命令均通过 `./venv.sh run python engine_cli.py` 调用：

### 5.1 查看帮助

```bash
./venv.sh run python engine_cli.py --help
```

### 5.2 执行全部规则

```bash
./venv.sh run python engine_cli.py run-all
# 输出示例:
# ✅ 钛媒体 - 数据要素相关文章 | 采集: 13 | 去重过滤: 0
# ✅ 巨潮资讯 - 数据要素相关公告 | 采集: 5 | 去重过滤: 3
```

### 5.3 执行指定规则

```bash
./venv.sh run python engine_cli.py run "钛媒体 - 数据要素相关文章"
```

### 5.4 列出所有规则

```bash
./venv.sh run python engine_cli.py rules
# 输出示例:
# ✅ 钛媒体 - 数据要素相关文章 [钛媒体] <html>
# ✅ 巨潮资讯 - 数据要素相关公告 [巨潮资讯] <api>
```

### 5.5 查看采集状态

```bash
./venv.sh run python engine_cli.py state
# 输出: 全局统计 + 规则列表 + 最近执行记录 + 错误列表
```

### 5.6 扫描规则目录

```bash
./venv.sh run python engine_cli.py scan
# 将 rules/ 下所有 YAML 注册到 state.json
```

---

## 6. YAML 规则配置详解

### 6.1 完整字段说明

| 字段 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `name` | ✅ | 规则名称 | `"钛媒体文章采集"` |
| `version` | | 版本号 | `"1.0.0"` |
| `description` | | 规则描述 | `"追踪数据行业动态"` |
| `enabled` | | 是否启用（默认 true） | `false` |
| `source.platform` | ✅ | 平台标识 | `"tmtpost"` |
| `source.type` | ✅ | 来源类型 | `"api"` / `"html"` / `"browser"` |
| `source.url` | 看情况 | HTML/Browser 场景的 URL | `"https://..."` |
| `source.base_url` | 看情况 | API 场景的 base URL | `"https://..."` |
| `source.auth.type` | | 认证方式 | `"none"` / `"cookie"` / `"api_key"` / `"oauth"` |
| `render.enabled` | | 是否启用浏览器渲染 | `true` / `false` |
| `list.items_path` | ✅ | 数据项提取路径 | 见下方详解 |
| `list.fields` | ✅ | 字段提取规则 | 见下方详解 |
| `dedup.incremental` | | 增量采集开关（默认 true） | `true` |
| `dedup.id_template` | | 去重 ID 模板 | `"cninfo_{raw_id}"` |
| `dedup.url_to_id_pattern` | | 从 URL 提取 ID 的正则 | `"tmtpost\\.com/(\\d+)\\.html"` |
| `output.path` | | 输出目录 | `"./output/tmtpost/"` |
| `output.filename_template` | | 输出文件名模板 | `"tmtpost_{date}.json"` |

### 6.2 items_path 提取语法

#### API 类型（JSONPath）

```yaml
items_path: "$.announcements[*]"
# 提取 response.announcements 数组
```

#### HTML 类型（正则或 XPath）

```yaml
# 正则模式（推荐）：regex:前缀，提取分组
items_path: 'regex:<a[^>]*class="[^"]*item[^"]*type-post[^"]*"[^>]*href="([^"]+)"[^>]*>.*?<img[^>]*alt="([^"]+)"[^>]*>'

# XPath 简化模式（仅支持 class 匹配）
items_path: "//a[contains(@class,'item')]"
```

### 6.3 field 字段类型

| type | 说明 | 关键参数 |
|------|------|---------|
| `field` | 从 JSON/HTML 中提取字段 | `path`: JSONPath 或 XPath |
| `constant` | 固定常量值 | `value`: 常量值 |
| `computed` | 通过模板计算 | `value`: 模板字符串, `vars`: 变量映射 |
| `attr` | 提取 HTML 属性 | `path`: XPath, `attr`: 属性名 |
| `element_text` | 从解析出的元素取 text | 配合 regex 使用 |
| `element_href` | 从解析出的元素取 href | 配合 regex 使用 |

### 6.4 computed 模板示例

```yaml
# 从 announcementId 和 orgId 拼接完整 URL
- name: "url"
  type: "computed"
  value: "https://www.cninfo.com.cn/new/disclosure/detail?announcementId={announcementId}&orgId={orgId}"
  vars:
    announcementId: "$.announcementId"
    orgId: "$.orgId"
```

### 6.5 transform 转换函数

| 函数 | 适用场景 | 示例 |
|------|---------|------|
| `strip_html` | 去除 HTML 标签 | `"<em>数据</em>要素" → "数据要素"` |
| `trim` | 去除首尾空白 | `"  数据  " → "数据"` |
| `timestamp_ms_to_iso` | 毫秒时间戳转 ISO | `1714567890000` → `"2024-05-01T..."` |

### 6.6 完整规则示例（API 类型）

```yaml
name: "巨潮资讯 - 数据要素相关公告"
version: "1.0.0"
description: "从巨潮资讯网搜索数据要素相关上市公司公告"

source:
  platform: "cninfo"
  type: "api"
  base_url: "https://www.cninfo.com.cn/new/fulltextSearch/full"
  auth:
    type: "none"

request:
  method: "POST"
  headers:
    User-Agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    Content-Type: "application/x-www-form-urlencoded"
  body_template: |
    searchkey={keyword}&sdate=&edate=&isfulltext=false&sortName=pubdate&sortType=desc&plateCode=
  params:
    keyword: "数据要素"

list:
  items_path: "$.announcements[*]"
  fields:
    - name: "title"
      type: "field"
      path: "$.announcementTitle"
      transform: "strip_html"
    - name: "url"
      type: "computed"
      value: "https://www.cninfo.com.cn/new/disclosure/detail?announcementId={announcementId}&orgId={orgId}"
      vars:
        announcementId: "$.announcementId"
        orgId: "$.orgId"
    - name: "platform"
      type: "constant"
      value: "巨潮资讯"
    - name: "publish_time"
      type: "field"
      path: "$.announcementTime"
      transform: "timestamp_ms_to_iso"
    - name: "company"
      type: "field"
      path: "$.secName"
    - name: "clue_type"
      type: "computed"
      value: "policy"
    - name: "raw_id"
      type: "field"
      path: "$.announcementId"

dedup:
  incremental: true
  id_template: "cninfo_{raw_id}"

pagination:
  enabled: true
  page_param: "pageNum"
  max_pages: 10

output:
  format: "json"
  path: "./output/cninfo/"
  filename_template: "cninfo_data_value_{date}.json"
```

### 6.7 完整规则示例（HTML + 正则）

```yaml
name: "钛媒体 - 数据要素相关文章"
version: "1.0.2"
description: "从钛媒体官网抓取数据要素相关文章列表"

source:
  platform: "tmtpost"
  type: "html"
  url: "https://www.tmtpost.com/"
  auth:
    type: "none"

render:
  enabled: false  # SSR页面，无需渲染

list:
  items_path: 'regex:<a[^>]*class="[^"]*item[^"]*type-post[^"]*"[^>]*href="([^"]+)"[^>]*>.*?<img[^>]*alt="([^"]+)"[^>]*>'
  fields:
    - name: "title"
      type: "element_text"
    - name: "url"
      type: "element_href"
    - name: "platform"
      type: "constant"
      value: "钛媒体"
    - name: "clue_type"
      type: "constant"
      value: "policy"

dedup:
  incremental: true
  id_template: "tmtpost_{article_id}"
  url_to_id_pattern: "tmtpost\\.com/(\\d+)\\.html"

output:
  format: "json"
  path: "./output/tmtpost/"
  filename_template: "tmtpost_data_articles_{date}.json"
```

---

## 7. 数据输出说明

### 7.1 输出 JSON 结构

```json
{
  "meta": {
    "platform": "tmtpost",
    "collected_at": "2024-05-01T12:00:00",
    "count": 12,
    "dedup_filtered": 2
  },
  "data": [
    {
      "title": "文章标题",
      "url": "https://www.tmtpost.com/123456.html",
      "platform": "钛媒体",
      "clue_type": "policy",
      "publish_time": null,
      "company": null
    }
  ]
}
```

### 7.2 输出路径规则

- 路径由 `output.path` 指定（支持相对路径如 `./output/tmtpost/`）
- 文件名由 `output.filename_template` 指定，支持 `{date}` 占位符（格式为 `YYYYMMDD`）

### 7.3 线索类型

每条采集记录都带有 `clue_type` 字段，标识线索类型：

| 类型值 | 含义 |
|--------|------|
| `policy` | 政策 |
| `project` | 项目 |
| `transaction` | 交易 |
| `registration` | 登记 |
| `investment` | 投资 |

---

## 8. 状态管理（state.json）

### 8.1 状态文件位置

`output/state.json`，由 `StateManager` 自动维护。

### 8.2 状态文件结构

```json
{
  "rules": {
    "钛媒体 - 数据要素相关文章": {
      "name": "钛媒体 - 数据要素相关文章",
      "version": "1.0.2",
      "platform": "tmtpost",
      "source_type": "html",
      "enabled": true,
      "rule_path": "./rules/tmtpost_data_articles.yaml",
      "last_run_at": "2026-04-30T12:00:00",
      "last_run_status": "success",
      "last_collected": 13,
      "last_dedup_filtered": 0,
      "total_runs": 5,
      "total_collected": 62,
      "last_error": null
    }
  },
  "executions": [
    {
      "execution_id": "exec_20260430120000_钛媒体",
      "rule_name": "钛媒体 - 数据要素相关文章",
      "status": "success",
      "started_at": "2026-04-30T12:00:00",
      "finished_at": "2026-04-30T12:00:05",
      "duration_sec": 5.2,
      "collected": 13,
      "dedup_filtered": 0,
      "output_path": "./output/tmtpost/tmtpost_data_articles_20260430.json"
    }
  ],
  "errors": [
    {
      "rule_name": "巨潮资讯 - 数据要素相关公告",
      "error": "NetworkError: timeout",
      "occurred_at": "2026-04-30T11:00:00"
    }
  ],
  "stats": {
    "total_collected": 62,
    "total_runs": 5,
    "total_failed": 1
  }
}
```

### 8.3 自动注册规则

运行 `./venv.sh run python engine_cli.py scan` 会扫描 `rules/` 目录，自动将所有 YAML 规则注册到 `state.json`，无需手动管理。

---

## 9. Dashboard 使用说明

### 9.1 启动

```bash
# 直接用浏览器打开（无需 HTTP 服务）
firefox /root/info-collector/APP/dashboard/index.html

# 或起一个简单的 HTTP 服务
cd /root/info-collector/APP/dashboard
python3 -m http.server 8080
# 然后访问 http://localhost:8080
```

### 9.2 功能说明

Dashboard 读取 `output/state.json` 和 `output/*.json`，实时展示：

- **概览 Tab**：选中规则的 KPI（运行次数/累计采集/最近状态）+ 最近执行明细
- **执行记录 Tab**：全局最近 30 条执行记录一览
- **错误日志 Tab**：全局错误列表，含规则名 + 错误信息 + 时间
- **数据查看 Tab**：加载所有 output JSON，支持按平台 / 线索类型 / 关键词过滤

### 9.3 左规则列表

彩色状态点表示各规则最新状态：
- 🟢 绿色 = 最近一次成功
- 🔴 红色 = 最近一次失败
- 🟡 黄色 = 运行中
- ⚪ 灰色 = 待执行 / 已禁用

---

## 10. 测试与调试

### 10.1 运行单元测试

```bash
cd /root/info-collector/APP/engine

# 运行所有测试
./venv.sh run python -m pytest tests/ -v

# 运行单个测试文件
./venv.sh run python -m pytest tests/test_state.py -v

# 运行单个测试用例
./venv.sh run python -m pytest tests/test_state.py::TestStateManager::test_record_failure -v
```

### 10.2 测试覆盖范围

| 测试文件 | 覆盖内容 |
|---------|---------|
| `test_state.py` | StateManager 注册/执行/错误/统计 |
| `test_dedup.py` | SQLite 去重、增量过滤 |
| `test_rule_parser.py` | YAML 解析、字段验证 |
| `test_crawl_browser.py` | Playwright 浏览器采集 |
| `test_engine_dedup.py` | 引擎去重集成 |
| `test_integration.py` | 端到端采集流程 |

### 10.3 调试采集中间结果

```python
from engine.engine import InfoCollectorEngine

engine = InfoCollectorEngine()

# 分步调试
rule = engine.load_rule("rules/tmtpost_data_articles.yaml")
print("Rule loaded:", rule.get("name"))

items = engine.crawl(rule)
print(f"Crawled {len(items)} items, first item:", items[0] if items else "none")

items, filtered = engine.deduplicate(items, rule)
print(f"After dedup: {len(items)} items, filtered: {filtered}")
```

### 10.4 查看 state.json

```bash
cat /root/info-collector/APP/engine/output/state.json | python3 -m json.tool
```

---

## 11. 注意事项与常见问题

### 11.1 常见错误

**Q: `ModuleNotFoundError: No module named 'engine'`**
> 确保在虚拟环境中运行：`./venv.sh run python engine_cli.py ...`

**Q: 采集数量为 0**
> 检查网络连通性；检查 `items_path` 是否能匹配到内容；检查 `source.url` 是否可访问

**Q: state.json 不存在**
> 先运行一次采集：`./venv.sh run python engine_cli.py run-all`，或手动扫描：`./venv.sh run python engine_cli.py scan`

**Q: 去重后无新数据**
> 正常现象，说明上次采集的数据还未过期，无需重复采集。可删除 `dedup.db` 重新开始：`rm dedup.db`

### 11.2 安全提示

- API 密钥等凭证不要写在 YAML 规则中，建议写入 `credentials.yaml` 并在 `.gitignore` 中忽略
- 不要将 `dedup.db` 和 `output/` 目录提交到 Git

### 11.3 清理数据

```bash
# 清空去重记录（重新全量采集）
rm /root/info-collector/APP/engine/dedup.db

# 清空所有输出和状态（谨慎操作）
rm -rf /root/info-collector/APP/engine/output/*.json
rm -rf /root/info-collector/APP/engine/output/*/
```
