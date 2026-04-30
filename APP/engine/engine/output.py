"""Output manager - JSON output handling"""
import json
import os
import glob
from datetime import datetime
from pathlib import Path


class OutputManager:
    """Manage JSON output"""

    def __init__(self, base_path: str = "./output"):
        """Initialize output manager"""
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    def save(self, items: list, rule: dict, dedup_filtered: int = 0) -> str:
        """Save items to JSON file and update combined_latest.json"""
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

        # Update combined_latest.json
        self._update_combined_latest(output_dir, rule.get("source", {}).get("platform", "unknown"))

        return output_path

    def _update_combined_latest(self, _source_dir: str = None, _platform: str = None):
        """Collect ALL date-stamped JSON files from ALL platform sub-dirs and write combined_latest.json.

        Args are ignored (kept for backwards compat) — we now scan the entire output tree.
        """
        combined_path = os.path.join(self.base_path, "combined_latest.json")

        # Scan ALL subdirectories under base_path for date-stamped JSON files
        all_files = []
        for root, dirs, files in os.walk(self.base_path):
            for fname in files:
                if fname.startswith(".") or fname == "combined_latest.json":
                    continue
                if fname.endswith(".json"):
                    all_files.append(os.path.join(root, fname))

        # Sort newest first; keep most recent 200 files to avoid OOM on huge runs
        all_files.sort(key=os.path.getmtime, reverse=True)
        all_files = all_files[:200]

        all_items = []
        seen_urls = set()
        latest_at = None

        for fpath in all_files:
            try:
                with open(fpath, encoding='utf-8') as f:
                    data = json.load(f)
                for item in data.get("data", []):
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        all_items.append(item)
                meta_at = data.get("meta", {}).get("collected_at")
                if meta_at and (latest_at is None or meta_at > latest_at):
                    latest_at = meta_at
            except (json.JSONDecodeError, IOError):
                continue

        combined_data = {
            "meta": {
                "platform": "combined",
                "collected_at": latest_at or datetime.now().isoformat(),
                "count": len(all_items),
                "sources": list(seen_urls),
            },
            "data": all_items
        }

        with open(combined_path, 'w', encoding='utf-8') as f:
            json.dump(combined_data, f, ensure_ascii=False, indent=2)

