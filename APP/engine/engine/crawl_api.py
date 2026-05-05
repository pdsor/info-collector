"""API Crawler - handles API-based data sources"""
import requests
import re
from datetime import datetime

from .parsers import JSONParser


class APICrawler:
    """Crawler for API-based data sources"""
    
    def build_request_params(self, rule: dict) -> dict:
        """Build request parameters from rule"""
        source = rule.get("source", {})
        request = rule.get("request", {})
        
        params = {
            "method": request.get("method", "GET"),
            "url": source.get("base_url", ""),
            "headers": request.get("headers", {}),
        }
        
        # Handle body template with variable substitution
        body_template = request.get("body_template", "")
        params_dict = request.get("params", {})
        
        # Replace placeholders in body
        body = body_template
        for key, value in params_dict.items():
            body = body.replace(f"{{{key}}}", str(value))
        
        if params["method"] == "POST":
            params["data"] = body
        
        return params
    
    def fetch(self, url: str, method: str = "GET", **kwargs) -> dict:
        """Fetch data from API"""
        # PSEUDOCODE: Use requests library
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()
    
    def parse_items(self, response_data: dict, items_path: str) -> list:
        """Parse items from API response using JSONPath-like syntax"""
        # Support both "$.announcements[*]" and "announcements" formats
        if not items_path:
            return response_data.get("data", [])
        return JSONParser.find(response_data, items_path)
    
    def extract_fields(self, item: dict, field_defs: list) -> dict:
        """Extract fields from item based on field definitions"""
        result = {}
        
        for field_def in field_defs:
            field_name = field_def["name"]
            field_type = field_def["type"]
            
            if field_type == "constant":
                result[field_name] = field_def["value"]
            
            elif field_type == "field":
                path = field_def.get("path", "")
                value = self._get_json_path(item, path)
                transform = field_def.get("transform")
                if transform:
                    value = self.transform_value(value, transform)
                result[field_name] = value
            
            elif field_type == "computed":
                template = field_def.get("value", "")
                vars_dict = field_def.get("vars", {})
                # Replace variables in template
                for var_name, var_path in vars_dict.items():
                    var_value = self._get_json_path(item, var_path)
                    template = template.replace(f"{{{var_name}}}", str(var_value))
                result[field_name] = template
        
        return result
    
    def _get_json_path(self, data: dict, path: str) -> str:
        """Get value from dict using JSONPath-like syntax"""
        # Support both "$.key.subkey" and "key.subkey" formats
        return JSONParser.find_one(data, path, default="")
    
    def transform_value(self, value, transform: str) -> str:
        """Apply transformation to value"""
        if not transform or not value:
            return value
        
        transforms = transform.split(",")
        for t in transforms:
            t = t.strip()
            if t == "strip_html":
                value = re.sub(r'<[^>]+>', '', str(value))
            elif t == "trim":
                value = str(value).strip()
            elif t == "timestamp_ms_to_iso":
                try:
                    ts = int(value)
                    # Handle milliseconds
                    if ts > 1e12:
                        ts = ts / 1000
                    value = datetime.fromtimestamp(ts).isoformat()
                except:
                    pass
        
        return value

    def fetch_with_pagination(self, rule: dict) -> list:
        """Fetch all pages and return combined results"""
        params = self.build_request_params(rule)
        pagination_cfg = rule.get("pagination", {})

        if not pagination_cfg.get("enabled", False):
            # Single page
            response = self.fetch(
                params["url"], method=params["method"],
                headers=params.get("headers", {}), data=params.get("data", {})
            )
            items_path = rule.get("list", {}).get("items_path", "")
            return self.parse_items(response, items_path)

        page_param = pagination_cfg.get("page_param", "pageNum")
        max_pages = pagination_cfg.get("max_pages", 10)

        all_items = []
        items_path = rule.get("list", {}).get("items_path", "")

        for page in range(1, max_pages + 1):
            # Replace page param in body
            body = params.get("data", "")
            body = re.sub(rf"{page_param}=[^&]*", f"{page_param}={page}", body)
            if page_param not in body:
                body = body + f"&{page_param}={page}" if body else f"{page_param}={page}"

            response = self.fetch(
                params["url"], method=params["method"],
                headers=params.get("headers", {}), data=body
            )

            items = self.parse_items(response, items_path)
            if not items:
                break
            all_items.extend(items)

        return all_items
