"""确定性数据治理管道。"""
import hashlib
import re
from dataclasses import dataclass
from html import unescape


INJECTION_PATTERNS = [
    "ignore previous instructions",
    "忽略之前的指令",
    "system prompt",
    "developer message",
]


@dataclass
class GovernanceResult:
    """治理处理结果。"""

    items: list[dict]
    summary: dict
    status: str


class GovernancePipeline:
    """对结构化采集结果执行清洗、风险标记和质量评分。"""

    def __init__(self, rule: dict):
        self.rule = rule
        self.config = rule.get("governance") or {}
        output_fields = (rule.get("output") or {}).get("fields") or []
        required_fields = self.config.get("required_fields") or output_fields
        self.required_fields = list(required_fields)
        self.min_completeness = float(self.config.get("min_completeness", 0.8))

    def process(self, items: list[dict]) -> GovernanceResult:
        """处理采集结果并返回治理摘要。"""
        cleaned_items = []
        seen_hashes = set()
        duplicate_count = 0
        injection_risk_count = 0
        completeness_values = []

        for item in items:
            cleaned = self._clean_item(item)
            content_hash = self._content_hash(cleaned)
            if self.config.get("dedup") in {"hash", "simhash", "minhash"}:
                if content_hash in seen_hashes:
                    duplicate_count += 1
                    continue
                seen_hashes.add(content_hash)

            injection_risk = self._has_injection_risk(cleaned)
            if injection_risk:
                injection_risk_count += 1
                self._remove_injection_text(cleaned)

            completeness = self._field_completeness(cleaned)
            completeness_values.append(completeness)
            cleaned["_governance"] = {
                "content_hash": content_hash,
                "field_completeness": completeness,
                "injection_risk": injection_risk,
            }
            cleaned_items.append(cleaned)

        field_completeness = (
            round(sum(completeness_values) / len(completeness_values), 4)
            if completeness_values else 1.0
        )
        status = "SUCCESS" if field_completeness >= self.min_completeness else "PARTIAL_SUCCESS"
        summary = {
            "item_count": len(cleaned_items),
            "duplicate_count": duplicate_count,
            "injection_risk_count": injection_risk_count,
            "field_completeness": field_completeness,
            "quality_score": round(max(0.0, field_completeness - injection_risk_count * 0.1), 4),
            "status": status,
        }
        return GovernanceResult(items=cleaned_items, summary=summary, status=status)

    def _clean_item(self, item: dict) -> dict:
        """清洗单条记录。"""
        return {key: self._clean_value(value) for key, value in item.items()}

    def _clean_value(self, value):
        """清洗字段值。"""
        if not isinstance(value, str):
            return value
        value = unescape(value)
        if self.config.get("sanitize", True):
            value = re.sub(r"<[^>]+>", "", value)
            value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
        return value.strip()

    def _has_injection_risk(self, item: dict) -> bool:
        """检测常见提示注入文本。"""
        text = " ".join(str(value).lower() for value in item.values() if isinstance(value, str))
        return any(pattern in text for pattern in INJECTION_PATTERNS)

    def _remove_injection_text(self, item: dict):
        """从文本字段中移除已知注入片段。"""
        for key, value in list(item.items()):
            if not isinstance(value, str):
                continue
            cleaned = value
            for pattern in INJECTION_PATTERNS:
                cleaned = re.sub(re.escape(pattern), "", cleaned, flags=re.IGNORECASE)
            item[key] = cleaned.strip(" 。.，,")

    def _field_completeness(self, item: dict) -> float:
        """计算必填字段完整率。"""
        if not self.required_fields:
            return 1.0
        present = 0
        for field in self.required_fields:
            value = item.get(field)
            if value is not None and str(value).strip() != "":
                present += 1
        return round(present / len(self.required_fields), 4)

    def _content_hash(self, item: dict) -> str:
        """根据结构化字段生成内容哈希。"""
        parts = []
        for key in sorted(item):
            if key.startswith("_"):
                continue
            parts.append(f"{key}={item.get(key)}")
        return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
