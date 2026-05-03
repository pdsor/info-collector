"""
InfoCollector 事件流协议
========================
所有 --format=json 模式下 run-rule / run-all 的输出均为 JSONL（逐行 JSON），
每行是一个独立事件，Dashboard 负责解析并写入任务历史。
"""
import time
import json


def _ts() -> int:
    """当前 Unix 时间戳（秒）"""
    return int(time.time())


def emit(event_type: str, **kwargs) -> str:
    """
    构造并返回一条 JSONL 行。
    所有事件必含 type 和 ts 字段。
    """
    event = {"type": event_type, "ts": _ts(), **kwargs}
    return json.dumps(event, ensure_ascii=False)


# ── 事件构造器 ──────────────────────────────────────────────

def event_start(rule: str) -> str:
    """单个规则开始执行"""
    return emit("start", rule=rule)


def event_status(rule: str, status: str, msg: str = "") -> str:
    """状态变化：running / success / failed / skipped"""
    return emit("status", rule=rule, status=status, msg=msg)


def event_progress(rule: str, phase: str, current: int, total: int) -> str:
    """进度：fetch / parse / save"""
    return emit("progress", rule=rule, phase=phase, current=current, total=total)


def event_item(rule: str, data: dict) -> str:
    """新增数据项（仅新增，去重前）"""
    return emit("item", rule=rule, data=data)


def event_error(rule: str, message: str, detail: str = "") -> str:
    """执行出错"""
    return emit("error", rule=rule, message=message, detail=detail)


def event_skip(rule: str, reason: str) -> str:
    """规则被跳过"""
    return emit("skip", rule=rule, reason=reason)


def event_complete(rule: str, new_count: int = 0, skip_count: int = 0, duration: float = 0.0) -> str:
    """单个规则执行完成"""
    return emit("complete", rule=rule, new_count=new_count, skip_count=skip_count, duration=round(duration, 2))


def event_summary(total_rules: int, total_new: int, total_skip: int, total_error: int, duration: float) -> str:
    """run-all 全部结束汇总（仅 run-all 输出）"""
    return emit(
        "summary",
        total_rules=total_rules,
        total_new=total_new,
        total_skip=total_skip,
        total_error=total_error,
        duration=round(duration, 2),
    )
