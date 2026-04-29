"""Output manager - JSON output handling"""
import json
import os
from datetime import datetime
from pathlib import Path


class OutputManager:
    """Manage JSON output"""
    
    def __init__(self, base_path: str = "./output"):
        """Initialize output manager"""
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)
    
    def save(self, items: list, rule: dict, dedup_filtered: int = 0) -> str:
        """Save items to JSON file"""
        # PSEUDOCODE: Build output path
        output_config = rule.get("output", {})
        output_dir = output_config.get("path", self.base_path)
        filename_template = output_config.get("filename_template", "{date}.json")
        
        # Create directory if needed
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate filename with date
        date_str = datetime.now().strftime("%Y%m%d")
        filename = filename_template.replace("{date}", date_str)
        output_path = os.path.join(output_dir, filename)
        
        # Build output structure
        output_data = {
            "meta": {
                "platform": rule.get("source", {}).get("platform", "unknown"),
                "collected_at": datetime.now().isoformat(),
                "count": len(items),
                "dedup_filtered": dedup_filtered
            },
            "data": items
        }
        
        # Write JSON
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        return output_path
