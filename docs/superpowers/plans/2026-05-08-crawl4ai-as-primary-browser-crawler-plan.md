# Crawl4AI 升级为浏览器渲染主力 — 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 Crawl4AI 打造成浏览器渲染默认主力，Playwright 降为轻量工具（resolve_url/screenshot）。核心改动：路由映射修复 + Crawl4AICrawler 补强 stealth/undetected/max_retries 能力。

**架构：** `client: browser` = `client: crawl4ai`（stealth 默认开启）；`client: playwright` 仅工具场景；`BrowserCrawler.resolve_url()` 直接委托 PlaywrightCrawler。

**技术栈：** crawl4ai 0.8.6, playwright, Python, pytest

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `APP/engine/engine/crawlers/crawl4ai_crawler.py` | Crawl4AI 封装：stealth 默认、undetected adapter、max_retries、proxy_config |
| `APP/engine/engine/crawl_browser.py` | BrowserCrawler：路由映射修复、`resolve_url` 单独路由到 Playwright |
| `APP/engine/engine/engine.py` | engine 默认 client 改为 `browser`，删除旧映射 |
| `APP/engine/engine/crawlers/playwright_crawler.py` | PlaywrightCrawler：保留 resolve_url/fetch_with_screenshot，不变 |
| `APP/engine/tests/test_crawl4ai_routing.py` | 新增：测试 client 路由正确性 |
| `APP/engine/tests/test_crawl4ai_stealth.py` | 新增：测试 stealth 默认、undetected 注入 |
| `APP/engine/tests/test_browser_crawler_resolve_url.py` | 新增：测试 resolve_url 走 PlaywrightCrawler |
| `APP/engine/rules/zhuzhiwen_performance/sogou_weixin.yaml` | 更新：client + render 配置 |

---

## 任务 1：重构 Crawl4AICrawler — stealth 默认 + undetected 支持

**文件：**
- 修改：`APP/engine/engine/crawlers/crawl4ai_crawler.py`

**依赖：** 无

- [ ] **步骤 1：编写失败的测试**

```python
# APP/engine/tests/test_crawl4ai_stealth.py
import pytest
from unittest.mock import patch, MagicMock

class TestCrawl4AIStealthDefaults:
    """验证 Crawl4AICrawler 的 stealth 默认行为"""

    def test_stealth_enabled_by_default(self):
        """stealth 默认开启，不传 config 时 BrowserConfig(enable_stealth=True)"""
        with patch('engine.crawlers.crawl4ai_crawler.AsyncWebCrawler') as mock_crawler:
            mock_instance = MagicMock()
            mock_crawler.return_value = mock_instance
            mock_result = MagicMock()
            mock_result.html = '<html></html>'
            mock_instance.arun.return_value = mock_result

            from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler
            pc = Crawl4AICrawler()
            # 不传 config，stealth 应默认 True
            with patch('engine.crawlers.crawl4ai_crawler.BrowserConfig') as MockBrowserConfig:
                pc.fetch('https://example.com')
                call_kwargs = MockBrowserConfig.call_args[1]
                assert call_kwargs.get('enable_stealth') == True

    def test_undetected_mode_injects_adapter(self):
        """当 config.undetected=True 时，使用 UndetectedAdapter"""
        with patch('engine.crawlers.crawl4ai_crawler.AsyncWebCrawler') as mock_crawler:
            mock_instance = MagicMock()
            mock_crawler.return_value = mock_instance
            mock_result = MagicMock()
            mock_result.html = '<html></html>'
            mock_instance.arun.return_value = mock_result

            from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler
            pc = Crawl4AICrawler()
            with patch('engine.crawlers.crawl4ai_crawler.UndetectedAdapter') as mock_adapter_cls:
                with patch('engine.crawlers.crawl4ai_crawler.AsyncPlaywrightCrawlerStrategy') as mock_strategy_cls:
                    mock_adapter = MagicMock()
                    mock_adapter_cls.return_value = mock_adapter
                    mock_strategy = MagicMock()
                    mock_strategy_cls.return_value = mock_strategy

                    pc.fetch('https://example.com', {'undetected': True})

                    # 验证 UndetectedAdapter 被实例化
                    mock_adapter_cls.assert_called_once()
                    # 验证 strategy 被创建时传入了 adapter
                    mock_strategy_cls.assert_called_once()
                    call_kwargs = mock_strategy_cls.call_args[1]
                    assert call_kwargs.get('browser_adapter') == mock_adapter

    def test_max_retries_passed_to_crawler_config(self):
        """max_retries 透传给 CrawlerRunConfig"""
        with patch('engine.crawlers.crawl4ai_crawler.AsyncWebCrawler') as mock_crawler:
            mock_instance = MagicMock()
            mock_crawler.return_value = mock_instance
            mock_result = MagicMock()
            mock_result.html = '<html></html>'
            mock_instance.arun.return_value = mock_result

            from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler
            pc = Crawl4AICrawler()
            with patch('engine.crawlers.crawl4ai_crawler.CrawlerRunConfig') as MockCrawlConfig:
                pc.fetch('https://example.com', {'max_retries': 3})
                call_kwargs = MockCrawlConfig.call_args[1]
                assert call_kwargs.get('max_retries') == 3
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_crawl4ai_stealth.py -v 2>&1
```

预期：FAIL（`enable_stealth` 当前默认为 False，`undetected` 未实现，`max_retries` 未透传）

- [ ] **步骤 3：重写 `crawl4ai_crawler.py`**

新的 `fetch()` 方法（保留 `_async_fetch` 异步实现不变，修改 config 构建逻辑）：

```python
# APP/engine/engine/crawlers/crawl4ai_crawler.py

# 在文件顶部添加新的 import
from crawl4ai import UndetectedAdapter
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy

class Crawl4AICrawler:
    def __init__(self):
        self._crawler = None

    def _get_crawler(self):
        if self._crawler is None:
            self._crawler = AsyncWebCrawler()
        return self._crawler

    def _build_browser_config(self, config: dict) -> BrowserConfig:
        user_agent = config.get("user_agent")
        browser_kwargs = {
            "headless": config.get("headless", True),
            "enable_stealth": config.get("stealth", True),  # 默认 True（原来是 False）
            "viewport_width": config.get("viewport_width", 1920),
            "viewport_height": config.get("viewport_height", 1080),
        }
        if user_agent:
            browser_kwargs["user_agent"] = user_agent
        return BrowserConfig(**browser_kwargs)

    def _build_crawler_config(self, config: dict) -> CrawlerRunConfig:
        want_markdown = config.get("markdown", True)
        return CrawlerRunConfig(
            wait_for=config.get("wait_for_selector"),
            wait_for_timeout=config.get("wait_for_timeout"),
            remove_forms=config.get("remove_forms", False),
            markdown_generator=DefaultMarkdownGenerator() if want_markdown else None,
            max_retries=config.get("max_retries", 0),
            proxy_config=self._build_proxy_config(config),
        )

    def _build_proxy_config(self, config):
        """Build ProxyConfig from render_config dict."""
        proxy = config.get("proxy")
        if not proxy:
            return None
        from crawl4ai import ProxyConfig
        return ProxyConfig(
            server=proxy,
            username=config.get("proxy_username"),
            password=config.get("proxy_password"),
        )

    async def _async_fetch(self, url: str, render_config: dict) -> str:
        config = render_config or {}
        browser_cfg = self._build_browser_config(config)

        # 构建 crawler_cfg
        crawler_cfg = self._build_crawler_config(config)

        # 如果 undetected=True，使用 UndetectedAdapter
        if config.get("undetected"):
            undetected_adapter = UndetectedAdapter()
            crawler_strategy = AsyncPlaywrightCrawlerStrategy(
                browser_config=browser_cfg,
                browser_adapter=undetected_adapter,
            )
            crawler = AsyncWebCrawler(
                crawler_strategy=crawler_strategy,
                config=browser_cfg,
            )
        else:
            crawler = self._get_crawler()
            result = await crawler.arun(url=url, config=crawler_cfg, browser_config=browser_cfg)

        result = await crawler.arun(url=url, config=crawler_cfg, browser_config=browser_cfg)
        want_markdown = config.get("markdown", True)
        if want_markdown:
            if hasattr(result, 'markdown') and result.markdown:
                if isinstance(result.markdown, str):
                    return result.markdown
                return str(result.markdown)
        return result.html

    def fetch(self, url: str, render_config: dict = None) -> str:
        return asyncio.get_event_loop().run_until_complete(self._async_fetch(url, render_config))
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_crawl4ai_stealth.py -v 2>&1
```

预期：PASS

- [ ] **步骤 5：Commit**

```bash
cd /root/info-collector && git add APP/engine/engine/crawlers/crawl4ai_crawler.py && git commit -m "feat(crawl4ai): enable stealth by default, add undetected mode and max_retries support" && git push origin master 2>&1
```

---

## 任务 2：修复 BrowserCrawler 路由映射 + resolve_url 单独路由

**文件：**
- 修改：`APP/engine/engine/crawl_browser.py`

**依赖：** 任务 1 完成

- [ ] **步骤 1：编写失败的测试**

```python
# APP/engine/tests/test_crawl4ai_routing.py
import pytest
from unittest.mock import patch, MagicMock

class TestBrowserCrawlerRouting:

    def test_browser_routes_to_crawl4ai(self):
        """client='browser' 应路由到 Crawl4AICrawler"""
        with patch('engine.crawlers.crawl4ai_crawler.AsyncWebCrawler') as mock_c4a:
            mock_instance = MagicMock()
            mock_c4a.return_value = mock_instance
            mock_result = MagicMock()
            mock_result.html = '<html>test</html>'
            mock_instance.arun.return_value = mock_result

            from engine.crawl_browser import BrowserCrawler
            bc = BrowserCrawler(client='browser')
            # 内部实现应为 Crawl4AICrawler
            assert bc._impl_type == 'browser'
            assert bc.client == 'browser'
            # 调用 fetch 应触发 Crawl4AI
            bc.fetch('https://example.com')
            mock_c4a.assert_called()

    def test_browser_alias_equals_crawl4ai(self):
        """client='browser' 和 client='crawl4ai' 行为一致"""
        with patch('engine.crawlers.crawl4ai_crawler.AsyncWebCrawler') as mock_c4a:
            mock_instance = MagicMock()
            mock_c4a.return_value = mock_instance
            mock_result = MagicMock()
            mock_result.html = '<html>test</html>'
            mock_instance.arun.return_value = mock_result

            from engine.crawl_browser import BrowserCrawler
            bc1 = BrowserCrawler(client='browser')
            bc2 = BrowserCrawler(client='crawl4ai')
            # 两者路由到的实现类型相同
            assert type(bc1._impl).__name__ == type(bc2._impl).__name__

    def test_resolve_url_uses_playwright(self):
        """resolve_url 应走 PlaywrightCrawler，不是 Crawl4AICrawler"""
        with patch('engine.crawlers.playwright_crawler.PlaywrightCrawler') as mock_pw_cls:
            mock_pw = MagicMock()
            mock_pw.resolve_url.return_value = 'https://mp.weixin.qq.com/s/xxx'
            mock_pw_cls.return_value = mock_pw

            from engine.crawl_browser import BrowserCrawler
            bc = BrowserCrawler(client='browser')
            # 即使 client 是 browser，resolve_url 也走 Playwright
            result = bc.resolve_url('https://weixin.sogou.com/link?url=...')
            mock_pw.resolve_url.assert_called_once()
            assert 'mp.weixin.qq.com' in result
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_crawl4ai_routing.py -v 2>&1
```

预期：FAIL（`client='browser'` 当前映射到 `PlaywrightCrawler`，resolve_url 逻辑未单独路由）

- [ ] **步骤 3：重写 `crawl_browser.py`**

```python
# APP/engine/engine/crawl_browser.py
"""Browser Crawler - handles JavaScript-rendered pages and anti-bot protection

Dual-routing BrowserCrawler that delegates to:
  - Crawl4AICrawler (for browser rendering with stealth/anti-bot)
  - PlaywrightCrawler (for lightweight tool use: resolve_url, screenshot)
"""
from typing import Optional
from .crawlers import PlaywrightCrawler, Crawl4AICrawler


class BrowserCrawler:
    """Dual-routing crawler: Crawl4AI for JS rendering, Playwright for tools.
    
    Args:
        client: "browser" (default=Crawl4AICrawler) or "playwright" (tool only)
               "browser" is an alias for "crawl4ai" (stealth + anti-bot enabled by default)
    """

    def __init__(self, client: str = None):
        self._client = client or "browser"
        self._impl: Optional[object] = None
        self._impl_type: Optional[str] = None
        self._ensure_impl()

    def _ensure_impl(self):
        """Lazy init based on current _client.
        
        Routing:
          - "browser"  → Crawl4AICrawler (JS rendering + stealth, default)
          - "crawl4ai" → Crawl4AICrawler (same as browser)
          - "playwright" → PlaywrightCrawler (resolve_url, screenshot tool)
        """
        if self._impl_type != self._client:
            # "browser" is an alias for "crawl4ai" (JS rendering + stealth)
            if self._client == "browser" or self._client == "crawl4ai":
                self._impl = Crawl4AICrawler()
            elif self._client == "playwright":
                self._impl = PlaywrightCrawler()
            else:
                raise ValueError(f"Unknown client: {self._client}")
            self._impl_type = self._client

    def switch_client(self, client: str):
        """Switch crawler implementation (closes old one first)"""
        if self._client == client:
            return
        if self._impl is not None:
            self._impl.close()
        self._client = client
        self._impl = None
        self._impl_type = None
        self._ensure_impl()

    @property
    def client(self) -> str:
        """Current client type."""
        return self._client

    def fetch(self, url: str, render_config: dict = None) -> str:
        """Fetch page using browser, return HTML after JS rendering.
        
        render_config keys:
            stealth: bool (default True) — enable StealthAdapter
            undetected: bool (default False) — enable UndetectedAdapter (for heavy anti-bot)
            headless: bool (default True)
            user_agent: str
            wait_for_selector: str
            wait_for_timeout: int (ms)
            viewport_width: int (default 1920)
            viewport_height: int (default 1080)
            max_retries: int (default 0) — anti-bot escalation rounds
            proxy: str — proxy server URL
            extra_headers: dict
        """
        return self._impl.fetch(url, render_config)

    def fetch_with_screenshot(self, url: str, render_config: dict = None) -> tuple:
        """Fetch page and return (html, screenshot_path). For debugging."""
        return self._impl.fetch_with_screenshot(url, render_config)

    def resolve_url(self, url: str, render_config: dict = None, timeout: int = 15000) -> str:
        """Resolve a URL through browser redirects, returning the final URL.
        
        URL navigation doesn't need stealth — always uses PlaywrightCrawler directly.
        """
        # Always use PlaywrightCrawler for URL resolution (lightweight, no stealth needed)
        pw = PlaywrightCrawler()
        return pw.resolve_url(url, render_config, timeout)

    def parse_items(self, html_content: str, items_path: str) -> list:
        """Parse items from browser-rendered HTML using CSS/XPath/regex extraction."""
        return self._impl.parse_items(html_content, items_path)

    def extract_attr(self, html_content: str, xpath: str, attr: str) -> str:
        """Extract attribute from HTML element."""
        return self._impl.extract_attr(html_content, xpath, attr)

    def extract_text(self, html_content: str, xpath: str) -> str:
        """Extract text content from HTML element."""
        return self._impl.extract_text(html_content, xpath)

    def extract_fields(self, html_content: str, field_defs: list) -> dict:
        """Extract fields from HTML based on field definitions"""
        return self._impl.extract_fields(html_content, field_defs)

    def extract_with_llm(self, url: str, prompt: str, schema: dict = None, strategy: str = "llm", render_config: dict = None):
        """Extract structured content using LLM (only supported by crawl4ai client)."""
        if not hasattr(self._impl, 'extract_with_llm'):
            raise NotImplementedError(
                f"extract_with_llm is not supported by {self._client} client. "
                "Use 'browser' or 'crawl4ai' client to enable LLM extraction."
            )
        return self._impl.extract_with_llm(url, prompt, schema, strategy, render_config)

    def close(self):
        """Cleanup crawler resources"""
        if self._impl is not None:
            self._impl.close()
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_crawl4ai_routing.py -v 2>&1
```

预期：PASS

- [ ] **步骤 5：Commit**

```bash
cd /root/info-collector && git add APP/engine/engine/crawl_browser.py && git commit -m "refactor(crawl_browser): route 'browser' to Crawl4AI, move resolve_url to PlaywrightCrawler" && git push origin master 2>&1
```

---

## 任务 3：更新 engine.py 默认 client

**文件：**
- 修改：`APP/engine/engine/engine.py`

**依赖：** 任务 2 完成

- [ ] **步骤 1：确认当前 engine 默认 client**

```bash
grep -n "BrowserCrawler(client=" /root/info-collector/APP/engine/engine/engine.py
```

预期：第 65 行 `BrowserCrawler(client="playwright")`

- [ ] **步骤 2：修改 engine.py 第 65 行**

```python
# 原：
self.browser_crawler = BrowserCrawler(client="playwright")
# 改为：
self.browser_crawler = BrowserCrawler(client="browser")
```

同时删除 `_ensure_impl()` 中对 `"browser"` 的旧映射（已由 `crawl_browser.py` 统一处理）。

- [ ] **步骤 3：验证语法**

```bash
cd /root/info-collector/APP/engine && .venv/bin/python -m py_compile engine/engine.py && echo "Syntax OK"
```

预期：输出 "Syntax OK"

- [ ] **步骤 4：Commit**

```bash
cd /root/info-collector && git add APP/engine/engine/engine.py && git commit -m "chore(engine): default browser_crawler client to 'browser' (Crawl4AI)" && git push origin master 2>&1
```

---

## 任务 4：更新 sogou_weixin.yaml 规则

**文件：**
- 修改：`APP/engine/rules/zhuzhiwen_performance/sogou_weixin.yaml`

**依赖：** 任务 1、2 完成

- [ ] **步骤 1：读取当前 YAML**

```bash
cat /root/info-collector/APP/engine/rules/zhuzhiwen_performance/sogou_weixin.yaml
```

- [ ] **步骤 2：更新 client 和 render 配置**

将 `client: browser`（已是 browser）确认渲染配置，加入 `stealth: true`（显式，默认值可省略但写出来更清晰），`undetected: false`。

- [ ] **步骤 3：验证 YAML 语法**

```bash
cd /root/info-collector/APP/engine && .venv/bin/python -c "import yaml; yaml.safe_load(open('rules/zhuzhiwen_performance/sogou_weixin.yaml'))" && echo "YAML OK"
```

预期：输出 "YAML OK"

- [ ] **步骤 4：Commit**

```bash
cd /root/info-collector && git add APP/engine/rules/zhuzhiwen_performance/sogou_weixin.yaml && git commit -m "feat(sogou_weixin): update to use Crawl4AI with stealth enabled" && git push origin master 2>&1
```

---

## 任务 5：集成验证 — 真实网络测试

**文件：** 无（验证测试）

**依赖：** 任务 1-4 全部完成

- [ ] **步骤 1：对 sogou.weixin.com 运行采集（debug 模式）**

```bash
cd /root/info-collector/APP/engine && .venv/bin/python -c "
import logging
logging.basicConfig(level=logging.DEBUG)
from engine.engine import InfoCollectorEngine
engine = InfoCollectorEngine()
rule = engine.load_rule('rules/zhuzhiwen_performance/sogou_weixin.yaml')
items = engine.crawl(rule)
print(f'Crawled {len(items)} items')
if items:
    print(f'First URL: {items[0].get(\"url\", \"NO URL\")}')
    print(f'Contains mp.weixin: {\"mp.weixin.qq.com\" in items[0].get(\"url\", \"\")}')
engine.close()
" 2>&1 | tail -30
```

预期：
- 不报 antispider 页面
- 能拿到 `https://mp.weixin.qq.com/s/...` 格式的真实 URL
- 或至少能看到 `weixin.sogou.com/antispider` 不再出现

- [ ] **步骤 2：如果 antispider 仍然出现，启用 undetected 模式**

修改 `sogou_weixin.yaml`，加入 `undetected: true`，重新运行测试。

- [ ] **步骤 3：Commit 最终结果**

无论成功与否，commit 本次测试结果（可含注释说明当前 sogou 反爬状态）。

```bash
cd /root/info-collector && git add -A && git commit -m "test(sogou_weixin): integration test with Crawl4AI stealth" && git push origin master 2>&1
```

---

## 自检清单

- [ ] 规格第 1-5 节全部有对应任务覆盖
- [ ] 无占位符（TODO/待定/后续实现）
- [ ] 任务顺序：1→2→3→4→5（无循环依赖）
- [ ] 每个任务有独立的测试文件
- [ ] 每个任务有独立的 commit
- [ ] 类型/方法名在任务间保持一致
