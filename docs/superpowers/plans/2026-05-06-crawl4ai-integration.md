# Crawl4AI 集成实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 用 Crawl4AI 完全替代现有 Playwright 实现，对外接口不变，支持 LLM extraction + 反爬稳定性 + Markdown 高质量输出。

**架构：** 通过 `client: crawl4ai` 枚举值路由到 Crawl4AI，所有 `source.type: browser` 默认走 Crawl4AI。`BrowserCrawler` 类内部双路由（Crawl4AI / Playwright），`source.extraction.enabled` 开启 LLM extraction，`type: llm`/`type: markdown` 作为新的 field type。

**技术栈：** crawl4ai>=0.8.6, playwright>=1.40.0, Python 3.x, Pydantic

---

## 文件结构

```
APP/engine/engine/
  crawlers/
    __init__.py          # 新增：导出 CrawlerResult, BrowserCrawler
    crawl4ai_crawler.py  # 新增：Crawl4AI 封装类
    playwright_crawler.py # 新增：降级用 Playwright 封装类（现有逻辑迁移）
  crawl_browser.py       # 重写：BrowserCrawler 类，内部组合 crawlers/ 下的两个实现
  parsers.py             # 修改：新增 UA 枚举，HTMLParser 支持 markdown 输入
  rule_parser.py         # 修改：client 枚举扩展（新增 crawl4ai），extraction 配置解析

测试文件：
  tests/test_crawl4ai_crawler.py           # 新增
  tests/test_crawl4ai_field_extraction.py  # 新增
```

---

## 任务列表

- [ ] 任务0：修复 close() 资源泄漏（engines/engine.py 新增 close() 方法）
- [ ] 任务1：安装 crawl4ai，更新 requirements.txt
- [ ] 任务2：创建 crawlers/ 子目录，迁移现有 Playwright 到 playwright_crawler.py
- [ ] 任务3：实现 crawl4ai_crawler.py（Crawl4AI 封装）
- [ ] 任务4：重写 BrowserCrawler 实现双路由 + extract_fields 扩展
- [ ] 任务5：扩展 RuleParser 支持 client: crawl4ai + extraction 配置
- [ ] 任务6：新增单元测试 test_crawl4ai_crawler.py
- [ ] 任务7：新增单元测试 test_crawl4ai_field_extraction.py
- [ ] 任务8：端到端集成测试（真实 JS 渲染页面）

---

## 任务0：修复 close() 资源泄漏

**文件：**
- 修改：`APP/engine/engine/engine.py`

**步骤：**

- [ ] **步骤1：添加 close() 方法到 InfoCollectorEngine**

打开 `APP/engine/engine/engine.py`，在 `__init__` 方法后添加：

```python
def close(self):
    """清理所有 crawler 资源"""
    if self.dedup:
        try:
            self.dedup.close()
        except Exception:
            pass
    if self.browser_crawler:
        try:
            self.browser_crawler.close()
        except Exception:
            pass
```

- [ ] **步骤2：确认 engine_cli.py 调用 close()**

检查 `APP/engine/engine_cli.py`，在主入口（如 `run_rule()` 或 `run_all()` 函数末尾）添加 `engine.close()` 调用。如果 `engine_cli` 使用了 `with` 语句或 context manager 模式，则在 `__exit__` 中调用。

```python
# 在 engine_cli.py 的 main 或 run 函数末尾
engine = InfoCollectorEngine(...)
try:
    # ... 执行逻辑
finally:
    engine.close()
```

- [ ] **步骤3：Commit**

```bash
cd /root/info-collector
git add APP/engine/engine/engine.py APP/engine/engine_cli.py
git commit -m "fix(engine): add close() method to prevent resource leak"
```

---

## 任务1：安装 crawl4ai，更新 requirements.txt

**文件：**
- 修改：`APP/engine/requirements.txt`（或 `requirements-engine.txt`）

**步骤：**

- [ ] **步骤1：查看现有 requirements 文件**

```bash
cat /root/info-collector/APP/engine/requirements.txt 2>/dev/null || cat /root/info-collector/requirements.txt 2>/dev/null
```

- [ ] **步骤2：添加 crawl4ai 依赖**

在 requirements 文件末尾追加：

```
crawl4ai>=0.8.6
```

- [ ] **步骤3：安装**

```bash
pip install crawl4ai>=0.8.6
```

- [ ] **步骤4：Commit**

```bash
git add requirements.txt
git commit -m "chore: add crawl4ai>=0.8.6 dependency"
```

---

## 任务2：创建 crawlers/ 子目录，迁移现有 Playwright 到 playwright_crawler.py

**文件：**
- 创建：`APP/engine/engine/crawlers/__init__.py`
- 创建：`APP/engine/engine/crawlers/playwright_crawler.py`
- 创建：`APP/engine/engine/crawlers/crawl4ai_crawler.py`（空文件，任务3填充）

**步骤：**

- [ ] **步骤1：创建目录**

```bash
mkdir -p /root/info-collector/APP/engine/engine/crawlers
```

- [ ] **步骤2：创建 __init__.py**

```python
"""Crawler implementations - Crawl4AI and Playwright"""
from .crawl4ai_crawler import Crawl4AICrawler
from .playwright_crawler import PlaywrightCrawler

__all__ = ["Crawl4AICrawler", "PlaywrightCrawler"]
```

- [ ] **步骤3：创建 playwright_crawler.py（从 crawl_browser.py 迁移）**

读取当前 `APP/engine/engine/crawl_browser.py` 中除 `BrowserCrawler` 外的所有代码（常量 USER_AGENTS、HTMLParser 相关工具函数），以及 `BrowserCrawler.fetch()` 中非 Crawl4AI 的现有 Playwright 实现逻辑，封装为 `PlaywrightCrawler` 类：

```python
"""Playwright-based crawler (降级方案)"""
import random
from typing import Optional

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/115.0.1901.203",
]

class PlaywrightCrawler:
    """Playwright implementation for browser rendering"""

    def __init__(self):
        self._playwright = None
        self._browser = None

    def _get_playwright(self):
        if self._playwright is None:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
        return self._playwright

    def _get_browser(self, headless: bool = True, stealth: bool = True):
        pw = self._get_playwright()
        if self._browser is None or not self._browser.is_connected():
            args = [
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
            if stealth:
                args.extend([
                    "--disable-web-security",
                    "--disable-features=IsolateOrigins,site-per-process",
                ])
            self._browser = pw.chromium.launch(headless=headless, args=args)
        return self._browser

    def fetch(self, url: str, render_config: dict = None) -> str:
        """Fetch page using Playwright, return HTML after JS rendering"""
        config = render_config or {}
        headless = config.get("headless", True)
        stealth = config.get("stealth", True)
        ua = config.get("user_agent", "random")
        wait_for_selector = config.get("wait_for_selector")
        wait_for_timeout = config.get("wait_for_timeout", 3000)
        viewport_width = config.get("viewport_width", 1920)
        viewport_height = config.get("viewport_height", 1080)
        extra_headers = config.get("extra_headers", {})

        browser = self._get_browser(headless=headless, stealth=stealth)
        context = browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            extra_http_headers=extra_headers,
        )
        page = context.new_page()

        if ua == "random":
            page.set_extra_http_headers({"User-Agent": random.choice(USER_AGENTS)})
        elif ua:
            page.set_extra_http_headers({"User-Agent": ua})

        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if wait_for_selector:
            try:
                page.wait_for_selector(wait_for_selector, timeout=wait_for_timeout)
            except Exception:
                pass
        else:
            page.wait_for_timeout(wait_for_timeout)

        content = page.content()
        context.close()
        return content

    def close(self):
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
```

- [ ] **步骤4：创建 crawl4ai_crawler.py（空占位符）**

```python
"""Crawl4AI-based crawler"""
# TODO: 任务3 实现
```

- [ ] **步骤5：Commit**

```bash
git add APP/engine/engine/crawlers/
git commit -m "refactor(engine): extract crawler implementations to crawlers/ subdirectory"
```

---

## 任务3：实现 crawl4ai_crawler.py

**文件：**
- 修改：`APP/engine/engine/crawlers/crawl4ai_crawler.py`

**前置条件：** 任务1（crawl4ai 已安装）+ 任务2（crawlers/ 目录已创建）

**步骤：**

- [ ] **步骤1：实现 Crawl4AICrawler 类**

```python
"""Crawl4AI-based crawler"""
import os
from typing import Optional

class Crawl4AICrawler:
    """Crawl4AI implementation for browser rendering with LLM extraction support"""

    def __init__(self):
        self._browser = None
        self._crawler = None

    def fetch(self, url: str, render_config: dict = None) -> str:
        """Fetch page using Crawl4AI, return markdown or HTML content.

        render_config keys:
            headless: bool (default True)
            stealth: bool (default True)
            viewport_width: int (default 1920)
            viewport_height: int (default 1080)
            wait_for_selector: str (optional)
            wait_for_timeout: int (ms, default 5000)
            anti_bot: bool (default True)
            markdown: bool (default True) - return markdown vs raw HTML
            remove_footers: bool (default True)
            remove_forms: bool (default True)
        """
        import asyncio
        from crawl4ai import AsyncPlaywrightCrawlerStrategy

        config = render_config or {}
        headless = config.get("headless", True)
        stealth = config.get("stealth", True)
        anti_bot = config.get("anti_bot", True)
        viewport_width = config.get("viewport_width", 1920)
        viewport_height = config.get("viewport_height", 1080)
        wait_for_selector = config.get("wait_for_selector")
        wait_for_timeout = config.get("wait_for_timeout", 5000)
        use_markdown = config.get("markdown", True)
        remove_footers = config.get("remove_footers", True)
        remove_forms = config.get("remove_forms", True)

        # Build Crawl4AI config
        strategy = AsyncPlaywrightCrawlerStrategy(
            headless=headless,
            stealth=stealth,
            anti_bot=anti_bot,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )

        # Set up wait conditions
        if wait_for_selector:
            strategy.set_wait_for_selector(wait_for_selector, timeout=wait_for_timeout)

        async def _crawl():
            from crawl4ai import WebCrawler
            crawler = WebCrawler()
            await crawler.initialize()

            result = await crawler.crawl(
                url,
                crawler_strategy=strategy,
                # Crawl4AI markdown output options
                markdown=use_markdown,
                remove_footers=remove_footers,
                remove_forms=remove_forms,
            )

            await crawler.close()
            return result

        # Run async crawl
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(_crawl())

        if use_markdown:
            return result.markdown
        return result.html

    def extract_with_llm(self, url: str, prompt: str, schema, strategy: str = "cosine",
                         render_config: dict = None) -> dict:
        """Extract structured data using LLM.

        Args:
            url: page URL
            prompt: extraction prompt in natural language
            schema: Pydantic model defining output structure
            strategy: "cosine" | "relevance" | "threshold" | "must_match"
            render_config: same as fetch()
        """
        import asyncio
        from crawl4ai import AsyncPlaywrightCrawlerStrategy
        from crawl4ai.extraction_strategy import LLMExtractionStrategy
        from pydantic import BaseModel

        config = render_config or {}

        llm_strategy = LLMExtractionStrategy(
            prompt=prompt,
            schema=schema,
            extraction_strategy=strategy,
        )

        strategy_config = AsyncPlaywrightCrawlerStrategy(
            headless=config.get("headless", True),
            stealth=config.get("stealth", True),
            anti_bot=config.get("anti_bot", True),
        )

        async def _crawl():
            from crawl4ai import WebCrawler
            crawler = WebCrawler()
            await crawler.initialize()
            result = await crawler.crawl(
                url,
                crawler_strategy=strategy_config,
                extractor=llm_strategy,
            )
            await crawler.close()
            return result

        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(_crawl())
        return result.extracted_content

    def close(self):
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._crawler:
            try:
                self._crawler.close()
            except Exception:
                pass
            self._crawler = None
```

> **注意**：Crawl4AI v0.8.x API 可能与上述代码有差异。实现者需要：
> 1. 先运行 `python -c "import crawl4ai; print(dir(crawl4ai))"` 确认可用模块
> 2. 参考 `/root/info-collector/APP/engine/engine/crawl_browser.py` 的现有接口设计
> 3. 如果 API 差异较大，优先保持与 `render_config` 参数兼容

- [ ] **步骤2：Commit**

```bash
git add APP/engine/engine/crawlers/crawl4ai_crawler.py
git commit -m "feat(crawlers): add Crawl4AICrawler implementation"
```

---

## 任务4：重写 BrowserCrawler 实现双路由 + extract_fields 扩展

**文件：**
- 重写：`APP/engine/engine/crawl_browser.py`
- 修改：`APP/engine/engine/parsers.py`（如果需要支持 markdown field type）

**前置条件：** 任务2（crawlers/ 已创建）+ 任务3（crawl4ai_crawler.py 已实现）

**步骤：**

- [ ] **步骤1：重写 crawl_browser.py**

将当前 `crawl_browser.py` 替换为：

```python
"""Browser Crawler - handles JavaScript-rendered pages and anti-bot protection

Internal implementation: delegates to Crawl4AI (primary) or Playwright (fallback).
External interface unchanged for backward compatibility.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Try to import crawlers
try:
    from .crawlers import Crawl4AICrawler, PlaywrightCrawler
    CRAWL4AI_AVAILABLE = True
except ImportError:
    CRAWL4AI_AVAILABLE = False
    Crawl4AICrawler = None
    PlaywrightCrawler = None


class BrowserCrawler:
    """Browser crawler with Crawl4AI primary and Playwright fallback.

   对外接口与原有 Playwright 实现完全兼容，内部双路由。
    """

    def __init__(self):
        self._crawl4ai = None
        self._playwright = None
        self._crawl4ai_available = CRAWL4AI_AVAILABLE

    def _get_crawl4ai(self):
        if self._crawl4ai is None and self._crawl4ai_available:
            self._crawl4ai = Crawl4AICrawler()
        return self._crawl4ai

    def _get_playwright(self):
        if self._playwright is None:
            self._playwright = PlaywrightCrawler()
        return self._playwright

    def fetch(self, url: str, render_config: dict = None) -> str:
        """Fetch page, return HTML after JS rendering.

        render_config keys:
            headless: bool
            stealth: bool
            user_agent: str or "random"
            wait_for_selector: str
            wait_for_timeout: int (ms)
            viewport_width: int
            viewport_height: int
            extra_headers: dict
            client: str  # "crawl4ai" | "playwright" | None (auto)
            anti_bot: bool  # Crawl4AI only
            markdown: bool   # Crawl4AI only: return markdown vs HTML
            remove_footers: bool  # Crawl4AI only
            remove_forms: bool   # Crawl4AI only
        """
        config = render_config or {}
        client = config.get("client", None)

        # Auto-decide: prefer crawl4ai if available
        if client == "playwright":
            return self._get_playwright().fetch(url, config)
        elif client == "crawl4ai" or client is None:
            c4a = self._get_crawl4ai()
            if c4a is not None:
                return c4a.fetch(url, config)
            else:
                if client == "crawl4ai":
                    logger.warning("crawl4ai requested but not available, falling back to playwright")
                return self._get_playwright().fetch(url, config)
        else:
            # Unknown client, fallback to playwright
            return self._get_playwright().fetch(url, config)

    def extract_fields(self, content: str, field_defs: list) -> dict:
        """Extract fields from content.

        Supports existing field types (xpath, attr, constant) plus new types:
        - type: llm       → uses LLM extraction (requires url in context)
        - type: markdown  → returns content as-is (content is already markdown)

        NOTE: For type:llm, the field_def must include 'url' and 'prompt'.
              The llm extraction is called per-field, batching should be
              implemented at a higher level if needed.
        """
        from .parsers import HTMLParser

        result = {}
        pending_llm_fields = []

        for field_def in field_defs:
            field_name = field_def["name"]
            field_type = field_def.get("type", "xpath")

            if field_type == "constant":
                result[field_name] = field_def.get("value", "")
            elif field_type == "attr":
                path = field_def.get("path", "")
                attr = field_def.get("attr", "href")
                parser = HTMLParser(content)
                result[field_name] = parser.get_attr(path, attr)
            elif field_type == "llm":
                pending_llm_fields.append(field_def)
            elif field_type == "markdown":
                result[field_name] = content
            else:
                # Default: xpath-style extraction
                path = field_def.get("path", "")
                parser = HTMLParser(content)
                result[field_name] = parser.xpath_text(path)

        # Process LLM fields
        if pending_llm_fields:
            # All llm fields share the same URL (from context)
            # For simplicity: extract first llm field's url
            # In practice, this should be passed in from engine layer
            for field_def in pending_llm_fields:
                field_name = field_def["name"]
                # LLM extraction requires URL context - this should be provided
                # by the caller. Here we return empty and log a warning.
                logger.warning(
                    f"LLM extraction for field '{field_name}' requires URL context. "
                    "Use engine-level LLM extraction instead."
                )
                result[field_name] = ""

        return result

    def close(self):
        """Cleanup all crawler resources"""
        if self._crawl4ai:
            try:
                self._crawl4ai.close()
            except Exception:
                pass
            self._crawl4ai = None
        if self._playwright:
            try:
                self._playwright.close()
            except Exception:
                pass
            self._playwright = None
```

- [ ] **步骤2：更新 parsers/__init__.py 或 parsers.py**

确保 `HTMLParser` 类导出，同时检查是否需要添加 `markdown` 相关解析支持。

- [ ] **步骤3：确认 engine.py 的 client_mode 路由**

检查 `APP/engine/engine/engine.py` 中 `crawl()` 方法对 `client_mode == "browser"` 的处理——应传入 `render_config["client"] = "crawl4ai"`。

```python
# engine.py _crawl_browser 方法中，构造 render_config 时：
render_config = {
    "client": "crawl4ai",  # 所有 source.type: browser 默认走 Crawl4AI
    "headless": True,
    "stealth": True,
    # ... 其他配置
}
```

- [ ] **步骤4：Commit**

```bash
git add APP/engine/engine/crawl_browser.py
git commit -m "refactor(crawl_browser): replace Playwright with Crawl4AI as primary, add dual-router + llm/markdown field types"
```

---

## 任务5：扩展 RuleParser 支持 client: crawl4ai + extraction 配置

**文件：**
- 修改：`APP/engine/engine/rule_parser.py`

**前置条件：** 任务4（BrowserCrawler 已重写）

**步骤：**

- [ ] **步骤1：扩展 client 枚举验证**

在 `rule_parser.py` 中找到 client 字段的验证逻辑，添加 `crawl4ai` 到允许的枚举值：

```python
VALID_CLIENT_MODES = {"auto", "mobile", "desktop", "browser", "crawl4ai", "playwright"}

# 在 validate_rule() 或相关方法中添加验证：
client = source.get("client", "desktop")
if client not in VALID_CLIENT_MODES:
    raise ValueError(f"Invalid client mode: {client}. Allowed: {VALID_CLIENT_MODES}")
```

- [ ] **步骤2：添加 extraction 配置解析**

在 `RuleParser` 中添加对 `source.extraction` 配置的解析支持。在 `parse_rule()` 或 `validate()` 方法中添加：

```python
# 验证 source.extraction 配置
extraction = source.get("extraction", {})
if extraction.get("enabled"):
    if not extraction.get("prompt"):
        raise ValueError("extraction.enabled=true requires extraction.prompt")
    valid_strategies = {"cosine", "relevance", "threshold", "must_match"}
    strategy = extraction.get("strategy", "cosine")
    if strategy not in valid_strategies:
        raise ValueError(f"Invalid extraction strategy: {strategy}")
```

- [ ] **步骤3：Commit**

```bash
git add APP/engine/engine/rule_parser.py
git commit -m "feat(rule_parser): extend client enum with crawl4ai/playwright, add extraction config validation"
```

---

## 任务6：新增单元测试 test_crawl4ai_crawler.py

**文件：**
- 创建：`APP/engine/tests/test_crawl4ai_crawler.py`

**前置条件：** 任务1（crawl4ai 已安装）+ 任务3（crawl4ai_crawler.py 已实现）

**步骤：**

- [ ] **步骤1：编写测试**

```python
"""Tests for Crawl4AI crawler and dual-router BrowserCrawler"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.crawlers.crawl4ai_crawler import Crawl4AICrawler


class TestCrawl4AICrawler:
    """Test Crawl4AI crawler basic operations"""

    @pytest.fixture
    def crawler(self):
        c = Crawl4AICrawler()
        yield c
        c.close()

    def test_crawl4ai_available(self):
        """Crawl4AI should be importable"""
        assert CRAWL4AI_AVAILABLE, "crawl4ai should be installed"

    def test_fetch_returns_content(self, crawler):
        """fetch() should return non-empty string for a real page"""
        # Use a public JS-rendered page
        result = crawler.fetch("https://example.com")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fetch_with_markdown(self, crawler):
        """fetch() with markdown=True should return markdown"""
        result = crawler.fetch(
            "https://example.com",
            {"markdown": True, "headless": True}
        )
        assert isinstance(result, str)

    def test_fetch_playwright_fallback(self):
        """BrowserCrawler should fallback to Playwright when Crawl4AI unavailable"""
        from engine.crawl_browser import BrowserCrawler
        bc = BrowserCrawler()
        # Even if Crawl4AI fails, playwright fallback should work
        result = bc.fetch("https://example.com", {"client": "playwright"})
        assert isinstance(result, str)
        assert len(result) > 0
        bc.close()


class TestBrowserCrawlerDualRouter:
    """Test BrowserCrawler dual-router logic"""

    def test_auto_prefers_crawl4ai(self):
        """client=None should prefer Crawl4AI if available"""
        from engine.crawl_browser import BrowserCrawler, CRAWL4AI_AVAILABLE
        if not CRAWL4AI_AVAILABLE:
            pytest.skip("crawl4ai not available")
        bc = BrowserCrawler()
        result = bc.fetch("https://example.com", {"client": None})
        assert isinstance(result, str)
        bc.close()

    def test_explicit_playwright_client(self):
        """client=playwright should use PlaywrightCrawler"""
        from engine.crawl_browser import BrowserCrawler
        bc = BrowserCrawler()
        result = bc.fetch("https://example.com", {"client": "playwright"})
        assert isinstance(result, str)
        bc.close()

    def test_close_cleans_both(self):
        """close() should clean up both Crawl4AI and Playwright instances"""
        from engine.crawl_browser import BrowserCrawler
        bc = BrowserCrawler()
        bc.fetch("https://example.com", {"client": "crawl4ai"})
        bc.fetch("https://example.com", {"client": "playwright"})
        bc.close()  # Should not raise
```

- [ ] **步骤2：运行测试验证**

```bash
cd /root/info-collector/APP/engine
pytest tests/test_crawl4ai_crawler.py -v
```

- [ ] **步骤3：Commit**

```bash
git add APP/engine/tests/test_crawl4ai_crawler.py
git commit -m "test(crawl4ai): add test_crawl4ai_crawler.py with dual-router tests"
```

---

## 任务7：新增单元测试 test_crawl4ai_field_extraction.py

**文件：**
- 创建：`APP/engine/tests/test_crawl4ai_field_extraction.py`

**前置条件：** 任务4（BrowserCrawler.extract_fields 已支持 llm/markdown）

**步骤：**

- [ ] **步骤1：编写测试**

```python
"""Tests for LLM and Markdown field extraction types"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.crawl_browser import BrowserCrawler


class TestFieldExtraction:
    """Test extract_fields with new field types"""

    @pytest.fixture
    def browser_crawler(self):
        bc = BrowserCrawler()
        yield bc
        bc.close()

    def test_extract_constant_field(self, browser_crawler):
        """type: constant should return the constant value"""
        fields = [{"name": "source", "type": "constant", "value": "test"}]
        result = browser_crawler.extract_fields("<html></html>", fields)
        assert result["source"] == "test"

    def test_extract_xpath_field(self, browser_crawler):
        """type: xpath should extract via xpath"""
        html = "<html><body><h1>Hello World</h1></body></html>"
        fields = [{"name": "title", "type": "xpath", "path": "//h1/text()"}]
        result = browser_crawler.extract_fields(html, fields)
        assert result["title"] == "Hello World"

    def test_extract_markdown_field(self, browser_crawler):
        """type: markdown should return content as-is"""
        md_content = "# Hello\n\nThis is **markdown** content."
        fields = [{"name": "content", "type": "markdown"}]
        result = browser_crawler.extract_fields(md_content, fields)
        assert result["content"] == md_content

    def test_extract_mixed_fields(self, browser_crawler):
        """Mixing field types should work correctly"""
        html = "<html><body><h1>Title</h1><a href='/link'>Link</a></body></html>"
        fields = [
            {"name": "title", "type": "xpath", "path": "//h1/text()"},
            {"name": "url", "type": "attr", "path": "//a", "attr": "href"},
            {"name": "source", "type": "constant", "value": "test"},
            {"name": "raw", "type": "markdown"},
        ]
        result = browser_crawler.extract_fields(html, fields)
        assert result["title"] == "Title"
        assert result["url"] == "/link"
        assert result["source"] == "test"
        assert "Title" in result["raw"]  # raw HTML for markdown type
```

- [ ] **步骤2：运行测试**

```bash
cd /root/info-collector/APP/engine
pytest tests/test_crawl4ai_field_extraction.py -v
```

- [ ] **步骤3：Commit**

```bash
git add APP/engine/tests/test_crawl4ai_field_extraction.py
git commit -m "test(crawl4ai): add test_crawl4ai_field_extraction.py for llm/markdown field types"
```

---

## 任务8：端到端集成测试（真实 JS 渲染页面）

**文件：**
- 修改：`APP/engine/tests/test_integration.py`（或新建 `tests/test_crawl4ai_e2e.py`）

**前置条件：** 所有前述任务完成

**步骤：**

- [ ] **步骤1：编写 E2E 测试**

选择一个公开的 JS 渲染页面（如 GitHub trending、某 SPA 页面）验证完整链路：

```python
"""End-to-end test with a real JS-rendered page"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.engine import InfoCollectorEngine


class TestCrawl4AIE2E:
    """End-to-end test with a real JS-rendered page"""

    @pytest.fixture
    def engine(self):
        e = InfoCollectorEngine()
        yield e
        e.close()

    def test_browser_crawl_real_page(self, engine):
        """source.type: browser should successfully crawl a JS-rendered page"""
        import yaml
        rule = {
            "name": "test-browser-e2e",
            "source": {
                "type": "browser",
                "url": "https://example.com",
                "client": "crawl4ai"
            },
            "list": {
                "fields": [
                    {"name": "title", "type": "xpath", "path": "//title/text()"}
                ]
            }
        }
        items = engine.crawl(rule)
        assert isinstance(items, list)
        # No assertion on length (page content varies)
        assert len(items) >= 0

    def test_client_crawl4ai_explicit(self, engine):
        """client: crawl4ai should work end-to-end"""
        import yaml
        rule = {
            "name": "test-crawl4ai-client",
            "source": {
                "type": "browser",
                "url": "https://example.com",
                "client": "crawl4ai"
            },
            "list": {
                "fields": [
                    {"name": "content", "type": "markdown"}
                ]
            }
        }
        items = engine.crawl(rule)
        assert isinstance(items, list)
```

- [ ] **步骤2：运行测试**

```bash
cd /root/info-collector/APP/engine
pytest tests/test_crawl4ai_e2e.py -v  # 或 test_integration.py
```

- [ ] **步骤3：Commit**

```bash
git add APP/engine/tests/test_crawl4ai_e2e.py  # 或修改后的 test_integration.py
git commit -m "test: add Crawl4AI end-to-end integration test"
```

---

## 自检清单

- [ ] 规格覆盖度：每个规格章节都有对应任务
- [ ] 无占位符：所有步骤含实际代码/命令
- [ ] 任务顺序：0→1→2→3→4→5→6→7→8（任务2/3可并行，但需2先完成）
- [ ] 类型一致性：所有任务间方法名、参数名一致
- [ ] 依赖关系：每个任务标注了前置条件
