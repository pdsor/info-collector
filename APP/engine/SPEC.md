# Info Collector Engine - Specification v1.0

## 1. Overview

通用信息采集引擎，通过加载 YAML 规则文件，适配不同来源的数据采集，支持增量采集、全局去重、JSON 输出。

## 2. Core Interfaces

### 2.1 Engine Class

```python
class InfoCollectorEngine:
    def __init__(self, dedup_db_path: str = "./dedup.db")
    def load_rule(self, rule_path: str) -> dict: ...
    def crawl(self, rule: dict) -> list[dict]: ...
    def deduplicate(self, items: list[dict], rule: dict) -> list[dict]: ...
    def save_output(self, items: list[dict], rule: dict) -> str: ...
    def run(self, rule_path: str) -> dict: ...
```

### 2.2 Data Flow

```
YAML Rule File → load_rule() → crawl() → deduplicate() → save_output() → JSON File
                      ↑              ↓
                      ←←←←←←←←←←←←←←←←
```

## 3. YAML Rule Schema

```yaml
name: "规则名称"
version: "1.0.0"
description: "规则描述"

source:
  platform: "平台标识"
  type: "api" | "html" | "browser"  # api=调用API，html=解析HTML，browser=Playwright渲染
  base_url: "https://..."  # API场景
  url: "https://..."       # HTML场景
  auth:
    type: "none" | "cookie" | "api_key" | "oauth"
    credential: "..."  # 环境变量引用或直接值

render:              # 仅 source.type=browser 时有效
  enabled: true      # 是否启用浏览器渲染
  headless: true     # 是否无头
  stealth: true      # 是否启用反检测
  wait_for_selector: null   # 等待元素选择器
  wait_for_timeout: 3000    # 等待超时（毫秒）

request:
  method: "GET" | "POST"
  headers: {}
  body_template: "..."  # POST body 模板
  params: {}            # URL 参数

list:
  items_path: "JSONPath 或 XPath"
  fields:
    - name: "字段名"
      type: "field" | "attr" | "xpath" | "computed" | "constant"
      path: "JSONPath 或 XPath"
      attr: "属性名"  # attr类型使用
      value: "常量值" # computed/constant类型
      vars: {}        # computed类型中的变量
      transform: "strip_html|timestamp_ms_to_iso|trim"  # 转换函数

detail:
  enabled: true | false
  fields: []  # 同 list.fields

dedup:
  incremental: true | false
  id_template: "平台_{raw_id}"  # ID 生成模板

pagination:
  enabled: true | false
  page_param: "pageNum"
  max_pages: 10

output:
  format: "json"
  path: "engine/data/"
  filename_template: "{date}.json"

alert:
  on_failure: true | false
  retry_times: 3
```

## 4. Key Classes

| Class | Responsibility | Source Type |
|-------|----------------|-------------|
| `RuleParser` | 解析 YAML 规则文件，验证必填字段 | — |
| `Deduplicator` | SQLite 全局去重，管理 dedup.db | — |
| `APICrawler` | 处理 API 类型数据源 | `api` |
| `HTMLCrawler` | 处理 HTML 类型数据源，使用正则/XPath 解析 | `html` |
| `BrowserCrawler` | 处理 JS 渲染页面，Playwright 无头浏览器 | `browser` |
| `OutputManager` | 管理 JSON 输出 | — |
| `InfoCollectorEngine` | 核心引擎，协调各组件 | — |

### 4.1 BrowserCrawler 配置参数

```python
render_config = {
    "headless": True,           # 是否无头（默认 True）
    "stealth": True,            # 是否启用反检测（默认 True）
    "user_agent": "random",     # "random" 或具体 UA 字符串
    "wait_for_selector": None,  # CSS 选择器，等待该元素出现
    "wait_for_timeout": 3000,   # 等待超时（毫秒）
    "viewport_width": 1920,
    "viewport_height": 1080,
    "extra_headers": {},         # 额外 HTTP 头
}
```

### 4.2 Source Type 路由规则

| source.type | Crawler | 依赖 |
|-------------|---------|------|
| `api` | `APICrawler` | requests |
| `html` | `HTMLCrawler` | requests |
| `browser` | `BrowserCrawler` | playwright + chromium |

## 5. Deduplication Schema

### SQLite Table: dedup

```sql
CREATE TABLE dedup (
    id TEXT PRIMARY KEY,
    requirement TEXT NOT NULL,
    platform TEXT NOT NULL,
    url TEXT,
    collected_at TEXT NOT NULL,
    raw_id TEXT
);
CREATE INDEX idx_requirement ON dedup(requirement);
CREATE INDEX idx_platform ON dedup(platform);
```

### ID Generation

```
id = id_template.format(raw_id=raw_id)
# 例: cninfo_{announcementId} → cninfo_123456
```

## 6. JSON Output Schema

```json
{
  "meta": {
    "platform": "平台名",
    "collected_at": "ISO时间",
    "count": 10,
    "dedup_filtered": 5
  },
  "data": [...]
}
```

## 7. Test Plan

| Test File | Coverage |
|-----------|----------|
| test_rule_parser.py | YAML 解析、字段验证、路径解析 |
| test_dedup.py | SQLite 去重、增量过滤 |
| test_output.py | JSON 输出格式化 |
| test_crawl_api.py | API 请求、响应解析、分页 |
| test_crawl_html.py | HTML 解析、正则/XPath 提取 |
| test_crawl_browser.py | Playwright 渲染、UA 随机化、正则解析 |

## 8. Implementation Tasks

|| Task | Status ||
|------|--------|
| 创建项目目录结构 | ✅ |
| 编写 SPEC.md | ✅ |
| 实现 RuleParser | ✅ |
| 实现 Deduplicator | ✅ |
| 实现 APICrawler | ✅ |
| 实现 HTMLCrawler | ✅ |
| 实现 OutputManager | ✅ |
| 实现 InfoCollectorEngine | ✅ |
| 编写测试用例 | ✅ |
| 验证 YAML 规则文件 | ✅ |

## 9. JSONL Event Stream Protocol (v2.0)

`engine_cli run-rule --format=jsonl` 和 `run-all --format=jsonl` 输出以下 JSONL 行，每行一个 JSON 对象：

| event.type | 触发时机 | 关键字段 |
|-----------|---------|---------|
| `start` | 规则开始执行 | `rule`, `ts` |
| `status` | 阶段变化 | `rule`, `status`, `msg`, `ts` |
| `item` | 每条采集结果（仅调试模式） | `rule`, `data`, `ts` |
| `progress` | 分页/列表进度 | `rule`, `phase`, `current`, `total`, `ts` |
| `error` | 采集异常 | `rule`, `message`, `detail`, `ts` |
| `skip` | 规则跳过 | `rule`, `reason`, `ts` |
| `complete` | 单规则完成 | `rule`, `new_count`, `skip_count`, `duration`, `ts` |
| `summary` | 全部规则汇总（仅 run-all） | `total_rules`, `total_new`, `total_skip`, `total_error`, `duration`, `ts` |

> 注意：`engine_cli run-rule --format=json`（旧模式）仍返回结构化 JSON 结果，用于向后兼容。

## 10. Dashboard Task System

### 10.1 Task Lifecycle

```
POST /api/tasks/run-all           POST /api/tasks/run-single/<path>    Cron trigger
        │                                    │                              │
        └────────── trigger_task() ──────────┘                              │
                    │                                                     │
                    ├── 写入 task_history (status=running)                  │
                    ├── 启动后台线程执行 engine_cli --format=jsonl          │
                    ├── 返回 task_id  ──────────────────────────────────→ │
                    │                                                     │
              SSE /api/tasks/stream/<task_id>  ←订阅────────────────────────┘
                    │
                    ├── engine_cli stdout 逐行 JSONL 解析
                    ├── 写入 task_history (status, new_count, duration)
                    └── 完成时 status=running→completed/failed
```

### 10.2 Database Schema

**task_history 表**（由 migration 002_task_enhance.sql 创建）：

```sql
CREATE TABLE task_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name   TEXT    NOT NULL,
    status      TEXT    DEFAULT 'running',   -- running|completed|failed
    new_count   INTEGER,
    skip_count  INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    duration    REAL,
    created_at  TEXT    DEFAULT (datetime('now', 'localtime')),
    finished_at TEXT,
    trigger_type TEXT   DEFAULT 'manual',     -- manual|cron|api
    rule_path   TEXT                              -- 单规则执行为规则路径
);
```

### 10.3 Dashboard API Endpoints

|| Method | Path | 描述 |
|--------|-------|------|
| `GET` | `/api/tasks/history` | 查询任务历史（分页） |
| `POST` | `/api/tasks/run-all` | 触发全量执行，返回 `{task_id}` |
| `POST` | `/api/tasks/run-single/<path>` | 触发单规则执行，返回 `{task_id}` |
| `GET` | `/api/tasks/stream/<task_id>` | **SSE** 事件流订阅 |

### 10.4 SSE Event Flow

1. 客户端 `GET /api/tasks/stream/<task_id>`
2. 服务端立即返回 `text/event-stream` 响应头
3. 后台线程执行 `engine_cli --format=jsonl`，stdout 逐行写入 SSE
4. 服务端按 event type 转发：`data: {"type":"...","..."}\n\n`
5. 任务结束时发送 `event: done\ndata: {...}\n\n`，客户端关闭连接
6. 心跳（每 15s）：`event: heartbeat\ndata: {}\n\n`

### 10.5 Cron Integration

`cron_api.py` 在 APScheduler `run_job` 回调中调用 `trigger_task()`，由 `TaskExecutor` 统一处理异步执行链：记录 task_history → 执行 engine_cli → 通过 SSE 推送事件 → 更新 task_history 状态。
