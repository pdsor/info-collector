# YAML 规则编写手册

本文档是当前项目的 YAML 规则编写基准。新规则统一使用 Rule v2；旧格式仅用于维护已有规则和迁移参考。

手册内容以当前代码为准，主要对应以下实现：

- `APP/engine/engine/rule_parser.py`：读取和校验规则。
- `APP/engine/engine/engine.py`：按规则选择 API、HTML 或浏览器采集链路。
- `APP/engine/engine/crawl_api.py`：API 请求、分页、JSONPath 字段提取。
- `APP/engine/engine/crawl_html.py`：静态 HTML 请求和列表解析。
- `APP/engine/engine/crawl_browser.py`：浏览器渲染采集入口。
- `APP/engine/engine/crawlers/playwright_crawler.py`：Playwright 页面渲染和等待策略。
- `APP/engine/engine/governance.py`：结构化结果清洗、去重、完整率和质量分。
- `APP/engine/engine/output.py`：输出目录和结果文件生成。

## 1. 规则文件在系统里如何运行

一条 YAML 规则的完整运行链路如下：

1. Dashboard 或 CLI 选择规则文件。
2. `RuleParser.load_rule()` 使用 `yaml.safe_load()` 读取 YAML。
3. `RuleParser.validate()` 判断规则格式并做基础校验。
4. `InfoCollectorEngine.crawl()` 根据 `source.type` 和 `source.client` 选择采集方式。
5. 采集器请求网页或接口，得到原始 HTML 或 JSON。
6. `list.items_path` 先把页面或接口响应拆成多条列表项。
7. Rule v2 使用 `extract` 从每条列表项中提取结构化字段。
8. 正式运行时执行增量去重，沙箱试采不写去重库。
9. `GovernancePipeline` 清洗字段、计算内容哈希、完整率和质量分。
10. 正式运行时 `OutputManager` 写入 JSON 文件并更新 `combined_latest.json`。

Rule Center 的“试采”走 `/api/rules/preview`，只执行解析、采集、治理和结果截断，不写正式输出、不注册状态、不写去重库。

## 2. Rule v2 推荐结构

Rule v2 的识别条件是规则中出现 `rule_id`、`source_id` 或 `extract` 任一字段。只要被识别为 Rule v2，解析器会强制要求以下字段：

| 字段 | 是否强制校验 | 说明 |
| --- | --- | --- |
| `rule_id` | 是 | 规则唯一标识，建议使用 UUID 或稳定字符串。 |
| `source_id` | 是 | 来源唯一标识，用于区分同一事项下的来源。 |
| `version` | 是 | 规则版本，可以用数字或字符串。 |
| `extract` | 是 | Rule v2 的结构化字段定义，必须是非空对象。 |
| `source` | 运行必需 | 解析器未强制要求，但采集阶段需要。 |
| `list.items_path` | 运行必需 | 解析器未强制要求，但为空通常会采集 0 条。 |

推荐从下面的完整模板开始：

```yaml
rule_id: "data-value-example-html"
source_id: "example-html-source"
version: 1
status: TESTING
name: "示例站点 - 数据要素文章"
subject: "数据要素"
description: "从示例站点采集数据要素相关文章"
enabled: true

source:
  platform: "example"
  subject: "数据要素"
  type: "html"
  client: "auto"
  url: "https://example.com/news"
  auth:
    type: "none"

request:
  headers:
    User-Agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

list:
  items_path: "css:article.news-item"

extract:
  title:
    selector: "h2"
    type: "text"
  url:
    selector: "a"
    type: "attribute"
    attribute: "href"
  publish_time:
    selector: "time"
    type: "text"
  summary:
    selector: ".summary"
    type: "text"

dedup:
  incremental: true

governance:
  sanitize: true
  dedup: hash
  required_fields:
    - "title"
    - "url"
  min_completeness: 0.8

output:
  fields:
    - "title"
    - "url"
    - "publish_time"
    - "summary"
  save_raw: false
  filename_template: "example_data_value_{date}.json"
```

## 3. 顶层字段

| 字段 | 推荐 | 说明 |
| --- | --- | --- |
| `rule_id` | 必填 | Rule v2 规则唯一标识。 |
| `source_id` | 必填 | 来源唯一标识。 |
| `version` | 必填 | 规则版本。 |
| `status` | 推荐 | 可选值：`DRAFT`、`TESTING`、`PRODUCTION`、`DEPRECATED`。写其他值会校验失败。 |
| `name` | 推荐 | 规则名称，正式运行、状态记录和去重会使用。 |
| `subject` | 推荐 | 事项名。输出目录优先使用顶层 `subject`。 |
| `description` | 推荐 | 说明采集目的和适用范围。 |
| `enabled` | 推荐 | `false` 时正式运行和试采都会返回跳过。默认视为 `true`。 |
| `client` | 谨慎使用 | 顶层浏览器客户端配置，仅在浏览器采集链路中参与选择。通常写在 `source.client` 即可。 |

`subject` 的输出优先级是：顶层 `subject` 大于 `source.subject`。两者都没有时，当前输出逻辑会退回使用 `source.platform` 作为事项目录；为了避免输出混乱，新规则必须显式写 `subject`。

## 4. source：采集来源

`source` 决定采集器怎么拿到原始数据。

```yaml
source:
  platform: "cninfo"
  subject: "数据要素"
  type: "api"
  client: "desktop"
  url: "https://example.com/list"
  base_url: "https://example.com/api/search"
  enabled: true
```

### 4.1 source.type

| 值 | 运行链路 | 适用场景 |
| --- | --- | --- |
| `api` | `APICrawler` | 页面背后有稳定 JSON 接口，推荐优先使用。 |
| `html` | `HTMLCrawler` | 页面 HTML 里直接包含目标列表，不依赖前端渲染。 |
| `browser` | `BrowserCrawler` + Playwright | 内容由 JavaScript 渲染、需要等待 DOM、静态请求拿不到数据。 |

如果不写 `source.type`，引擎默认按 `html` 处理。

### 4.2 source.client

当前解析器允许的值是：`auto`、`mobile`、`desktop`、`browser`、`playwright`。

| 值 | 在 `html` 链路中的行为 | 在 `browser` 链路中的行为 |
| --- | --- | --- |
| `auto` | 先用桌面 UA 请求，响应长度小于 5000 字符时再用移动 UA 请求。 | 不建议用于 `browser`，当前浏览器客户端只接受 `browser` 或 `playwright`。 |
| `mobile` | 使用移动端 UA 请求。 | 不建议用于 `browser`。 |
| `desktop` | 使用桌面端 UA 请求。 | 不建议用于 `browser`。 |
| `browser` | 即使 `source.type` 不是 `browser`，也会强制走浏览器采集。 | 使用 Playwright。 |
| `playwright` | 不会强制切到浏览器；如果 `source.type: html`，仍按静态 HTML 请求处理。 | 使用 Playwright。 |

实际选择逻辑：

- `source.client: browser` 的优先级最高，会强制走浏览器采集。
- `source.type: api` 会走 API 采集，除非 `source.client: browser`。
- `source.type: browser` 会走浏览器采集。
- 其他情况走静态 HTML 采集。

禁止使用：

```yaml
source:
  client: "crawl4ai"
```

`crawl4ai` 会被解析器拒绝。

### 4.3 source.url 和 source.base_url

| 字段 | 用于 | 说明 |
| --- | --- | --- |
| `source.url` | `html`、`browser` | 页面 URL。 |
| `source.base_url` | `api` | 接口 URL。 |

API 规则如果只写 `url` 不写 `base_url`，当前 API 采集器不会使用它。

### 4.4 source.enabled

`source.enabled: false` 与顶层 `enabled: false` 效果类似，正式运行和试采都会跳过：

```yaml
source:
  enabled: false
```

## 5. request：请求配置

`request` 在 API 和 HTML 场景中的作用不同。

### 5.1 HTML 请求头

静态 HTML 采集会读取 `request.headers`。如果 headers 里写了 `User-Agent`，它会覆盖 `source.client` 自动选择的 UA。

```yaml
request:
  headers:
    User-Agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    Referer: "https://example.com/"
```

### 5.2 API 请求

API 采集使用以下字段：

```yaml
source:
  type: "api"
  base_url: "https://www.cninfo.com.cn/new/fulltextSearch/full"

request:
  method: "POST"
  headers:
    User-Agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    Content-Type: "application/x-www-form-urlencoded"
  body_template: |
    searchkey={keyword}&sdate=&edate=&isfulltext=false&sortName=pubdate&sortType=desc
  params:
    keyword: "数据要素"
```

运行时会做这些事：

- `method` 默认是 `GET`。
- 请求 URL 来自 `source.base_url`。
- `headers` 原样传给 `requests.request()`。
- `body_template` 中的 `{keyword}` 会被 `request.params.keyword` 替换。
- 只有 `method: "POST"` 时，替换后的 body 会作为 `data` 发送。

当前 API 采集器不支持在 YAML 中直接声明 query string 参数对象；如果要发 GET 查询参数，需要把参数写进 `source.base_url`。

## 6. list.items_path：如何拆出列表项

`list.items_path` 是第一层提取。它不负责最终字段，只负责把页面或接口响应拆成多条“候选记录”。

### 6.1 API：JSONPath

API 规则使用 JSONPath：

```yaml
list:
  items_path: "$.announcements[*]"
```

如果接口返回：

```json
{
  "announcements": [
    {"announcementTitle": "标题一"},
    {"announcementTitle": "标题二"}
  ]
}
```

`$.announcements[*]` 会产生两条列表项。后续字段从每条列表项里提取。

### 6.2 HTML 或 Browser：CSS

推荐优先使用 `css:`：

```yaml
list:
  items_path: "css:article.news-item"
```

每个匹配元素会被转换为类似下面的结构，供 `extract` 使用：

```json
{
  "href": "/detail/1",
  "title": "整条元素的文本",
  "text": "整条元素的文本",
  "html": "<article>...</article>"
}
```

Rule v2 的 `extract` 会在每个 `html` 片段内部继续查找字段。因此 `items_path` 应该选中“单条记录的外层容器”，不要直接选中标题或链接。

推荐：

```yaml
list:
  items_path: "css:article.news-item"
```

不推荐：

```yaml
list:
  items_path: "css:article.news-item h2"
```

### 6.3 HTML 或 Browser：XPath

也可以使用 `xpath:`：

```yaml
list:
  items_path: "xpath://div[contains(@class, 'news-item')]"
```

XPath 匹配结果同样会转换成包含 `href`、`title`、`html` 的列表项。

### 6.4 HTML 或 Browser：regex

`regex:` 主要用于旧规则兼容或页面结构极不规整时兜底：

```yaml
list:
  items_path: 'regex:<a[^>]*href="([^"]+)"[^>]*title="([^"]+)"[^>]*>'
```

正则捕获组行为：

- 1 个捕获组：生成 `{"href": 第 1 组}`。
- 2 个及以上捕获组：生成 `{"href": 第 1 组, "title": 第 2 组}`。

Rule v2 不推荐在新规则中依赖 `regex:`，因为正则列表项通常没有完整 `html` 片段，`extract` 在其上继续选择字段时容易得到空值。必须使用正则时，更适合旧格式 `list.fields` 的 `element_text` 和 `element_href`。

## 7. extract：Rule v2 字段提取

`extract` 是 Rule v2 的核心。它从每条列表项的 `html` 片段中提取结构化字段。

```yaml
extract:
  title:
    selector: "h2"
    type: "text"
  url:
    selector: "a"
    type: "attribute"
    attribute: "href"
  html_body:
    selector: ".content"
    type: "html"
  tags:
    selector: ".tag"
    type: "list"
```

### 7.1 extract 字段定义

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `selector` | 是 | CSS 选择器。当前 Rule v2 字段提取只支持 CSS 选择器，不支持 `xpath:` 前缀。 |
| `type` | 否 | 默认 `text`。可选：`text`、`attribute`、`html`、`list`。 |
| `attribute` | 条件必填 | `type: attribute` 时需要写属性名，如 `href`。 |

解析器只强制检查每个字段有 `selector`，不会提前检查 `type` 是否有效。未知 `type` 会按 `text` 的逻辑处理。

### 7.2 type: text

提取匹配元素的全部文本并去掉首尾空白。

```yaml
extract:
  title:
    selector: "h2.title"
    type: "text"
```

适合标题、摘要、发布时间、作者等纯文本字段。

### 7.3 type: attribute

提取匹配元素的属性。

```yaml
extract:
  url:
    selector: "a"
    type: "attribute"
    attribute: "href"
```

注意：当前 Rule v2 不会自动把相对 URL 转为绝对 URL。如果页面返回 `/detail/1`，输出就是 `/detail/1`。需要绝对 URL 时，优先选择页面中已有的绝对链接，或在后续代码中扩展 Rule v2 的 URL 拼接能力。

### 7.4 type: html

提取匹配元素的 HTML。

```yaml
extract:
  body_html:
    selector: ".article-content"
    type: "html"
```

治理阶段默认会清洗字符串中的 HTML 标签，所以如果希望最终保留 HTML，当前治理配置需要设置：

```yaml
governance:
  sanitize: false
```

### 7.5 type: list

提取多个匹配元素的文本列表。

```yaml
extract:
  tags:
    selector: ".tag"
    type: "list"
```

输出示例：

```json
{
  "tags": ["政策", "数据资产", "交易所"]
}
```

## 8. API 规则示例

适合能直接找到 JSON 接口的网站。优先选择 API 规则，因为结构稳定、速度快、对页面改版不那么敏感。

```yaml
rule_id: "cninfo-data-value-search"
source_id: "cninfo-fulltext-search"
version: 1
status: PRODUCTION
name: "巨潮资讯 - 数据要素相关公告"
subject: "数据要素"
description: "从巨潮资讯搜索数据要素相关上市公司公告"
enabled: true

source:
  platform: "cninfo"
  subject: "数据要素"
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

extract:
  title:
    selector: "announcementTitle"
    type: "text"

output:
  fields:
    - "title"
```

上面这个示例故意展示了一个问题：当前 Rule v2 的 `extract` 只适用于 HTML 或 Browser 列表项，不适用于 API JSON 字段。API 规则在当前代码中仍使用旧格式 `list.fields` 做字段提取。

因此，现阶段 API 规则推荐采用“Rule v2 元数据 + 旧字段提取”的过渡写法：

```yaml
rule_id: "cninfo-data-value-search"
source_id: "cninfo-fulltext-search"
version: 1
status: PRODUCTION
name: "巨潮资讯 - 数据要素相关公告"
subject: "数据要素"
enabled: true

source:
  platform: "cninfo"
  subject: "数据要素"
  type: "api"
  base_url: "https://www.cninfo.com.cn/new/fulltextSearch/full"

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
      transform: "strip_html,trim"
    - name: "url"
      type: "computed"
      value: "https://www.cninfo.com.cn/new/disclosure/detail?announcementId={announcementId}&orgId={orgId}"
      vars:
        announcementId: "$.announcementId"
        orgId: "$.orgId"
    - name: "publish_time"
      type: "field"
      path: "$.announcementTime"
      transform: "timestamp_ms_to_iso"
    - name: "company"
      type: "field"
      path: "$.secName"
    - name: "platform"
      type: "constant"
      value: "巨潮资讯"
    - name: "raw_id"
      type: "field"
      path: "$.announcementId"

extract:
  compatibility_marker:
    selector: "unused"
    type: "text"

dedup:
  incremental: true

governance:
  sanitize: true
  dedup: hash
  required_fields:
    - "title"
    - "url"
  min_completeness: 0.8

output:
  fields:
    - "title"
    - "url"
    - "publish_time"
    - "company"
    - "platform"
  filename_template: "cninfo_data_value_{date}.json"
```

说明：

- 因为只要出现 `extract` 就会被识别为 Rule v2，所以这里保留一个无业务意义的 `compatibility_marker` 让规则通过 Rule v2 校验。
- API 采集阶段实际读取的是 `list.fields`，不会读取 `extract`。
- 这是当前代码能力下的过渡方案。后续如果引擎支持 API Rule v2 字段提取，应迁移到真正的 JSON 字段 DSL。

## 9. 静态 HTML 规则示例

适合服务器直接返回完整列表 DOM 的页面。

```yaml
rule_id: "example-static-news"
source_id: "example-news-page"
version: 1
status: TESTING
name: "示例站点 - 静态新闻列表"
subject: "数据要素"
enabled: true

source:
  platform: "example"
  subject: "数据要素"
  type: "html"
  client: "auto"
  url: "https://example.com/news"

list:
  items_path: "css:article.news-item"

extract:
  title:
    selector: "h2"
    type: "text"
  url:
    selector: "a"
    type: "attribute"
    attribute: "href"
  publish_time:
    selector: "time"
    type: "text"
  summary:
    selector: ".summary"
    type: "text"

governance:
  sanitize: true
  dedup: hash
  required_fields:
    - "title"
    - "url"
  min_completeness: 0.8

output:
  fields:
    - "title"
    - "url"
    - "publish_time"
    - "summary"
  filename_template: "example_static_news_{date}.json"
```

调试要点：

- 如果采集 0 条，先检查 `items_path` 是否能选中单条记录外层容器。
- 如果条数正确但字段为空，检查 `extract.*.selector` 是否能在单条记录内部选中字段。
- 如果移动端页面结构更稳定，可以把 `source.client` 改为 `mobile`。

## 10. 浏览器渲染规则示例

适合内容由 JavaScript 渲染、静态请求拿不到列表的页面。

```yaml
rule_id: "example-browser-news"
source_id: "example-browser-page"
version: 1
status: TESTING
name: "示例站点 - 渲染新闻列表"
subject: "数据要素"
enabled: true

source:
  platform: "example"
  subject: "数据要素"
  type: "browser"
  client: "browser"
  url: "https://example.com/app/news"

render:
  headless: true
  stealth: true
  user_agent: "random"
  wait_for_selector: "article.news-item"
  wait_for_timeout: 5000
  viewport_width: 1920
  viewport_height: 1080
  extra_headers:
    Referer: "https://example.com/"

list:
  items_path: "css:article.news-item"

extract:
  title:
    selector: "h2"
    type: "text"
  url:
    selector: "a"
    type: "attribute"
    attribute: "href"
  publish_time:
    selector: "time"
    type: "text"

governance:
  sanitize: true
  dedup: hash
  required_fields:
    - "title"
    - "url"

output:
  fields:
    - "title"
    - "url"
    - "publish_time"
  filename_template: "example_browser_news_{date}.json"
```

`render` 的真实含义：

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `headless` | `true` | 是否无头运行浏览器。 |
| `stealth` | `true` | 是否启用一组降低自动化特征的 Chromium 参数。 |
| `user_agent` | `random` | 随机桌面 UA，或写固定 UA 字符串。 |
| `wait_for_selector` | 无 | 等待某个 CSS 选择器出现。等不到时不会直接失败，会继续使用当前页面内容。 |
| `wait_for_timeout` | `3000` | 等待选择器的毫秒数。 |
| `viewport_width` | `1920` | 浏览器视口宽度。 |
| `viewport_height` | `1080` | 浏览器视口高度。 |
| `extra_headers` | `{}` | 创建浏览器上下文时传入的额外请求头。 |

浏览器页面加载流程：

1. Playwright 打开 Chromium。
2. `page.goto(url, wait_until="domcontentloaded", timeout=15000)`。
3. 如果配置了 `wait_for_selector`，等待对应元素。
4. 额外等待 1500 毫秒让页面脚本继续执行。
5. 读取最终 `page.content()`，再按 `items_path` 和 `extract` 提取。

## 11. governance：治理配置

治理阶段会处理已经提取好的结构化字段。

```yaml
governance:
  sanitize: true
  dedup: hash
  required_fields:
    - "title"
    - "url"
  min_completeness: 0.8
```

| 字段 | 默认值 | 说明 |
| --- | --- | --- |
| `sanitize` | `true` | 清除 HTML 标签、控制字符，并做 HTML 实体反转义。 |
| `dedup` | 无 | 写 `hash`、`simhash` 或 `minhash` 时，按内容哈希在本次结果内去重。当前三者实际都按同一个内容哈希逻辑处理。 |
| `required_fields` | `output.fields` | 用于计算字段完整率。 |
| `min_completeness` | `0.8` | 平均完整率低于该值时，任务状态为 `partial_success`。 |

每条记录会追加 `_governance` 字段：

```json
{
  "_governance": {
    "content_hash": "内容哈希",
    "field_completeness": 1.0,
    "injection_risk": false
  }
}
```

治理摘要会写入输出文件的 `meta.governance`：

```json
{
  "item_count": 10,
  "duplicate_count": 1,
  "injection_risk_count": 0,
  "field_completeness": 0.95,
  "quality_score": 0.95,
  "status": "SUCCESS"
}
```

提示注入风险检测目前只匹配少量固定文本，例如 `ignore previous instructions`、`忽略之前的指令`、`system prompt`、`developer message`。匹配后会从文本字段中移除这些片段，并标记 `injection_risk: true`。

## 12. dedup：增量去重

正式运行时，`dedup.incremental: true` 会启用跨运行去重：

```yaml
dedup:
  incremental: true
```

当前去重调用使用：

- 规则维度：`name`。
- 平台维度：`source.platform`。
- 记录维度：每条 item 的 `raw_id` 和 `url`。

如果没有 `raw_id`，应尽量保证 `url` 稳定。对于 HTML 页面，Rule v2 当前不会自动从 URL 正则提取 `raw_id`；旧格式采集链路支持 `dedup.url_to_id_pattern`。

`dedup.id_template` 在现有输出中可作为文档化约定保留，但当前去重实现实际不使用这个模板生成 ID。

## 13. output：输出配置

```yaml
output:
  fields:
    - "title"
    - "url"
    - "publish_time"
  save_raw: false
  filename_template: "example_{date}.json"
```

| 字段 | 说明 |
| --- | --- |
| `fields` | 治理默认必填字段来源；当前保存时不会按这个列表裁剪 item 字段。 |
| `save_raw` | 当前代码没有保存原始响应的实现，建议固定写 `false`。 |
| `filename_template` | 输出文件名模板，`{date}` 会替换成 `YYYYMMDD`。 |
| `path` | 可选。写了以后直接作为输出目录；不写则使用默认目录结构。 |

默认输出目录：

```text
APP/engine/output/{subject}/{platform}/{filename_template}
APP/engine/output/{subject}/combined_latest.json
```

输出文件结构：

```json
{
  "meta": {
    "subject": "数据要素",
    "platform": "example",
    "rule_name": "示例站点 - 静态新闻列表",
    "collected_at": "2026-05-15T10:00:00",
    "count": 3,
    "dedup_filtered": 0,
    "governance": {}
  },
  "data": []
}
```

如果正式运行后没有新增数据，当前输出逻辑不会写数据文件。

`combined_latest.json` 会汇总同一事项下各平台最近的数据文件，并按 URL 做一次合并去重，最多扫描最近 200 个 JSON 文件。

## 14. 沙箱试采

Rule Center 的试采接口是：

```text
POST /api/rules/preview
```

请求体：

```json
{
  "yaml": "rule_id: ...",
  "limit": 5
}
```

行为：

- YAML 为空返回 400。
- YAML 解析或规则校验失败返回 400。
- 采集异常返回 200，但 `success: false`。
- `limit` 会被限制在 1 到 20。
- 试采不写正式输出、不更新 `state.json`、不写去重库。
- 试采仍会执行治理，所以预览结果会包含 `_governance` 字段。

返回结构：

```json
{
  "success": true,
  "status": "success",
  "total_collected": 2,
  "preview_count": 1,
  "items": [],
  "governance": {}
}
```

## 15. 常见网页适配方法

### 15.1 静态列表页

判断方法：浏览器查看源代码能看到目标标题和链接。

推荐配置：

```yaml
source:
  type: "html"
  client: "auto"
list:
  items_path: "css:article"
extract:
  title:
    selector: "h2"
    type: "text"
  url:
    selector: "a"
    type: "attribute"
    attribute: "href"
```

### 15.2 移动端结构更简单的页面

很多站点移动端 HTML 更轻，适合用移动 UA。

```yaml
source:
  type: "html"
  client: "mobile"
```

如果页面对 UA 敏感，也可以直接写请求头：

```yaml
request:
  headers:
    User-Agent: "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
```

### 15.3 JavaScript 渲染页面

判断方法：`requests` 请求得到的 HTML 里没有目标列表，但浏览器页面上能看到。

推荐配置：

```yaml
source:
  type: "browser"
  client: "browser"
render:
  wait_for_selector: ".news-item"
  wait_for_timeout: 5000
list:
  items_path: "css:.news-item"
```

### 15.4 搜索 API

判断方法：浏览器开发者工具 Network 里能看到返回 JSON 的接口。

当前推荐使用兼容字段提取：

```yaml
source:
  type: "api"
  base_url: "https://example.com/api/search"
request:
  method: "POST"
  body_template: |
    keyword={keyword}&pageNum=1
  params:
    keyword: "数据要素"
list:
  items_path: "$.data.records[*]"
  fields:
    - name: "title"
      type: "field"
      path: "$.title"
    - name: "url"
      type: "field"
      path: "$.url"
extract:
  compatibility_marker:
    selector: "unused"
```

### 15.5 正则兜底

只在 CSS、XPath 都难以稳定选中时使用。

```yaml
list:
  items_path: 'regex:<a[^>]*href="([^"]+)"[^>]*title="([^"]+)"[^>]*>'
```

新规则中使用正则时要特别注意：Rule v2 的 `extract` 依赖列表项中的 `html`，而正则列表项通常只有 `href` 和 `title`。因此正则更适合旧格式兼容链路。

## 16. 调试与排错

### 16.1 规则校验失败

常见原因：

| 错误表现 | 原因 |
| --- | --- |
| `Missing required field: rule_id` | 被识别为 Rule v2，但缺少 `rule_id`。 |
| `Missing required field: source_id` | 被识别为 Rule v2，但缺少 `source_id`。 |
| `Rule v2 requires non-empty extract` | `extract` 为空对象。 |
| `Invalid rule status` | `status` 不在允许列表内。 |
| `Invalid client strategy` | `client` 或 `source.client` 值不合法。 |
| `Crawl4AI` | 使用了已禁止的 `crawl4ai`。 |
| `source.extraction` | 使用了系统内 AI/LLM 提取配置。 |

### 16.2 采集 0 条

按顺序检查：

1. `source.url` 或 `source.base_url` 是否正确。
2. `source.type` 是否选对。
3. 静态 HTML 是否真的包含目标数据。
4. `list.items_path` 是否选中了单条记录容器。
5. JS 渲染页面是否需要 `source.type: browser`。
6. 浏览器规则是否需要 `render.wait_for_selector`。
7. API 规则的 `list.items_path` JSONPath 是否指向数组。

### 16.3 有条数但字段为空

按顺序检查：

1. `items_path` 是否选得太窄，导致列表项内部没有标题或链接。
2. `extract.*.selector` 是否相对于单条列表项，而不是相对于整页。
3. `attribute` 是否写对，例如链接通常是 `href`。
4. Rule v2 是否误用于 API JSON 字段提取。

### 16.4 输出文件没有生成

常见原因：

- 规则被 `enabled: false` 或 `source.enabled: false` 跳过。
- 采集结果为空。
- 增量去重后没有新增数据。
- 采集失败，任务返回 `failed`。

## 17. 禁止配置

项目目标是确定性采集和结构化治理，不在运行链路中调用 AI。

禁止浏览器客户端：

```yaml
source:
  client: "crawl4ai"
```

禁止系统内 AI 提取配置：

```yaml
source:
  extraction:
    enabled: true
    strategy: "llm"
    prompt: "extract articles"
```

这些配置会在规则校验阶段失败。

## 18. 旧格式兼容说明

旧格式仍被当前代码支持，现有规则大多使用这种写法。新规则不推荐继续使用，但维护旧规则时必须理解它。

旧格式最小结构：

```yaml
name: "钛媒体 - 数据要素相关文章"
subject: "数据要素"
version: "1.0.2"
enabled: true

source:
  platform: "tmtpost"
  type: "html"
  client: "auto"
  subject: "数据要素"
  url: "https://www.tmtpost.com/"

list:
  items_path: 'regex:<a[^>]*href="([^"]+)"[^>]*title="([^"]+)"[^>]*>'
  fields:
    - name: "title"
      type: "element_text"
    - name: "url"
      type: "element_href"

output:
  filename_template: "tmtpost_data_articles_{date}.json"
```

旧格式解析器强制要求：

- `name`
- `source`
- `list`

### 18.1 旧格式 API 字段类型

API 规则使用 `list.fields`：

| type | 运行行为 |
| --- | --- |
| `field` | 从当前 JSON 列表项中用 JSONPath 取值。 |
| `constant` | 输出固定值。 |
| `computed` | 使用 `value` 模板，并用 `vars` 中的 JSONPath 替换占位符。 |

示例：

```yaml
list:
  items_path: "$.announcements[*]"
  fields:
    - name: "title"
      type: "field"
      path: "$.announcementTitle"
      transform: "strip_html,trim"
    - name: "url"
      type: "computed"
      value: "https://example.com/detail?id={id}"
      vars:
        id: "$.announcementId"
    - name: "platform"
      type: "constant"
      value: "巨潮资讯"
```

支持的 `transform`：

| transform | 说明 |
| --- | --- |
| `strip_html` | 移除 HTML 标签。 |
| `trim` | 去掉首尾空白。 |
| `timestamp_ms_to_iso` | 毫秒或秒时间戳转 ISO 字符串。 |

多个转换用逗号分隔。

### 18.2 旧格式 HTML/Browser 字段类型

HTML 和 Browser 旧格式同样使用 `list.fields`：

| type | 运行行为 |
| --- | --- |
| `constant` | 输出固定值。 |
| `attr` | 从列表项字典中取指定属性，默认 `href`。 |
| `computed` | 直接输出 `value`，HTML 链路不会替换变量。 |
| `element_text` | 取列表项里的 `title`，没有则取 `text`。 |
| `element_href` | 取列表项里的 `href`。 |
| `xpath` | 在列表项的 `html` 片段上执行 XPath 提取文本。 |

`element_href` 支持特殊 URL 转换：

```yaml
fields:
  - name: "url"
    type: "element_href"
    transform: "sogou_link"
```

`sogou_link` 会尝试解析搜狗微信中间链接中的真实文章 URL。浏览器链路还支持：

```yaml
fields:
  - name: "url"
    type: "element_href"
    resolve_url: true
```

`resolve_url: true` 会用浏览器打开链接并返回跳转后的最终 URL；失败时保留原始 URL。

### 18.3 旧格式 url_to_id_pattern

旧格式 HTML 和 Browser 链路支持从 URL 中提取 `raw_id`：

```yaml
dedup:
  incremental: true
  url_to_id_pattern: "tmtpost\\.com/(\\d+)\\.html"
```

如果正则匹配成功，会把第一个捕获组写入 item 的 `raw_id`。

## 19. 从旧格式迁移到 Rule v2

迁移原则：

- 静态 HTML 和 Browser 规则优先迁移到真正的 Rule v2 `extract`。
- API 规则当前保留 `list.fields`，同时补齐 Rule v2 元数据，等引擎支持 JSON 版 `extract` 后再迁移。
- 迁移后必须用试采验证条数、字段完整率和输出字段。

### 19.1 HTML 规则迁移

旧格式：

```yaml
list:
  items_path: "css:article.news-item"
  fields:
    - name: "title"
      type: "element_text"
    - name: "url"
      type: "element_href"
```

Rule v2：

```yaml
list:
  items_path: "css:article.news-item"
extract:
  title:
    selector: "h2"
    type: "text"
  url:
    selector: "a"
    type: "attribute"
    attribute: "href"
```

迁移时要确认 `items_path` 选中的是包含 `h2` 和 `a` 的外层元素。

### 19.2 Browser 规则迁移

旧格式中的 `render` 可以保留。字段部分迁移到 `extract`：

```yaml
source:
  type: "browser"
  client: "browser"
render:
  wait_for_selector: ".result-card"
list:
  items_path: "css:.result-card"
extract:
  title:
    selector: ".title"
    type: "text"
  url:
    selector: "a"
    type: "attribute"
    attribute: "href"
```

### 19.3 API 规则迁移

当前 API 规则不要强行把 JSONPath 写进 `extract.selector`。Rule v2 的 `extract.selector` 是 CSS 选择器，API JSON 不会走这段逻辑。

推荐过渡方式：

```yaml
rule_id: "stable-rule-id"
source_id: "stable-source-id"
version: 1
status: PRODUCTION

source:
  type: "api"
  base_url: "https://example.com/api"

list:
  items_path: "$.data[*]"
  fields:
    - name: "title"
      type: "field"
      path: "$.title"

extract:
  compatibility_marker:
    selector: "unused"
```

后续引擎如增加 JSON 版 Rule v2 字段提取，再把 `list.fields` 迁移为新的 API 字段 DSL。

## 20. 新规则编写检查清单

写完规则后按下面顺序检查：

1. 是否有 `rule_id`、`source_id`、`version`、非空 `extract`。
2. `status` 是否是 `DRAFT`、`TESTING`、`PRODUCTION`、`DEPRECATED` 之一。
3. `subject` 和 `source.subject` 是否明确。
4. `source.type` 是否符合数据来源：接口用 `api`，静态页面用 `html`，JS 渲染用 `browser`。
5. HTML 或 Browser 规则的 `items_path` 是否选中单条记录外层容器。
6. HTML 或 Browser 规则的 `extract` 是否只使用 CSS 选择器。
7. API 规则是否使用 `list.fields` 做 JSON 字段提取。
8. `governance.required_fields` 是否至少包含 `title` 和 `url`。
9. `dedup.incremental` 是否符合运行需求。
10. 是否没有 `crawl4ai`、`source.extraction`、LLM prompt 等禁止配置。
11. 是否已经在 Rule Center 试采，确认 `total_collected`、`preview_count` 和字段完整率符合预期。

