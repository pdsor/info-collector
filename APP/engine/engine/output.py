"""Output manager - JSON output handling with subject-based directory structure"""
import json
import os
import glob
from datetime import datetime
from pathlib import Path


class OutputManager:
    """Manage JSON output under output/{subject}/{platform}/ structure"""

    def __init__(self, base_path: str = "engine/data"):
        """Initialize output manager.
        
        Args:
            base_path: Root output directory (engine/data)
        """
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    def _resolve_subject(self, rule: dict) -> str:
        """Resolve subject from rule: top-level 'subject' > source.subject > platform (fallback)."""
        subject = (
            rule.get("subject")
            or rule.get("source", {}).get("subject")
        )
        if not subject:
            # Fallback: use platform as pseudo-subject for rules without subject field
            platform = rule.get("source", {}).get("platform", "")
            if platform:
                return platform
            raise ValueError(
                f"Rule '{rule.get('name')}' has no 'subject' field. "
                "Each rule must declare a subject."
            )
        return subject

    def _resolve_platform(self, rule: dict) -> str:
        """Get platform from rule."""
        return rule.get("source", {}).get("platform", "unknown")

    def _resolve_output_dir(self, rule: dict) -> str:
        """Build output directory path: {base_path}/{subject}/{platform}/
        If rule["output"]["path"] is explicitly set (custom path), use it directly.
        """
        output_cfg = rule.get("output") or {}
        explicit_path = output_cfg.get("path")
        if explicit_path:
            return explicit_path  # Custom path provided; use as-is
        subject = self._resolve_subject(rule)
        platform = self._resolve_platform(rule)
        return os.path.join(self.base_path, subject, platform)

    def save(self, items: list, rule: dict, dedup_filtered: int = 0) -> str:
        """Save items to JSON file and update subject-level combined_latest.json.

        Output path: {base_path}/{subject}/{platform}/data_{date}.json
        Combined path: {base_path}/{subject}/combined_latest.json
        """
        output_dir = self._resolve_output_dir(rule)
        os.makedirs(output_dir, exist_ok=True)

        filename_template = rule.get("output", {}).get(
            "filename_template", "data_{date}.json"
        )
        date_str = datetime.now().strftime("%Y%m%d")
        filename = filename_template.replace("{date}", date_str)
        output_path = os.path.join(output_dir, filename)

        output_data = {
            "meta": {
                "subject": self._resolve_subject(rule),
                "platform": self._resolve_platform(rule),
                "rule_name": rule.get("name"),
                "collected_at": datetime.now().isoformat(),
                "count": len(items),
                "dedup_filtered": dedup_filtered,
            },
            "data": items,
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        # Update subject-level combined_latest.json
        self._update_combined_latest(rule)

        return output_path

    def _update_combined_latest(self, rule: dict):
        """Collect ALL date-stamped JSON files for this subject (all platforms)
        and write combined_latest.json to the subject directory.

        Path: {base_path}/{subject}/combined_latest.json
        """
        subject = self._resolve_subject(rule)
        subject_dir = os.path.join(self.base_path, subject)
        combined_path = os.path.join(subject_dir, "combined_latest.json")
        os.makedirs(subject_dir, exist_ok=True)

        # Scan all platform sub-dirs under this subject for data JSON files
        all_files = []
        if os.path.isdir(subject_dir):
            for root, dirs, files in os.walk(subject_dir):
                for fname in files:
                    if (fname.startswith(".")
                        or fname == "combined_latest.json"
                        or not fname.endswith(".json")):
                        continue
                    all_files.append(os.path.join(root, fname))

        # Sort newest first; keep most recent 200 to avoid OOM
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
                "subject": subject,
                "platform": "combined",
                "collected_at": latest_at or datetime.now().isoformat(),
                "count": len(all_items),
            },
            "data": all_items,
        }

        with open(combined_path, 'w', encoding='utf-8') as f:
            json.dump(combined_data, f, ensure_ascii=False, indent=2)
