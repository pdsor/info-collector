"""HTML Crawler - handles HTML-based data sources"""
import requests
import re


class HTMLCrawler:
    """Crawler for HTML-based data sources using regex-based extraction"""
    
    def fetch(self, url: str, **kwargs) -> str:
        """Fetch HTML page"""
        response = requests.get(url, **kwargs)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or 'utf-8'
        return response.text
    
    def parse_items(self, html_content: str, items_path: str) -> list:
        """Parse items from HTML using regex-based extraction.

        Supports two modes:
          - regex:"<pattern>"  — full regex with named or numbered groups: href, text, title
          - xpath:"//tag[@class='name']"  — legacy XPath-style simple class matching
        """
        if items_path.startswith("regex:"):
            pattern = items_path[6:]  # strip "regex:" prefix
            results = []
            for m in re.finditer(pattern, html_content):
                groups = m.groups()
                if len(groups) >= 2:
                    results.append({"href": groups[0], "title": groups[1]})
                elif len(groups) == 1:
                    results.append({"href": groups[0]})
            return results

        # Legacy XPath-style: only handles simple class-based matching
        if "contains(@class" in items_path:
            match = re.search(r"//(\w+)\[contains\(@class,\s*'([^']+)'\)\]", items_path)
            if match:
                tag, class_name = match.groups()
                pattern = rf"<{tag}[^>]*class=['\"]?[^\"']*{re.escape(class_name)}[^\"']*['\"]?[^>]*href=['\"]([^\"']+)['\"][^>]*>"
                matches = re.findall(pattern, html_content)
                return [{"href": m} for m in matches]
        elif "@class=" in items_path:
            match = re.search(r"//(\w+)\[@class=['\"]([^'\"]+)['\"]\]", items_path)
            if match:
                tag, class_name = match.groups()
                pattern = rf"<{tag}[^>]*class=['\"]?{re.escape(class_name)}['\"]?[^>]*>"
                matches = re.findall(pattern, html_content)
                return [{"html": m} for m in matches]
        return []
    
    def extract_attr(self, html_content: str, xpath: str, attr: str) -> str:
        """Extract attribute from HTML element"""
        if "@class=" in xpath:
            match = re.search(r"//(\w+)\[@class=['\"]([^'\"]+)['\"]\]", xpath)
            if match:
                tag, class_name = match.groups()
                pattern = rf"<{tag}[^>]*class=['\"]{re.escape(class_name)}['\"][^>]*>"
                match = re.search(pattern, html_content)
                if match:
                    element = match.group(0)
                    attr_match = re.search(rf"{attr}=['\"]([^'\"]+)['\"]", element)
                    if attr_match:
                        return attr_match.group(1)
        return ""
    
    def extract_text(self, html_content: str, xpath: str) -> str:
        """Extract text content from HTML element"""
        if "@class=" in xpath:
            match = re.search(r"//(\w+)\[@class=['\"]([^'\"]+)['\"]\]//text\(\)", xpath)
            if match:
                tag, class_name = match.groups()
                pattern = rf"<{tag}[^>]*class=['\"]{re.escape(class_name)}['\"][^>]*>([^<]+)</{tag}>"
                text_match = re.search(pattern, html_content)
                if text_match:
                    return text_match.group(1).strip()
            
            # Handle simple //tag[@class='name']//text() pattern
            simple_match = re.search(r"//(\w+)\[@class=['\"]([^'\"]+)['\"]\]", xpath)
            if simple_match:
                tag, class_name = simple_match.groups()
                pattern = rf"<{tag}[^>]*class=['\"]{re.escape(class_name)}['\"][^>]*>([^<]+)</{tag}>"
                text_match = re.search(pattern, html_content)
                if text_match:
                    return text_match.group(1).strip()
        return ""
    
    def extract_fields(self, html_content: str, field_defs: list) -> dict:
        """Extract fields from HTML based on field definitions"""
        result = {}
        
        for field_def in field_defs:
            field_name = field_def["name"]
            field_type = field_def["type"]
            
            if field_type == "constant":
                result[field_name] = field_def["value"]
            elif field_type == "attr":
                path = field_def.get("path", "")
                attr = field_def.get("attr", "href")
                result[field_name] = self.extract_attr(html_content, path, attr)
            elif field_type == "xpath":
                result[field_name] = self.extract_text(html_content, field_def.get("path", ""))
        
        return result
