"""SimHash 近似去重测试。"""

import pytest

from engine.simhash import fingerprint, hamming_distance, is_near_duplicate, tokenize


def test_tokenize_chinese_splits_per_char():
    tokens = tokenize("数据集名单")
    assert tokens == ["数", "据", "集", "名", "单"]


def test_tokenize_mixed():
    tokens = tokenize("数据集 ABC 123")
    assert "数" in tokens
    assert "据" in tokens
    assert "ABC" in tokens
    assert "123" in tokens


def test_identical_text_zero_distance():
    text = "湖北省第三批高质量数据集名单公示"
    fp1 = fingerprint(text)
    fp2 = fingerprint(text)
    assert hamming_distance(fp1, fp2) == 0


def test_near_duplicate_within_threshold():
    base = "湖北省第三批高质量数据集名单公示，共收录25个数据集。"
    near = "湖北省第三批高质量数据集名单公示，共收录26个数据集。"
    fp1 = fingerprint(base)
    fp2 = fingerprint(near)
    assert is_near_duplicate(fp1, fp2, threshold=5)


def test_completely_different_text_exceeds_threshold():
    text_a = "湖北省第三批高质量数据集名单"
    text_b = "北京市2026年春季招标公告发布通知"
    fp_a = fingerprint(text_a)
    fp_b = fingerprint(text_b)
    assert not is_near_duplicate(fp_a, fp_b, threshold=3)


def test_empty_text_fingerprint_is_zero():
    assert fingerprint("") == 0
    assert fingerprint(None) == 0


def test_hamming_distance_known_values():
    assert hamming_distance(0b1010, 0b1001) == 2
    assert hamming_distance(0, 0) == 0
    assert hamming_distance(0xFF, 0x00) == 8
