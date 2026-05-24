# YAML 规则编写手册

本手册对应 Info Collector NG 本地 MVP。规则必须由人工编写或离线生成后上传，系统只负责校验、试采、结构化提取和治理，不在运行链路中调用 AI。

## 基本原则

- 规则必须输出结构化字段，不允许把原始 HTML 当作最终数据。
- 默认不保存原始响应；只有规则明确声明 `output.save_raw: true` 时才允许后续扩展保存 Raw。
- 浏览器渲染使用 Playwright。
- 禁止 `client: crawl4ai`。
- 禁止 `source.extraction`、LLM prompt、语义提取策略等系统内 AI 配置。

## Rule v2 最小结构

```yaml
rule_id: "3fa85f64-5717-4562-b3fc-2c963f66afa6"
source_id: "example-source"
version: 1
status: PRODUCTION
source:
  platform: "example"
  type: "html"
  url: "https://example.com/news"
list:
  items_path: "css:article"
extract:
  title:
    selector: "h1"
    type: "text"
  url:
    selector: "a"
    type: "attribute"
    attribute: "href"
  publish_time:
    selector: "time"
    type: "text"
output:
  fields: ["title", "url", "publish_time"]
  save_raw: false
governance:
  sanitize: true
  dedup: hash
  required_fields: ["title", "url"]
  min_completeness: 0.8
```

## source

```yaml
source:
  platform: "example"
  type: "html"      # api | html | browser
  url: "https://example.com"
  client: "desktop" # auto | mobile | desktop | browser | playwright
```

- `api`：请求接口并用 JSONPath 提取。
- `html`：静态 HTTP 页面，使用 CSS 或 XPath 提取。
- `browser`：Playwright 渲染页面后再提取。
- `client: browser` 与 `client: playwright` 均走 Playwright。

## list

`items_path` 定义列表项选择器：

```yaml
list:
  items_path: "css:article"
```

支持：

- `css:<selector>`
- `xpath:<expr>`
- `regex:<pattern>`，仅用于旧规则兼容

## extract

Rule v2 推荐使用 `extract` 定义字段：

```yaml
extract:
  title: { selector: "h1", type: "text" }
  html_body: { selector: ".content", type: "html" }
  url: { selector: "a", type: "attribute", attribute: "href" }
  tags: { selector: ".tag", type: "list" }
```

字段类型：

| 类型 | 说明 |
|------|------|
| `text` | 提取文本 |
| `html` | 提取选中元素 HTML |
| `attribute` | 提取属性，需设置 `attribute` |
| `list` | 提取多个匹配文本 |

## governance

```yaml
governance:
  sanitize: true
  dedup: hash
  required_fields: ["title", "content"]
  min_completeness: 0.8
```

治理管道会执行：

- HTML 标签清洗。
- 控制字符清洗。
- 常见提示注入文本标记。
- 内容哈希。
- 字段完整率计算。
- 质量分计算。

当字段完整率低于 `min_completeness` 时，治理状态为 `PARTIAL_SUCCESS`。

## output

```yaml
output:
  fields: ["title", "url", "publish_time"]
  save_raw: false
  filename_template: "data_{date}.json"
```

输出文件会写入：

```text
APP/engine/output/{subject}/{platform}/
```

输出 `meta.governance` 包含治理摘要。

## 禁止配置

以下配置会被拒绝：

```yaml
source:
  client: "crawl4ai"
```

```yaml
source:
  extraction:
    enabled: true
    prompt: "extract ..."
    strategy: "llm"
```
