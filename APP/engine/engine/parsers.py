"""engine/parsers.py - 统一解析层，基于 parsel + jsonpath-ng"""
import re
import json
from datetime import datetime
from typing import Optional

import parsel
from jsonpath_ng import parse as jsonpath_parse


# ── UA 策略常量 ────────────────────────────────────────────────
class UA:
    MOBILE = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
        "Mobile/15E148 Safari/604.1"
    )
    DESKTOP = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )


# ── HTML 解析器 ────────────────────────────────────────────────
class HTMLParser:
    """基于 parsel 的 HTML 解析器，替代自写 regex/XPath"""

    def __init__(self, html_content: str):
        self.selector = parsel.Selector(text=html_content)

    def select(self, css: str):
        """CSS 选择器，返回 SelectorList"""
        return self.selector.css(css)

    def xpath(self, xpath: str):
        """XPath 选择器，返回 SelectorList"""
        return self.selector.xpath(xpath)

    @staticmethod
    def css_one(html_content: str, css: str) -> Optional[str]:
        """CSS 选择器，取第一个元素的 text"""
        sel = parsel.Selector(text=html_content)
        return sel.css(css).xpath("string()").get(default="").strip()

    @staticmethod
    def css_attr(html_content: str, css: str, attr: str) -> Optional[str]:
        """CSS 选择器，取第一个元素指定属性的值"""
        sel = parsel.Selector(text=html_content)
        return sel.css(css).attrib.get(attr, "")

    @staticmethod
    def extract_links(css: str, html_content: str) -> list:
        """CSS 选择器，提取所有匹配的 {href, title} 元组列表"""
        sel = parsel.Selector(text=html_content)
        results = []
        for el in sel.css(css):
            href = el.attrib.get("href", "")
            text = "".join(el.xpath("string()").getall()).strip()
            results.append({"href": href, "title": text})
        return results


# ── JSON 解析器 ────────────────────────────────────────────────
class JSONParser:
    """基于 jsonpath-ng 的 JSON 解析器，替代自写 JSONPath"""

    @staticmethod
    def find(data: dict, jsonpath_expr: str) -> list:
        """使用 JSONPath 表达式从 JSON 数据中提取值

        Args:
            data: JSON 数据（dict 或 list）
            jsonpath_expr: JSONPath 表达式，如 "$.data[*]" 或 "$..items[?(@.id)]"

        Returns:
            匹配的值的列表
        """
        try:
            jp = jsonpath_parse(jsonpath_expr)
            return [m.value for m in jp.find(data)]
        except Exception:
            return []

    @staticmethod
    def find_one(data: dict, jsonpath_expr: str, default=None):
        """JSONPath 取第一个匹配值，不存在则返回 default"""
        results = JSONParser.find(data, jsonpath_expr)
        return results[0] if results else default

    @staticmethod
    def transform_strip_html(value: str) -> str:
        """移除 HTML 标签"""
        return re.sub(r"<[^>]+>", "", str(value))

    @staticmethod
    def transform_timestamp_ms_to_iso(value) -> str:
        """毫秒时间戳转 ISO 格式"""
        if not value:
            return value
        try:
            ts = int(value)
            if ts > 1e12:
                ts = ts / 1000
            return datetime.fromtimestamp(ts).isoformat()
        except Exception:
            return value

    TRANSFORM_MAP = {
        "strip_html": transform_strip_html.__func__,
        "trim": lambda v: str(v).strip() if v else v,
        "timestamp_ms_to_iso": transform_timestamp_ms_to_iso.__func__,
    }

    @classmethod
    def apply_transforms(cls, value, transforms: str) -> str:
        """批量应用转换函数

        Args:
            value: 原始值
            transforms: 逗号分隔的转换名称，如 "strip_html,trim"
        """
        if not transforms:
            return value
        for t in transforms.split(","):
            t = t.strip()
            fn = cls.TRANSFORM_MAP.get(t)
            if fn:
                value = fn(value)
        return value
