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
  type: "api" | "html"  # api=调用API，html=解析HTML
  base_url: "https://..."  # API场景
  url: "https://..."       # HTML场景
  auth:
    type: "none" | "cookie" | "api_key" | "oauth"
    credential: "..."  # 环境变量引用或直接值

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
  path: "./output/"
  filename_template: "{date}.json"

alert:
  on_failure: true | false
  retry_times: 3
```

## 4. Key Classes

| Class | Responsibility |
|-------|----------------|
| `RuleParser` | 解析 YAML 规则文件，验证必填字段 |
| `Deduplicator` | SQLite 全局去重，管理 dedup.db |
| `APICrawler` | 处理 API 类型数据源 |
| `HTMLCrawler` | 处理 HTML 类型数据源，使用 XPath 解析 |
| `OutputManager` | 管理 JSON 输出 |
| `InfoCollectorEngine` | 核心引擎，协调各组件 |

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
| test_crawl_html.py | HTML 解析、XPath 提取 |

## 8. Implementation Tasks

| Task | Status |
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
