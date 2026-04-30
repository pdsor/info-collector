# info-collector 使用手册

## 目录

1. [快速开始](#1-快速开始)
2. [系统架构](#2-系统架构)
3. [引擎使用指南](#3-引擎使用指南)
4. [YAML 规则配置详解](#4-yaml-规则配置详解)
5. [数据输出说明](#5-数据输出说明)
6. [去重机制](#6-去重机制)
7. [Dashboard 使用说明](#7-dashboard-使用说明)
8. [测试与调试](#8-测试与调试)
9. [注意事项与常见问题](#9-注意事项与常见问题)
10. [文件清单](#10-文件清单)

---

## 1. 快速开始

### 1.1 环境要求

| 组件 | 要求 |
|------|------|
| Python | ≥ 3.10 |
| 内存 | ≥ 4GB（启用浏览器渲染时建议 8GB） |
| 磁盘 | 至少 1GB 可用空间 |
| 网络 | 可访问外网 |

### 1.2 安装依赖

```bash
# 进入引擎目录
cd /root/info-collector/APP/engine

# 安装 Python 依赖（如需要）
pip install requests pyyaml playwright

# 安装 Playwright 浏览器（仅首次）
python -m playwright install chromium
```

### 1.3 运行第一个采集任务

```bash
cd /root/info-collector/APP/engine

# 方式一：直接运行（自动加载规则→采集→去重→输出）
python -c "
from engine import InfoCollectorEngine
engine = InfoCollectorEngine()
result = engine.run('rules/tmtpost_data_articles.yaml')
print(result)
"

# 方式二：指定规则文件运行
python -c "
from engine import InfoCollectorEngine
engine = InfoCollectorEngine()
result = engine.run('rules/cninfo_data_value_search.yaml')
print(result)
"
```

### 1.4 查看输出

```bash
# 查看输出目录
ls -la output/*/

# 查看最新数据（JSON）
cat output/combined/combined_latest.json
```

---

## 2. 系统架构

### 2.1 三层模块架构

```
┌─────────────────────────────────────────────────────────┐
│  模块一：信息收集定义           （YAML 规则文件）         │
│  - 定义采集目标、字段、平台、去重策略                    │
└────────────────────────┬────────────────────────────────┘
                         │ YAML
┌────────────────────────▼────────────────────────────────┐
│  模块二：采集程序引擎           （engine/）             │
│  - RuleParser        → 解析 YAML 规则                   │
│  - APICrawler       → API 来源数据抓取                 │
│  - HTMLCrawler      → HTML 来源数据抓取                 │
│  - BrowserCrawler   → JS 渲染页面抓取（Playwright）     │
│  - Deduplicator     → SQLite 全局去重                  │
│  - OutputManager    → JSON 输出管理                    │
└────────────────────────┬────────────────────────────────┘
                         │ JSON
┌────────────────────────▼────────────────────────────────┐
│  模块三：数据展示               （dashboard/）            │
│  - index.html        → 纯 HTML+CSS 看板                 │
│  - 支持规则/平台/线索类型三维筛选                       │
└─────────────────────────────────────────────────────────┘
```

### 2.2 数据流向

```
YAML 规则文件
     ↓ load_rule()
规则字典
     ↓ crawl()
原始数据列表
     ↓ deduplicate()
去重后数据
     ↓ save_output()
JSON 文件（output/）
```

---

## 3. 引擎使用指南

### 3.1 基本用法

```python
from engine import InfoCollectorEngine

# 初始化引擎（指定去重数据库路径）
engine = InfoCollectorEngine(dedup_db_path="./dedup.db")

# 方式一：一键运行（加载→采集→去重→输出，全自动）
result = engine.run("rules/tmtpost_data_articles.yaml")
# 返回: {'status': 'success', 'rule': '...', 'collected': N, 'dedup_filtered': M, 'output_path': '...'}

# 方式二：分步控制
rule = engine.load_rule("rules/tmtpost_data_articles.yaml")   # 加载规则
items = engine.crawl(rule)                                      # 采集数据
items, filtered = engine.deduplicate(items, rule)              # 去重
output_path = engine.save_output(items, rule, filtered)        # 保存
```

### 3.2 引擎类 API

```python
class InfoCollectorEngine:
    def __init__(self, dedup_db_path: str = "./dedup.db")
        """初始化引擎"""

    def load_rule(self, rule_path: str) -> dict
        """加载并验证 YAML 规则文件"""

    def crawl(self, rule: dict) -> list[dict]
        """根据 source.type 执行对应爬虫（api/html/browser）"""

    def deduplicate(self, items: list, rule: dict) -> tuple
        """去重，返回 (过滤后列表, 被过滤数量)"""

    def save_output(self, items: list, rule: dict, dedup_filtered: int = 0) -> str
        """保存为 JSON，返回文件路径"""

    def run(self, rule_path: str) -> dict
        """完整流水线：加载→采集→去重→输出"""
```

### 3.3 爬虫类

| 类 | 用途 | source.type |
|----|------|-------------|
| `APICrawler` | REST API 调用 | `api` |
| `HTMLCrawler` | 直接 HTML 抓取（requests） | `html` |
| `BrowserCrawler` | Playwright 无头浏览器（JS 渲染） | `browser` |

---

## 4. YAML 规则配置详解

### 4.1 完整字段说明

| 字段 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `name` | ✅ | 规则名称 | `"钛媒体文章采集"` |
| `version` | | 版本号 | `"1.0.0"` |
| `description` | | 规则描述 | `"追踪数据行业动态"` |
| `source.platform` | ✅ | 平台标识 | `"tmtpost"` |
| `source.type` | ✅ | 来源类型 | `"api` \| `html` \| `browser"` |
| `source.url` | 看情况 | HTML/Browser 场景的 URL | `"https://..."` |
| `source.base_url` | 看情况 | API 场景的 base URL | `"https://..."` |
| `source.auth.type` | | 认证方式 | `"none` \| `cookie` \| `api_key` \| `oauth"` |
| `source.auth.credential` | | 凭证（环境变量或直接值） | `"${COOKIE}"` 或 `"abc123"` |
| `render.enabled` | | 是否启用浏览器渲染 | `true` / `false` |
| `list.items_path` | ✅ | 数据项提取路径 | 见下方详解 |
| `list.fields` | ✅ | 字段提取规则 | 见下方详解 |
| `dedup.incremental` | | 增量采集开关 | `true`（默认） |
| `dedup.id_template` | | 去重 ID 模板 | `"cninfo_{raw_id}"` |
| `dedup.url_to_id_pattern` | | 从 URL 提取 ID 的正则 | `"tmtpost\\.com/(\\d+)\\.html"` |
| `output.path` | | 输出目录 | `"./output/tmtpost/"` |
| `output.filename_template` | | 输出文件名模板 | `"tmtpost_{date}.json"` |
| `alert.on_failure` | | 失败是否预警 | `true` |
| `alert.retry_times` | | 重试次数 | `3` |

### 4.2 items_path 提取语法

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

### 4.3 field 字段类型

| type | 说明 | 关键参数 |
|------|------|---------|
| `field` | 从 JSON/HTML 中提取字段 | `path`: JSONPath 或 XPath |
| `constant` | 固定常量值 | `value`: 常量值 |
| `computed` | 通过模板计算 | `value`: 模板字符串, `vars`: 变量映射 |
| `attr` | 提取 HTML 属性 | `path`: XPath, `attr`: 属性名 |
| `element_text` | 从解析出的元素取 text | 配合 regex 使用 |
| `element_href` | 从解析出的元素取 href | 配合 regex 使用 |

### 4.4 computed 模板示例

```yaml
# 从 announcementId 和 orgId 拼接完整 URL
- name: "url"
  type: "computed"
  value: "https://www.cninfo.com.cn/new/disclosure/detail?announcementId={announcementId}&orgId={orgId}"
  vars:
    announcementId: "$.announcementId"
    orgId: "$.orgId"
```

### 4.5 transform 转换函数

| 函数 | 适用场景 | 示例 |
|------|---------|------|
| `strip_html` | 去除 HTML 标签 | `"<em>数据</em>要素" → "数据要素"` |
| `trim` | 去除首尾空白 | `"  数据  "` → `"数据"` |
| `timestamp_ms_to_iso` | 毫秒时间戳转 ISO | `1714567890000` → `"2024-05-01T..."` |

### 4.6 完整规则示例（API 类型）

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

alert:
  on_failure: true
  retry_times: 3
```

### 4.7 完整规则示例（HTML + 正则）

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

alert:
  on_failure: true
  retry_times: 3
```

---

## 5. 数据输出说明

### 5.1 输出 JSON 结构

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
      "company": null,
      "summary": null
    }
  ]
}
```

### 5.2 输出路径规则

- 路径由 `output.path` 指定（支持相对路径如 `./output/tmtpost/`）
- 文件名由 `output.filename_template` 指定，支持 `{date}` 占位符
- `{date}` 格式为 `YYYYMMDD`

### 5.3 combined_latest.json

运行后，数据会同步合并到 `output/combined_latest.json`，方便 Dashboard 统一查看。

---

## 6. 去重机制

### 6.1 全局去重原理

- 使用 SQLite 数据库（`dedup.db`），所有规则共享
- 增量采集：同一来源第二次运行只采集新数据
- 跨来源去重：同一内容被多个来源采集时，只会输出一次

### 6.2 去重 ID 生成

```
id = id_template.format(raw_id=raw_id)
# 例: "cninfo_{announcementId}" → "cninfo_123456"
# 例: "tmtpost_{article_id}" → "tmtpost_789"
```

### 6.3 关闭去重

```yaml
dedup:
  incremental: false  # 关闭增量，每次全量采集
```

### 6.4 手动清空去重记录

```bash
# 删除去重数据库（下次运行会自动重建）
rm /root/info-collector/APP/engine/dedup.db
```

---

## 7. Dashboard 使用说明

### 7.1 启动

直接用浏览器打开 HTML 文件：

```bash
# Linux/macOS
firefox /root/info-collector/APP/dashboard/index.html
# 或
google-chrome /root/info-collector/APP/dashboard/index.html

# Windows
start index.html
```

### 7.2 功能

- **三维筛选**：按规则名称 / 平台 / 线索类型筛选数据
- **统计摘要**：显示总数、平台分布、线索类型分布
- **数据列表**：分页展示每条采集记录（标题、平台、时间、线索类型、来源 URL）
- **查看原文**：点击链接跳转原文页

### 7.3 数据加载

Dashboard 默认读取 `output/combined_latest.json`。

如需切换数据源，可修改 `index.html` 中第 1 行 `DATA_FILE` 常量。

---

## 8. 测试与调试

### 8.1 运行单元测试

```bash
cd /root/info-collector/APP/engine

# 运行所有测试
python -m pytest tests/ -v

# 运行单个测试文件
python -m pytest tests/test_rule_parser.py -v

# 运行单个测试用例
python -m pytest tests/test_rule_parser.py::TestRuleParser::test_load_valid_rule -v
```

### 8.2 测试覆盖范围

| 测试文件 | 覆盖内容 |
|---------|---------|
| `test_rule_parser.py` | YAML 解析、字段验证、items_path 解析 |
| `test_dedup.py` | SQLite 去重、增量过滤 |
| `test_output.py` | JSON 输出格式、文件名生成 |
| `test_crawl_api.py` | API 请求构建、JSON 解析、字段提取 |
| `test_crawl_html.py` | HTML 正则解析、属性提取 |

### 8.3 调试采集中间结果

```python
from engine import InfoCollectorEngine

engine = InfoCollectorEngine()

# 加载规则
rule = engine.load_rule("rules/tmtpost_data_articles.yaml")

# 只看采集结果（不保存，不去重）
items = engine.crawl(rule)
print(f"采集到 {len(items)} 条数据")
print(items[0] if items else "无数据")
```

### 8.4 调试 BrowserCrawler（无头浏览器）

```python
from engine.crawl_browser import BrowserCrawler

bc = BrowserCrawler()

# 抓取并截图（截图路径在返回值中）
html, screenshot = bc.fetch_with_screenshot("https://www.tmtpost.com/", {
    "headless": True,
    "wait_for_timeout": 5000
})
print(f"截图: {screenshot}")
print(f"HTML 长度: {len(html)}")

# 关闭浏览器
bc.close()
```

---

## 9. 注意事项与常见问题

### 9.1 注意事项

| 类别 | 说明 |
|------|------|
| **凭证安全** | 凭证直接写 YAML 文件（不推荐），建议使用环境变量引用 `${COOKIE}` |
| **增量采集** | 同一来源第二次运行自动跳过已采集数据，无需手动处理 |
| **去重范围** | 去重按 `requirement` 范围隔离，不同采集需求的去重记录互不影响 |
| **浏览器内存** | Playwright 浏览器渲染较耗内存，服务器建议 4核8G 以上 |
| **反爬策略** | 遇到 403/418 时：① 减少请求频率 ② 换 User-Agent ③ 启用 `render: enabled: true` |
| **日志规范** | 成功日志不含原始数据（数据量大），只记录来源、数量、耗时 |
| **输出覆盖** | 相同 `{date}` 的采集会覆盖同名文件，建议用 `combined_latest.json` 查看最新数据 |
| **YAML 格式** | YAML 中 `body_template` 使用 `|` 保留多行格式，否则 POST body 会变形 |

### 9.2 常见问题

**Q: 采集超时怎么办？**

- HTML: 检查网络连通性，确认 `curl <url>` 能正常返回
- API: 检查 `base_url`、`method`（GET/POST）是否正确
- Browser: 确认 Playwright chromium 已安装 (`python -m playwright install chromium`)

**Q: 数据为空？**

1. 确认 `items_path` 是否正确（API 用 JSONPath，HTML 用 regex）
2. 确认 `fields` 中的 `path` 是否与数据结构匹配
3. 加日志打印 raw_items，看是否提取到数据

**Q: 去重后数据全被过滤？**

- 说明之前已采集过这些数据（正常行为）
- 如需重新采集，删除 `dedup.db`

**Q: 浏览器渲染超时？**

- `BrowserCrawler.fetch()` 默认 15s 超时
- 可在 YAML 中调整 `render.wait_for_timeout`（毫秒）
- 某些网站有更强的反爬，可能需要引入代理池

**Q: 如何新增一个数据来源？**

1. 在 `rules/` 下新建 YAML 文件（如 `my_source.yaml`）
2. 参考示例规则，填写 `source`、`list`、`output` 等字段
3. 运行 `engine.run("rules/my_source.yaml")` 测试

**Q: 飞书/钉钉告警怎么接？**

当前版本仅支持日志记录。后续版本计划支持 Webhook 回调，由用户自行对接飞书/钉钉机器人。

---

## 10. 文件清单

```
info-collector/
├── DOCS/
│   ├── requirement-doc.md     # 需求文档（业务需求 + 技术规格）
│   ├── manual.md               # 本使用手册
│   └── SPEC.md                 # 技术规格（类接口、YAML schema）
│
├── APP/
│   ├── engine/                 # 采集引擎
│   │   ├── engine/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py       # 核心引擎类
│   │   │   ├── rule_parser.py  # YAML 规则解析器
│   │   │   ├── dedup.py        # SQLite 全局去重
│   │   │   ├── output.py       # JSON 输出管理器
│   │   │   ├── crawl_api.py    # API 采集器
│   │   │   ├── crawl_html.py   # HTML 采集器
│   │   │   └── crawl_browser.py # 浏览器采集器（Playwright）
│   │   ├── rules/              # YAML 规则文件目录
│   │   │   ├── cninfo_data_value_search.yaml  # 巨潮资讯规则
│   │   │   └── tmtpost_data_articles.yaml      # 钛媒体规则
│   │   ├── output/             # 采集输出目录
│   │   │   ├── cninfo/         # 巨潮资讯数据
│   │   │   ├── tmtpost/        # 钛媒体数据
│   │   │   └── combined_latest.json  # 合并数据
│   │   ├── dedup.db            # SQLite 去重数据库
│   │   ├── tests/              # 单元测试
│   │   │   ├── __init__.py
│   │   │   ├── test_rule_parser.py
│   │   │   ├── test_dedup.py
│   │   │   ├── test_output.py
│   │   │   ├── test_crawl_api.py
│   │   │   └── test_crawl_html.py
│   │   └── SPEC.md             # 技术规格
│   │
│   └── dashboard/              # Dashboard 看板
│       └── index.html          # 纯 HTML+CSS 数据展示页
│
└── .git/                       # Git 仓库
```

### 关键文件说明

| 文件 | 说明 |
|------|------|
| `engine/engine.py` | 核心引擎，入口类 `InfoCollectorEngine` |
| `engine/rule_parser.py` | YAML 规则解析与验证 |
| `engine/crawl_api.py` | API 采集，支持 POST/GET、JSONPath、transform |
| `engine/crawl_html.py` | HTML 采集，支持正则和 XPath 提取 |
| `engine/crawl_browser.py` | 浏览器采集，Playwright 封装，支持 headless + stealth |
| `engine/dedup.py` | SQLite 去重，按 `平台_raw_id` 全局去重 |
| `engine/output.py` | JSON 输出，含 meta 头（platform/time/count）|
| `rules/*.yaml` | 数据源规则定义，一个来源一个文件 |
| `dashboard/index.html` | 纯前端看板，无需构建直接打开 |
