"""CloakBrowserCrawler — 用 CloakBrowser (Cloak Chromium) 替代 Playwright 渲染。

CloakBrowser 在 C++ 源码层 patch Chromium 指纹，绕过瑞数 / Cloudflare / Akamai 等 JS challenge
WAF。其 API 返回标准 Playwright Browser 对象，所以这里只覆盖 PlaywrightCrawler 的
浏览器实例化部分，其余解析/提取逻辑全部复用。
"""

from .playwright_crawler import PlaywrightCrawler, USER_AGENTS

__all__ = ["CloakBrowserCrawler", "USER_AGENTS"]


class CloakBrowserCrawler(PlaywrightCrawler):
    """使用 CloakBrowser stealth Chromium 作为底层渲染引擎。

    与 PlaywrightCrawler 的差别：
      * 不调用 `sync_playwright().start()`，由 `cloakbrowser.launch()` 直接接管
      * 默认开启 `stealth_args=True`，把 58 个 C++ patch 后的指纹打开
      * 默认 `humanize=False`（鼠标/键盘自然移动会拖慢采集），需要时由 render_config 打开
    """

    def __init__(self):
        super().__init__()
        # 父类用 _playwright 表示 sync_playwright 句柄；CloakBrowser 不需要单独的 PW 句柄
        # 但保留字段以兼容父类 close()
        self._playwright = None
        self._browser = None
        self._launch_kwargs: dict = {}

    def _get_playwright(self):
        """CloakBrowser 内部已封装 Playwright 生命周期，无需独立 sync_playwright。"""
        return None

    def _get_browser(self, headless: bool = True, stealth: bool = True):
        """启动 CloakBrowser Chromium，必要时按 render_config 重启切换 headless 模式。"""
        import cloakbrowser

        # 浏览器存活则复用；headless 切换时重新启动
        if self._browser is not None:
            try:
                if self._browser.is_connected() and self._launch_kwargs.get("headless") == headless:
                    return self._browser
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        kwargs = dict(
            headless=headless,
            stealth_args=stealth,
            humanize=False,
        )
        self._launch_kwargs = kwargs
        self._browser = cloakbrowser.launch(**kwargs)
        return self._browser

    def close(self):
        """关闭浏览器；不调用父类的 _playwright.stop()，因为这里没有独立 sync_playwright。"""
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        self._launch_kwargs = {}
