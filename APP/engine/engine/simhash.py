"""轻量 SimHash 近似去重实现（无外部依赖）。

算法：
  1. 把文本切成 token（中文按字，英文按词）。
  2. 每个 token 取 SHA-256 前 `bits` 位得到一个整数哈希。
  3. 对每个 bit 位，统计所有 token 哈希在该位的投票（1→+1，0→-1）。
  4. 最终 fingerprint：bit i = 1 if vote[i] > 0 else 0。
  5. 两个 fingerprint 的 Hamming 距离 ≤ threshold → 近似重复。
"""

import hashlib
import re


def tokenize(text: str) -> list[str]:
    """拆分文本为 token 列表。中文按字，英文/数字按词。"""
    tokens = []
    for segment in re.split(r"(\s+)", text or ""):
        if re.match(r"[一-鿿]+", segment):
            tokens.extend(list(segment))  # 中文逐字
        elif segment.strip():
            tokens.append(segment.strip())
    return [t for t in tokens if t]


def fingerprint(text: str, bits: int = 64) -> int:
    """计算文本的 SimHash fingerprint。"""
    votes = [0] * bits
    for token in tokenize(text):
        h = int(hashlib.sha256(token.encode("utf-8")).hexdigest(), 16)
        for i in range(bits):
            votes[i] += 1 if (h >> i) & 1 else -1
    result = 0
    for i in range(bits):
        if votes[i] > 0:
            result |= 1 << i
    return result


def hamming_distance(a: int, b: int) -> int:
    """计算两个整数的 Hamming 距离（不同 bit 数量）。"""
    x = a ^ b
    count = 0
    while x:
        count += x & 1
        x >>= 1
    return count


def is_near_duplicate(a: int, b: int, threshold: int = 3) -> bool:
    """Hamming 距离 ≤ threshold 时判定为近似重复。"""
    return hamming_distance(a, b) <= threshold
