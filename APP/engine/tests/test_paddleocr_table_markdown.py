from run_paddleocr_image_test import _table_markdown_from_lines


def line(text, x, y):
    return {
        "text": text,
        "score": 0.99,
        "box": [[x - 5, y - 5], [x + 5, y - 5], [x + 5, y + 5], [x - 5, y + 5]],
    }


def test_table_markdown_has_real_newlines_and_repairs_first_sequence_id():
    lines = [
        line("序号", 40, 20),
        line("案例名称", 190, 20),
        line("牵头单位", 430, 20),
        line("参与单位", 610, 20),
        line("11", 40, 60),
        line("第一条案例", 190, 60),
        line("第一牵头单位", 430, 60),
        line("第一参与单位", 610, 60),
        line("2", 40, 100),
        line("第二条案例", 190, 100),
        line("第二牵头单位", 430, 100),
        line("第二参与单位", 610, 100),
    ]

    markdown, corrections = _table_markdown_from_lines(lines, image_width=686)

    assert markdown.splitlines() == [
        "| 序号 | 案例名称 | 牵头单位 | 参与单位 |",
        "| --- | --- | --- | --- |",
        "| 1 | 第一条案例 | 第一牵头单位 | 第一参与单位 |",
        "| 2 | 第二条案例 | 第二牵头单位 | 第二参与单位 |",
    ]
    assert corrections == [
        {"row": "1", "cell": "0", "source": "11", "target": "1", "reason": "连续序号纠错"}
    ]


def test_table_markdown_does_not_apply_word_specific_corrections():
    lines = [
        line("序号", 40, 20),
        line("案例名称", 190, 20),
        line("牵头单位", 430, 20),
        line("参与单位", 610, 20),
        line("1", 40, 60),
        line("测试案例", 190, 60),
        line("测试单位", 430, 60),
        line("某某科技有限公", 610, 60),
        line("2", 40, 100),
        line("第二案例", 190, 100),
        line("第二单位", 430, 100),
        line("司、其他单位", 610, 100),
    ]

    markdown, corrections = _table_markdown_from_lines(lines, image_width=686)

    assert "某某科技有限公" in markdown
    assert "司、其他单位" in markdown
    assert "某某科技有限公司" not in markdown
    assert not any(item["reason"] == "固定词替换" for item in corrections)


def test_table_markdown_keeps_real_row_eleven_when_sequence_continues_to_twelve():
    lines = [
        line("序号", 40, 20),
        line("案例名称", 190, 20),
        line("牵头单位", 430, 20),
        line("参与单位", 610, 20),
        line("11", 40, 60),
        line("第十一条案例", 190, 60),
        line("第十一牵头单位", 430, 60),
        line("第十一参与单位", 610, 60),
        line("12", 40, 100),
        line("第十二条案例", 190, 100),
        line("第十二牵头单位", 430, 100),
        line("第十二参与单位", 610, 100),
    ]

    markdown, corrections = _table_markdown_from_lines(lines, image_width=686)

    assert "| 11 | 第十一条案例 | 第十一牵头单位 | 第十一参与单位 |" in markdown
    assert "| 12 | 第十二条案例 | 第十二牵头单位 | 第十二参与单位 |" in markdown
    assert corrections == []
