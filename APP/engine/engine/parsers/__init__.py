"""HTML/XML Parsing utilities using parsel"""
from parsel import Selector

__all__ = ["HTMLParser"]


class HTMLParser:
    """Wrapper around parsel.Selector for HTML parsing with XPath and CSS support"""

    def __init__(self, html_content: str):
        self.selector = Selector(text=html_content)

    def xpath(self, xpath_expr: str) -> "HTMLParser":
        """Execute XPath and return new HTMLParser with results"""
        result = self.selector.xpath(xpath_expr)
        parser = HTMLParser.__new__(HTMLParser)
        parser.selector = result
        return parser

    def css(self, css_expr: str) -> "HTMLParser":
        """Execute CSS selector and return new HTMLParser with results"""
        result = self.selector.css(css_expr)
        parser = HTMLParser.__new__(HTMLParser)
        parser.selector = result
        return parser

    def get(self, attr: str = None) -> str:
        """Get text content or attribute value"""
        if attr:
            # Get attribute value
            values = self.selector.getall()
            if values:
                return values[0].get(attr, "") if isinstance(values[0], dict) else ""
            # Try @attr syntax
            result = self.selector.xpath(f"@{attr}").getall()
            return result[0] if result else ""
        else:
            # Get text content
            return self.selector.get()

    def getall(self) -> list:
        """Get all matching elements as list"""
        return self.selector.getall()

    def text(self) -> str:
        """Get concatenated text content of all matching elements"""
        return "".join(self.selector.css("::text").getall()).strip()

    def re(self, regex: str) -> list:
        """Extract text matching regex pattern"""
        return self.selector.re(regex)
