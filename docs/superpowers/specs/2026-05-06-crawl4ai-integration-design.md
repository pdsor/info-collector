# Crawl4AI 集成设计规格

> 状态：草稿，待用户审查
> 日期：2026-05-06
> 目标：用 Crawl4AI 完全替换现有 Playwright 实现

---

## 1. 背景与目标

info-collector 通用采集程序的 browser crawler 层当前使用 Playwright（`BrowserCrawler` 类），虽已支持 stealth 模式，但在以下方面存在不足：
- JS 渲染策略单一，无 LLM 辅助解析
- 反爬对抗能力有限，复杂站点容易触发检测
- HTML 输出质量依赖 `page.content()`，含大量噪音标签

Crawl4AI v0.8.6 提供：LLM extraction、多种 anti-bot 策略、高质量 markdown 输出。本次集成以 **完全替代** 为目标，对外接口（`BrowserCrawler` 类）保持不变。

---

## 2. 关键设计决策（已获批）

| # | 决策 | 结论 |
|---|---|---|
| A | `client` 字段扩展方式 | 新增 `client: crawl4ai` 枚举值，扩展现有 `client` 字段（auto/mobile/desktop/browser） |
| B | `source.type` 路由 | 所有 `source.type: browser` 统一走 Crawl4AI（不改并存的旧的 Playwright 实现） |
| C | 替换策略 | 完全替换 `crawl_browser.py`，对外接口不变 |
| D | source.type 与 client 关系 | 所有 `source.type: browser` 无条件走 Crawl4AI，`client` 字段保留给未来扩展 |
| E | 集成哪些能力 | 全部（LLM extraction + 反爬稳定性 + Markdown输出） |

---

## 3. YAML 规则扩展

### 3.1 新增 `client` 枚举值

```yaml
# 现有
client: auto      # desktop 优先，响应过小时 fallback mobile
client: mobile    # 固定 mobile UA
client: desktop   # 固定 desktop UA
client: browser   # Playwright JS 渲染（现有）

# 新增
client: crawl4ai  # Crawl4AI JS 渲染 + LLM extraction
```

### 3.2 `source` 配置扩展（适用于 `type: browser` 时）

```yaml
source:
  type: browser
  url: "https://example.com/page"
  client: crawl4ai                    # 新增：指定 crawler 类型
  browser:
    headless: true                    # 默认 true
    stealth: true                     # 默认 true（anti-bot）
    viewport_width: 1920              # 默认 1920
    viewport_height: 1080             # 默认 1080
    wait_for_selector: ".content"    # 可选：等待元素
    wait_for_timeout: 5000            # 默认 3000ms
    anti_bot: true                    # 新增：更强的反爬策略
  extraction:
    enabled: true                     # 新增：启用 LLM extraction
    prompt: "提取所有文章标题、链接和发布时间"  # 新增：LLM 抽取提示词
    strategy: "cosine"                # 新增：抽取策略（cosine/relevance/threshold/must_match）
    chunk_token_threshold: 4000       # 可选：chunk 阈值
  markdown:
    enabled: true                     # 新增：输出 markdown（替代 raw HTML）
    remove_footers: true              # 可选：移除页脚
    remove_forms: true                # 可选：移除表单
```

### 3.3 字段定义扩展（`fields` 中新增 type）

```yaml
# 现有支持的 field type
fields:
  - name: title
    type: xpath       # 或 css
    path: "//h1/text()"
  - name: url
    type: attr
    attr: href

# 新增
fields:
  - name: title
    type: llm          # 新增：LLM 抽取字段
    prompt: "文章标题"
  - name: content
    type: markdown     # 新增：直接输出 markdown
```

> **向后兼容**：现有 YAML 无需修改。`client` 字段缺失时，`source.type: browser` 默认行为走 Crawl4AI（如果安装了 crawl4ai），未安装时 fallback 到旧 Playwright 实现。

---

## 4. 架构设计

### 4.1 文件变更

```
APP/engine/engine/
  crawl_browser.py    # 重写：基于 Crawl4AI，完全替代现有 Playwright 实现
  crawlers/
    __init__.py       # 新增：crawler 子模块
    crawl4ai_crawler.py   # 新增：Crawl4AI 封装
    playwright_crawler.py # 保留：降级用（当 crawl4ai 不可用时）
```

### 4.2 类设计

```python
# crawl_browser.py（完全重写）
class BrowserCrawler:
    """
    对外接口不变，内部实现替换为 Crawl4AI。
    当 crawl4ai 未安装时，降级到 Playwright 实现。
    """

    def fetch(self, url: str, render_config: dict = None) -> str:
        """
        渲染 JS 并返回页面内容。
        - render_config.get('client') == 'crawl4ai' 时使用 Crawl4AI
        - 否则 fallback 到 Playwright
        返回: markdown 或 HTML 字符串（取决于 render_config.markdown.enabled）
        """
        client = render_config.get('client', 'playwright') if render_config else 'playwright'
        if client == 'crawl4ai':
            return self._fetch_crawl4ai(url, render_config)
        else:
            return self._fetch_playwright(url, render_config)

    def _fetch_crawl4ai(self, url: str, config: dict) -> str:
        """使用 Crawl4AI 渲染页面"""
        ...

    def _fetch_playwright(self, url: str, config: dict) -> str:
        """降级：使用 Playwright（现有实现）"""
        ...

    def extract_fields(self, content: str, field_defs: list) -> dict:
        """
        支持新的 field type：
        - type: llm      → 调用 LLMExtractionStrategy
        - type: markdown → 直接返回 markdown 内容
        """
        ...

    def close(self):
        """清理所有 crawler 实例"""
        ...
```

### 4.3 解析流程

```
YAML source.client: "crawl4ai"
       ↓
engine.py crawl() 识别 client_mode == "browser"
       ↓
BrowserCrawler.fetch(url, render_config)
       ↓
Crawl4AI 渲染 + 可选 LLM extraction
       ↓
返回 markdown / HTML 字符串
       ↓
parsers 层处理（CSS/XPath/JSONPath）
       ↓
dedup 去重 → output 输出
```

### 4.4 LLM Extraction 集成

当 `source.extraction.enabled: true` 或 `fields[].type: llm` 时：

```python
from crawl4ai import AsyncPlaywrightCrawlerStrategy
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from pydantic import BaseModel

class ArticleSchema(BaseModel):
    title: str
    url: str
    publish_date: str = ""

strategy = LLMExtractionStrategy(
    prompt="提取所有文章标题、链接和发布时间",
    schema=ArticleSchema,
    extraction_strategy="cosine"  # or "relevance", "threshold", "must_match"
)

result = await crawler.crawl(url, extractor=strategy)
```

> **注意**：LLM extraction 依赖外部 LLM API（OpenAI/Anthropic），需要配置 `OPENAI_API_KEY` 或等效环境变量。Extractor 结果以 JSON 形式返回，绕过 CSS/XPath 解析。

---

## 5. 向后兼容与降级

| 场景 | 行为 |
|---|---|
| `client: crawl4ai`，crawl4ai 已安装 | 使用 Crawl4AI |
| `client: crawl4ai`，crawl4ai **未**安装 | 警告日志 + fallback Playwright |
| `client: browser`（旧 YAML） | Crawl4AI（默认，已安装时） |
| `client: browser`，crawl4ai **未**安装 | 旧 Playwright 实现 |
| `client: playwright`（如果未来新增） | 显式走 Playwright |

---

## 6. 依赖变更

```txt
# requirements.txt 新增
crawl4ai>=0.8.6

# 条件依赖（crawl4ai 安装时自动带上）
# playwright 仍保留用于降级
playwright>=1.40.0
```

---

## 7. 测试计划

### 7.1 单元测试

- `test_crawl4ai_crawler.py`：验证 Crawl4AI 渲染、markdown 输出、LLM extraction、降级逻辑
- `test_crawl4ai_field_extraction.py`：验证 `type: llm` / `type: markdown` 字段解析
- 修改 `test_crawl_browser.py`：保持 Playwright 降级路径测试

### 7.2 集成测试

- 用一个真实 JS 渲染页面（选一个公开的 SPA 站）验证端到端采集
- 验证 YAML `client: crawl4ai` 端到端通路

---

## 8. 实施步骤（草稿）

> 以下由 writing-plans 技能细化

1. 安装 crawl4ai 依赖，更新 requirements.txt
2. 新增 `crawl4ai_crawler.py` Crawl4AI 封装类
3. 重写 `BrowserCrawler.fetch()` 实现双路由（Crawl4AI / Playwright）
4. 新增 `BrowserCrawler.extract_fields()` 对 `type: llm` / `type: markdown` 的支持
5. 扩展 `RuleParser` 支持 `client: crawl4ai` 和 `extraction` 配置
6. 新增单测：`test_crawl4ai_crawler.py`、`test_crawl4ai_field_extraction.py`
7. 端到端集成测试（真实 JS 渲染页面）
8. 更新 `SPEC.md` 文档

---

## 9. 风险与注意点

| 风险 | 缓解 |
|---|---|
| LLM extraction 依赖外部 API 成本/可用性 | 通过 `source.extraction.enabled` 开关控制，默认关闭 |
| crawl4ai 与现有 playwright 依赖冲突 | 降级方案：client 非 crawl4ai 时用旧 Playwright |
| LLM extraction 解析结果格式不稳定 | 使用 Pydantic schema 约束输出结构 |
| markdown 输出与现有 parsers 层 CSS/XPath 不兼容 | markdown 输出作为独立 `type: markdown` field type，不影响现有解析 |

---

## 10. 规格自检

- [x] 占位符：无
- [x] 内部一致性：client 路由逻辑、source.type 关系、降级策略相互一致
- [x] 范围：聚焦 Crawl4AI 集成，不做无关重构
- [x] 模糊性：`client: browser` 默认走 Crawl4AI 已明确定义
