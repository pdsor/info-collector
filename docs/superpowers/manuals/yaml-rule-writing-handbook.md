# info-collector YAML 规则编写手册

> 本手册覆盖 info-collector 引擎全部 YAML 参数，基于代码源码编写，版本对应 Crawl4AI 集成完成后的最新状态。

---

## 目录

1. [快速开始](#1-快速开始)
2. [顶层字段](#2-顶层字段)
3. [source 数据源配置](#3-source-数据源配置)
4. [request HTTP 请求配置](#4-request-http-请求配置)
5. [list 列表提取配置](#5-list-列表提取配置)
6. [detail 详情页配置](#6-detail-详情页配置)
7. [render 浏览器渲染配置](#7-render-浏览器渲染配置)
8. [pagination 分页配置](#8-pagination-分页配置)
9. [dedup 去重配置](#9-dedup-去重配置)
10. [output 输出配置](#10-output-输出配置)
11. [schedule 调度配置](#11-schedule-调度配置)
12. [source.extraction LLM 提取配置](#12-sourceextraction-llm-提取配置)
13. [完整示例](#13-完整示例)
14. [字段速查表](#14-字段速查表)

---

## 1. 快速开始

### 最小规则

```yaml
name: 我的规则
source:
  platform: myplatform
  type: html
  url: https://example.com
list:
  items_path: css:.item
  fields:
    - name: title
      type: element_text
    - name: url
      type: element_href
```

### 三种数据源类型

| type | 说明 | 适用场景 |
|------|------|----------|
| `html` | 直接请求 HTML，适用于 SSR 页面 | 新闻列表、静态页面 |
| `api` | 发送 HTTP 请求解析 JSON | 官方 API、JSON 接口 |
| `browser` | 浏览器渲染（JS 动态加载） | React/Vue SPA、反爬强的页面 |

---

## 2. 顶层字段

```yaml
name: "规则名称"           # 必填，规则唯一标识，用于日志和状态记录
subject: "数据要素"        # 强烈建议，用于输出目录结构 engine/data/{subject}/
version: "1.0.0"          # 可选，版本号
description: "描述..."    # 可选，说明规则用途
enabled: true             # 可选，默认为 true；设为 false 则跳过执行
```

**优先级**：`subject` 字段可放在顶层，也可以放在 `source` 层级下（`source.subject`），顶层优先。

---

## 3. source 数据源配置

```yaml
source:
  platform: "cninfo"              # 必填，数据平台标识
  type: "html"                    # 必填，数据源类型：html | api | browser
  subject: "数据要素"             # 可选，归属主题（也可放顶层）
  url: "https://..."              # type=html 或 type=browser 时必填
  base_url: "https://..."         # type=api 时必填，API 端点
  client: "auto"                  # 可选，UA 客户端策略
  enabled: true                   # 可选，默认为 true；设为 false 跳过
  auth:                           # 可选，认证配置
    type: "none"                  # 目前仅支持 none
  extraction:                     # 可选，LLM 提取配置（详见第 12 节）
    enabled: false
```

### client UA 客户端策略

| 值 | 说明 | 适用场景 |
|----|------|----------|
| `auto` | 先用桌面 UA，若页面 < 5KB 则切换移动 UA | 响应式页面，优先桌面内容 |
| `mobile` | 强制使用移动端 User-Agent | 移动端专属页面 |
| `desktop` | 强制使用桌面端 User-Agent | PC 端页面 |
| `browser` | 走浏览器渲染（Playwright/Crawl4AI），UA 由渲染引擎控制 | JS 动态加载页面 |
| `crawl4ai` | 强制使用 Crawl4AI 渲染引擎（支持 LLM 提取） | 需要 LLM 提取的场景 |

> **注意**：`client` 字段也可以放在**顶层**，优先级：`rule.client` > `source.client`。

### type 与 client 组合效果

| source.type | client | 实际爬虫 |
|-------------|--------|----------|
| `html` | `desktop/mobile/auto` | HTMLCrawler（requests） |
| `html` | `browser` | BrowserCrawler（Playwright） |
| `html` | `crawl4ai` | BrowserCrawler（Crawl4AI） |
| `api` | 任意 | APICrawler |
| `browser` | 任意 | BrowserCrawler |

---

## 4. request HTTP 请求配置

> 仅 `source.type: api` 或 `source.type: html`（非 browser）时使用。

```yaml
request:
  method: "GET"                   # HTTP 方法：GET | POST
  headers:                        # 请求头
    User-Agent: "Mozilla/5.0 ..."
    Content-Type: "application/json"
  body_template: |                # POST 请求体，支持 {变量名} 占位符
    {"keyword": "{keyword}"}
  params:                         # 替换 body_template 中 {变量名} 的实际值
    keyword: "数据要素"
```

### body_template 变量替换

`body_template` 中的 `{变量名}` 会被 `params` 中对应键值替换。

```yaml
# 示例：POST body 中替换关键词
body_template: |
  searchkey={keyword}&sdate=&edate=&isfulltext=false
params:
  keyword: "数据要素"
```

---

## 5. list 列表提取配置

```yaml
list:
  items_path: "css:.article-item"  # 必填，列表项选择器
  fields:                           # 必填，字段提取规则
    - name: "title"
      type: "element_text"
    - name: "url"
      type: "element_href"
```

### items_path 选择器格式

| 格式 | 示例 | 说明 |
|------|------|------|
| `css:<selector>` | `css:.item a` | CSS 选择器，返回匹配元素的 href 和 text |
| `xpath:<expr>` | `xpath://div[@class="item"]//a` | XPath 表达式，返回 href 和 text |
| `regex:<pattern>` | `regex:<a[^>]*href="([^"]+)"[^>]*>([^<]+)` | 正则带分组，返回 href 和 title |
| `//tag[@class='name']` | `//a[@class='item']` | 旧式 XPath（仅支持简单 class 匹配） |

### field 字段类型（通用）

| type | 说明 | 必需字段 |
|------|------|----------|
| `constant` | 固定值 | `value` |
| `computed` | 模板计算值，支持 `{变量名}` 替换 | `value`, `vars` |
| `field` | 从 API JSON 中取字段（仅 API 类型） | `path` |
| `attr` | 从 HTML 元素取属性（HTML/browser 类型） | `path`, `attr` |
| `xpath` | XPath 提取文本（HTML/browser 类型） | `path` |
| `element_text` | 从 parse_items 返回的元素中取 text | — |
| `element_href` | 从 parse_items 返回的元素中取 href | — |

### field.type: field（API JSON 提取）

```yaml
- name: "title"
  type: "field"
  path: "$.announcementTitle"      # JSONPath 格式，$ 表示根
  transform: "strip_html"          # 可选，对值做变换
```

**transform 变换函数**（可组合，用逗号分隔）：

| 值 | 说明 |
|----|------|
| `strip_html` | 去除 HTML 标签 |
| `trim` | 去除首尾空白 |
| `timestamp_ms_to_iso` | 毫秒时间戳 → ISO 格式字符串 |

```yaml
# 示例：提取时间戳字段并转换
- name: "publish_time"
  type: "field"
  path: "$.announcementTime"
  transform: "timestamp_ms_to_iso"
```

### field.type: computed（模板计算）

将其他字段值嵌入模板字符串：

```yaml
- name: "url"
  type: "computed"
  value: "https://www.cninfo.com.cn/new/disclosure/detail?announcementId={announcementId}&orgId={orgId}"
  vars:
    announcementId: "$.announcementId"
    orgId: "$.orgId"
```

### field.type: attr（HTML 属性提取）

```yaml
- name: "image"
  type: "attr"
  path: "xpath://div[@class='cover']//img"
  attr: "src"                       # 默认为 "href"
```

### field.type: xpath（XPath 文本提取）

```yaml
- name: "content"
  type: "xpath"
  path: "xpath://div[@class='article-content']//text()"
```

### field.type: element_text / element_href

`items_path` 返回的元素（如 `css:.item`）自带 `href` 和 `title`/`text` 字段时使用：

```yaml
# items_path: css:.item → 返回 [{"href": "...", "title": "..."}]
- name: "title"
  type: "element_text"              # 取 title 字段
- name: "url"
  type: "element_href"              # 取 href 字段
```

---

## 6. detail 详情页配置

用于在列表页提取之后，再请求每个详情页抓取更多信息。当前实现为**预留字段**（`detail.enabled: false` 生效），暂无独立详情页爬取逻辑。

```yaml
detail:
  enabled: false                    # 目前固定 false，详情页逻辑待实现
```

---

## 7. render 浏览器渲染配置

> 仅 `source.type: browser` 或 `client: browser/crawl4ai` 时生效。

```yaml
render:
  enabled: true                     # 是否启用浏览器渲染（默认 false）
  headless: true                    # 是否无头模式，默认 true
  stealth: true                      # 是否启用反爬规避（修改 navigator.webdriver 等），默认 true
  user_agent: "random"              # User-Agent：字符串或 "random"（随机从内置列表选）
  wait_for_selector: ".main-content" # CSS 选择器，等待该元素出现后再抓取
  wait_for_timeout: 5000            # 等待超时（毫秒），默认 3000
  viewport_width: 1920              # 视口宽度，默认 1920
  viewport_height: 1080             # 视口高度，默认 1080
  markdown: true                    # 仅 crawl4ai：返回 Markdown 而非 HTML，默认 true
  remove_forms: false               # 仅 crawl4ai：移除表单元素，默认 false
  extra_headers:                    # 额外 HTTP 头
    Referer: "https://example.com"
```

### Playwright vs Crawl4AI 支持差异

| 配置项 | Playwright | Crawl4AI |
|--------|--------|--------|
| `headless` | ✅ | ✅ |
| `stealth` | ✅ | ✅（`enable_stealth`） |
| `anti_bot` | — | ✅（`stealth` 的别名） |
| `user_agent` | ✅ | ✅ |
| `wait_for_selector` | ✅ | ✅ |
| `wait_for_timeout` | ✅ | ✅ |
| `viewport_width/height` | ✅ | ✅ |
| `markdown` | — | ✅ |
| `remove_forms` | — | ✅ |
| `extra_headers` | ✅ | — |

---

## 8. pagination 分页配置

> 仅 `source.type: api` 时，分页在请求体中替换页码参数。

```yaml
pagination:
  enabled: true                     # 是否启用分页，默认 false
  page_param: "pageNum"             # POST body 中的页码参数名
  max_pages: 10                     # 最大页数，默认 10
```

分页逻辑：遍历第 1~max_pages 页，每次请求将 body 中的 `{page_param}={n}` 替换为当前页码。当某页返回空数据时中断。

---

## 9. dedup 去重配置

```yaml
dedup:
  incremental: true                 # 是否启用增量去重，默认 false（true 时才真正去重）
  id_template: "cninfo_{raw_id}"    # 可选，全局去重 ID 模板（目前未使用）
  url_to_id_pattern: "tmtpost\\.com/(\\d+)\\.html"  # 从 URL 提取 raw_id 的正则
```

### url_to_id_pattern 工作原理

1. 用正则从 `url` 字段提取 `raw_id`（第一个捕获组）
2. 存入 SQLite 去重数据库
3. 相同 `requirement` + `platform` + `raw_id` 的记录会被下次运行过滤掉

---

## 10. output 输出配置

```yaml
output:
  format: "json"                                    # 输出格式，目前仅支持 json
  path: "engine/data/数据要素/cninfo"                # 可选，自定义输出路径（绝对或相对）
  filename_template: "cninfo_data_value_{date}.json"  # 文件名模板，{date} 替换为 YYYYMMDD
```

**输出路径规则**：
- 若指定 `path`：输出到 `{path}`
- 若未指定 `path`：输出到 `engine/data/{subject}/{platform}/data_{date}.json`
- 同时生成 `engine/data/{subject}/combined_latest.json`（汇总所有平台最新数据）

---

## 11. schedule 调度配置

> 由 Dashboard 的 APScheduler 调度执行，规则 YAML 中声明式配置，server.py 负责解析。

```yaml
schedule:
  cron: "0 8 * * *"              # 标准 cron 表达式
  interval: null                 # 或者使用间隔，如 "30m"、"2h"（二选一）
  enabled: true                  # 是否启用调度
```

Dashboard 读取规则文件中的 `schedule` 字段，在数据库中创建对应的 cron 任务。

---

## 12. source.extraction LLM 提取配置

> 仅 `client: crawl4ai` 时可用（Playwright 不支持 LLM 提取）。

当 `source.extraction.enabled: true` 时，引擎跳过传统的 `items_path` + `fields` 解析，直接用 LLM 从页面内容中提取结构化数据。

```yaml
source:
  platform: "example"
  type: "browser"
  client: "crawl4ai"
  url: "https://example.com/article"
  extraction:
    enabled: true
    prompt: "从文章页面提取：标题、作者、发布时间、正文内容"
    strategy: "llm"               # 提取策略：llm（默认）| cosine
    schema:                       # 可选，结构化提取 schema（Pydantic 风格 dict）
      type: "object"
      properties:
        title:
          type: "string"
        author:
          type: "string"
        content:
          type: "string"
      required: ["title", "content"]
```

### extraction.schema 示例

```yaml
extraction:
  enabled: true
  prompt: |
    请从以下文章中提取结构化信息：
    1. 文章标题
    2. 作者名称
    3. 发布日期（ISO 格式）
    4. 文章正文（纯文本，去除 HTML）
  strategy: "llm"
  schema:
    type: "object"
    properties:
      title:
        type: "string"
        description: "文章标题"
      author:
        type: "string"
        description: "作者名称"
      publish_date:
        type: "string"
        description: "发布日期，ISO 格式"
      content:
        type: "string"
        description: "文章正文"
    required: ["title", "content"]
```

### extraction.strategy

| 值 | 说明 |
|----|------|
| `llm`（默认） | LLM 语义提取，根据 prompt + schema 提取 |
| `cosine` | 余弦相似度语义过滤，根据 schema 的 model_name 等参数过滤相关内容 |

---

## 13. 完整示例

### 示例一：API 类型（巨潮资讯）

```yaml
name: "巨潮资讯 - 数据要素相关公告"
subject: "数据要素"
version: "1.0.0"
description: "从巨潮资讯网搜索数据要素相关上市公司公告"
enabled: true

source:
  platform: "cninfo"
  type: "api"
  subject: "数据要素"
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
      type: "constant"
      value: "policy"
    - name: "raw_id"
      type: "field"
      path: "$.announcementId"
    - name: "org_id"
      type: "field"
      path: "$.orgId"

dedup:
  incremental: true
  id_template: "cninfo_{raw_id}"

pagination:
  enabled: true
  page_param: "pageNum"
  max_pages: 10

output:
  format: "json"
  filename_template: "cninfo_data_value_{date}.json"

alert:
  on_failure: true
  retry_times: 3
```

### 示例二：HTML 类型（钛媒体）

```yaml
name: "钛媒体 - 数据要素相关文章"
subject: "数据要素"
version: "1.0.2"
description: "从钛媒体官网抓取数据要素相关文章列表"
enabled: true

source:
  platform: "tmtpost"
  type: "html"
  client: "auto"
  subject: "数据要素"
  url: "https://www.tmtpost.com/"
  auth:
    type: "none"

render:
  enabled: false                   # SSR 页面，无需 JS 渲染

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
    - name: "publish_time"
      type: "constant"
      value: null
    - name: "company"
      type: "constant"
      value: null
    - name: "clue_type"
      type: "constant"
      value: "policy"
    - name: "summary"
      type: "constant"
      value: null

detail:
  enabled: false

dedup:
  incremental: true
  id_template: "tmtpost_{article_id}"
  url_to_id_pattern: "tmtpost\\.com/(\\d+)\\.html"

output:
  format: "json"
  filename_template: "tmtpost_data_articles_{date}.json"

alert:
  on_failure: true
  retry_times: 3
```

### 示例三：Browser + Crawl4AI + LLM 提取

```yaml
name: "财经网站 - LLM 提取示例"
subject: "金融数据"
version: "1.0.0"
enabled: true

source:
  platform: "finance"
  type: "browser"
  client: "crawl4ai"
  url: "https://example.com/article/12345"
  extraction:
    enabled: true
    prompt: |
      从这篇文章中提取：
      - 标题
      - 作者
      - 发布日期
      - 正文内容（纯文本）
    strategy: "llm"
    schema:
      type: "object"
      properties:
        title: {type: "string"}
        author: {type: "string"}
        publish_date: {type: "string"}
        content: {type: "string"}
      required: ["title", "content"]

render:
  headless: true
  stealth: true
  wait_for_selector: "article"
  wait_for_timeout: 5000
  markdown: true

dedup:
  incremental: true
  url_to_id_pattern: "example\\.com/article/(\\d+)"

output:
  format: "json"
  filename_template: "finance_articles_{date}.json"
```

### 示例四：Browser + CSS 选择器（非 LLM）

```yaml
name: "新闻网站 - Browser + CSS"
subject: "新闻"
version: "1.0.0"
enabled: true

source:
  platform: "news"
  type: "browser"
  client: "crawl4ai"               # 使用 Crawl4AI（也可用 "browser"走 Playwright）
  url: "https://news.example.com/tech"

render:
  headless: true
  stealth: true
  wait_for_selector: ".article-list"
  wait_for_timeout: 5000
  markdown: true                   # 返回 Markdown，用 CSS 选择器解析

list:
  items_path: "css:.article-item"  # 匹配 <div class="article-item">...
  fields:
    - name: "title"
      type: "element_text"         # 取元素内的文本
    - name: "url"
      type: "element_href"          # 取 <a> 的 href
    - name: "platform"
      type: "constant"
      value: "示例新闻"

dedup:
  incremental: true
  url_to_id_pattern: "news\\.example\\.com/(\\d+)"

output:
  format: "json"
  filename_template: "news_tech_{date}.json"
```

---

## 14. 字段速查表

### 顶层

| 字段 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `name` | ✅ | string | 规则名称 |
| `subject` | 建议 | string | 数据主题（决定输出目录） |
| `version` | | string | 版本号 |
| `description` | | string | 规则描述 |
| `enabled` | | bool | 是否启用，默认 true |
| `client` | | string | UA 策略（顶层覆盖），见 source.client |

### source

| 字段 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `platform` | ✅ | string | 平台标识 |
| `type` | ✅ | string | `html` \| `api` \| `browser` |
| `subject` | | string | 主题（可放顶层） |
| `url` | △ | string | 列表页 URL（type=html/browser） |
| `base_url` | △ | string | API 端点（type=api） |
| `client` | | string | UA 策略：`auto` \| `mobile` \| `desktop` \| `browser` \| `crawl4ai` |
| `enabled` | | bool | 是否启用 |
| `auth.type` | | string | 认证类型，目前仅 `none` |
| `extraction` | | dict | LLM 提取配置 |

### request（api 类型）

| 字段 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `method` | | string | `GET` \| `POST`，默认 GET |
| `headers` | | dict | HTTP 请求头 |
| `body_template` | | string | POST 请求体，支持 `{变量}` 占位 |
| `params` | | dict | 替换 body_template 中的变量 |

### list

| 字段 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `items_path` | ✅ | string | 列表项选择器 |
| `fields` | ✅ | list | 字段提取规则 |

### field

| type | 必需字段 |
|------|----------|
| `constant` | `value` |
| `computed` | `value`, `vars` |
| `field` | `path` |
| `attr` | `path`, `attr` |
| `xpath` | `path` |
| `element_text` | — |
| `element_href` | — |

### render

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | false | 启用浏览器渲染 |
| `headless` | bool | true | 无头模式 |
| `stealth` | bool | true | 反爬规避 |
| `user_agent` | string | `"random"` | UA |
| `wait_for_selector` | string | — | 等待元素 |
| `wait_for_timeout` | int | 3000 | 等待超时（ms） |
| `viewport_width` | int | 1920 | 视口宽度 |
| `viewport_height` | int | 1080 | 视口高度 |
| `markdown` | bool | true | 仅 crawl4ai：返回 Markdown |
| `remove_forms` | bool | false | 仅 crawl4ai：移除表单 |

### pagination（api 类型）

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `enabled` | false | 启用分页 |
| `page_param` | `"pageNum"` | 页码参数名 |
| `max_pages` | 10 | 最大页数 |

### dedup

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `incremental` | false | 启用增量去重 |
| `id_template` | — | 全局去重 ID 模板 |
| `url_to_id_pattern` | — | 从 URL 提取 raw_id 的正则 |

### output

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `format` | `"json"` | 输出格式 |
| `path` | — | 自定义输出路径 |
| `filename_template` | `"data_{date}.json"` | 文件名模板 |

### schedule

| 字段 | 说明 |
|------|------|
| `cron` | 标准 cron 表达式，与 interval 二选一 |
| `interval` | 间隔表达式，如 `"30m"`、`"2h"` |
| `enabled` | 是否启用调度 |

### source.extraction

| 字段 | 必填 | 说明 |
|------|------|------|
| `enabled` | ✅ | 是否启用 LLM 提取 |
| `prompt` | ✅（enabled=true） | LLM 提取指令 |
| `strategy` | | `llm`（默认）\| `cosine` |
| `schema` | | Pydantic 风格结构化 schema dict |
