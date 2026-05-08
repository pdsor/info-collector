# Crawl4AI 作为浏览器渲染主力方案

**状态：** 已批准
**日期：** 2026-05-08
**目标：** 让 Crawl4AI 成为所有浏览器渲染场景的默认主力，Playwright 降为轻量工具

---

## 背景

info-collector 的采集目标分三类：
- **API 类**：直接 HTTP 请求，任意客户端均可
- **HTML 类**：requests + lxml，无需渲染
- **浏览器类**：JS 渲染 + 反爬，**期望统一走 Crawl4AI**

当前问题：
1. `client: browser` 实际路由到 `PlaywrightCrawler`，而非 `Crawl4AICrawler`
2. `Crawl4AICrawler` 的 `enable_stealth` 默认为 `False`，未发挥反爬能力
3. `UndetectedAdapter`、`max_retries`、`proxy_config` 等核心功能均未支持
4. `resolve_url` 写在 `PlaywrightCrawler` 里是对的（URL 导航不需要 stealth），但没有清晰的分层

---

## 架构分层

```
engine.py crawl()
    │
    ├── source.type="api"  → APICrawler（直接 HTTP）
    │
    ├── source.type="html" → HTMLCrawler（requests + lxml）
    │
    └── source.type="browser" → _crawl_browser()
                                     │
                                     ├── client="browser"  → Crawl4AICrawler (默认)
                                     │                          ├── StealthAdapter (默认启用)
                                     │                          ├── UndetectedAdapter (按配置)
                                     │                          └── max_retries escalation
                                     │
                                     └── client="playwright" → PlaywrightCrawler (轻量工具)
                                                                    ├── resolve_url()
                                                                    └── fetch_with_screenshot()
```

---

## 路由映射规则

| YAML `client` 值 | 实际 crawler | 用途 |
|---|---|---|
| `browser` | Crawl4AICrawler + stealth | **默认**，JS 渲染来源统一走这个 |
| `crawl4ai` | Crawl4AICrawler | 显式指定，效果同 `browser` |
| `playwright` | PlaywrightCrawler | 仅工具场景（resolve_url / screenshot） |

---

## Crawl4AICrawler 升级

**文件：** `APP/engine/engine/crawlers/crawl4ai_crawler.py`

### 1. stealth 默认开启

```python
browser_kwargs = {
    "headless": config.get("headless", True),
    "enable_stealth": config.get("stealth", True),  # 默认 True（原来为 False）
    ...
}
```

### 2. undetected 模式

当 `config.get("undetected") == True` 时，通过 `AsyncPlaywrightCrawlerStrategy` 注入 `UndetectedAdapter`：

```python
from crawl4ai import UndetectedAdapter
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy

if config.get("undetected"):
    undetected_adapter = UndetectedAdapter()
    strategy = AsyncPlaywrightCrawlerStrategy(
        browser_config=browser_cfg,
        browser_adapter=undetected_adapter
    )
    # 用 strategy 创建 crawler
```

### 3. max_retries 支持

透传给 `CrawlerRunConfig`：

```python
CrawlerRunConfig(
    max_retries=config.get("max_retries", 0),
    proxy_config=self._build_proxy_config(config),
    ...
)
```

### 4. proxy_config 支持

```python
from crawl4ai import ProxyConfig

def _build_proxy_config(self, config):
    proxy = config.get("proxy")
    if not proxy:
        return None
    return ProxyConfig(server=proxy, username=config.get("proxy_username"), password=config.get("proxy_password"))
```

### 5. resolve_url 不在 Crawl4AICrawler 实现

`BrowserCrawler.resolve_url()` 直接路由到 `PlaywrightCrawler`，因为 URL 导航只需 `wait_until="commit"`，不需要 stealth 能力。

---

## BrowserCrawler 修改

**文件：** `APP/engine/engine/crawl_browser.py`

### 1. `_ensure_impl()` 重构

```python
def _ensure_impl(self):
    # "browser" 是 crawl4ai 的别名（JS 渲染 + 反爬）
    if self._client == "browser":
        effective = "crawl4ai"
    else:
        effective = self._client

    if effective == "playwright":
        self._impl = PlaywrightCrawler()
    elif effective == "crawl4ai":
        self._impl = Crawl4AICrawler()
    else:
        raise ValueError(f"Unknown client: {self._client}")
    self._impl_type = self._client
```

### 2. `resolve_url()` 单独路由

```python
def resolve_url(self, url, render_config=None, timeout=15000):
    """URL 导航走 Playwright，不需要 stealth"""
    from .crawlers import PlaywrightCrawler
    pw = PlaywrightCrawler()
    return pw.resolve_url(url, render_config, timeout)
```

---

## engine.py 修改点

**文件：** `APP/engine/engine/engine.py`

1. **第 65 行**：`BrowserCrawler(client="playwright")` → `BrowserCrawler(client="browser")`（默认走 Crawl4AI）
2. **第 29 行**：删除 `"browser" → "playwright"` 的旧映射（由 `crawl_browser.py` 接管）
3. **`_crawl_browser()` 第 257-260 行**：resolve_url 调用逻辑不变，但 `BrowserCrawler.resolve_url()` 已直接路由到 Playwright

---

## YAML 规则示例

```yaml
source:
  type: browser
  client: browser              # 等同于 crawl4ai，默认走 stealth
  url: https://weixin.sogou.com/weixin?type=2&query=大衣哥
  render:
    stealth: true              # 默认 True，可省略
    undetected: false           # 默认 False，搜狗用基础 stealth
    headless: true
    wait_for_timeout: 5000
    # max_retries: 3           # 可选，anti-bot escalation
    # proxy: http://proxy:8080 # 可选

list:
  items_path: "css:.news-list li"
  fields:
    - name: url
      type: element_href
      resolve_url: true        # 通过 PlaywrightCrawler 跟随重定向
    - name: title
      type: element_text
```

---

## 已知限制

- `UndetectedAdapter` 的效果因网站而异，搜狗的反爬可能需要真实浏览器 cookie 才能完全绕过
- `resolve_url` 独立使用 PlaywrightCrawler，与主采集流程共享同一个 browser instance 时需注意上下文隔离

---

## 测试策略

### 单元测试（mock 网络）

1. `test_crawl4ai_routing.py`：验证 `client: browser` 路由到 `Crawl4AICrawler`
2. `test_crawl4ai_stealth.py`：验证 stealth 默认开启、`undetected` 注入逻辑
3. `test_browser_crawler_resolve_url.py`：验证 `resolve_url` 走 PlaywrightCrawler

### 集成测试（真实网络）

1. 对 `https://weixin.sogou.com` 跑 `client: browser` + `stealth: true`，验证非 antispider 页面返回
2. 对比 `client: crawl4ai` 和 `client: playwright` 的 sogou 采集结果

---

## 改动文件清单

| 文件 | 操作 |
|---|---|
| `engine/crawlers/crawl4ai_crawler.py` | 重构：stealth 默认、undetected、max_retries、proxy_config |
| `engine/crawl_browser.py` | 重构：路由映射、`resolve_url` 单独路由 |
| `engine/engine.py` | 修改：默认 client + 删除旧映射 |
| `tests/test_crawl4ai_routing.py` | 新增 |
| `tests/test_crawl4ai_stealth.py` | 新增 |
| `rules/zhuzhiwen_performance/sogou_weixin.yaml` | 更新：client + render 配置 |
