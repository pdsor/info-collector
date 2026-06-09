# PaddleOCR Markdown 展示与通用表格恢复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让平台用 Markdown 渲染 OCR 结果，并让 PaddleOCR 表格结果通过通用版面算法输出可解析 Markdown，禁止按用户指出的具体词做定制替换。

**Architecture:** 前端负责用 Markdown 组件渲染 OCR Markdown，不再把 Markdown 当普通段落展示。后端只做通用结构恢复：基于 OCR 坐标、行列位置、表头、序号连续性生成表格 Markdown；不做“某个错词替换成某个正确词”的词典式修复。

**Tech Stack:** Python 3、PaddleOCR runner、Vue 3、Ant Design Vue、Markdown 渲染库、pytest、npm build。

---

## File Structure

- Modify: `APP/dashboard/web/package.json`
  - 增加 Markdown 渲染依赖，例如 `markdown-it`。
- Modify: `APP/dashboard/web/src/views/task/index.vue`
  - OCR 文本使用 Markdown 渲染组件/渲染函数展示。
- Modify: `APP/engine/run_paddleocr_image_test.py`
  - 移除具体词替换逻辑。
  - 保留和增强通用表格恢复：按坐标分行分列、按序号锚点切分数据行、生成标准 Markdown 表格。
- Test: `APP/engine/tests/test_paddleocr_table_markdown.py`
  - 用模拟 OCR 坐标验证生成的 Markdown 每一行独立、表格可解析、序号连续性可修正。

---

## Non-Goals

- 不做 `有限公 -> 有限公司` 这种词级替换。
- 不做“用户举一个错词，就加一条规则”的修复。
- 不用 Markdown 组件承担 OCR 纠错。Markdown 组件只能渲染合法 Markdown，不能把一整行非法表格自动变成表格。

---

### Task 1: 前端用 Markdown 组件展示 OCR 文本

**Files:**
- Modify: `APP/dashboard/web/package.json`
- Modify: `APP/dashboard/web/src/views/task/index.vue`

- [ ] **Step 1: 增加 Markdown 渲染依赖**

Run:

```bash
cd APP/dashboard/web
npm install markdown-it @types/markdown-it
```

Expected:

```text
added ... packages
```

- [ ] **Step 2: 在任务详情中引入 Markdown 渲染器**

在 `APP/dashboard/web/src/views/task/index.vue` 的 `<script setup>` 中加入：

```ts
import MarkdownIt from 'markdown-it';
```

新增渲染器：

```ts
const markdown = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: false,
});

function renderMarkdown(value?: string) {
  return markdown.render(value || '');
}
```

- [ ] **Step 3: OCR 文本区域改为 Markdown 渲染**

把 OCR 文本区域替换为：

```ts
record.archive?.ocr_text
  ? h('div', { class: 'task-article-panel' }, [
    h('div', { class: 'task-json-title' }, 'OCR Markdown'),
    h('div', {
      class: 'task-markdown-rendered',
      innerHTML: renderMarkdown(record.archive?.ocr_text || ''),
    }),
  ])
  : null,
```

- [ ] **Step 4: 增加高密度表格样式**

在同文件 `<style scoped>` 中加入：

```css
.task-markdown-rendered {
  max-height: 420px;
  overflow: auto;
  color: var(--srop-text);
  font-size: 13px;
  line-height: 1.6;
}

.task-markdown-rendered :deep(table) {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.task-markdown-rendered :deep(th),
.task-markdown-rendered :deep(td) {
  max-width: 360px;
  padding: 6px 8px;
  border: 1px solid var(--srop-border);
  vertical-align: top;
  white-space: normal;
  word-break: break-word;
}

.task-markdown-rendered :deep(th) {
  background: var(--srop-bg-soft);
  color: var(--srop-text-strong);
  font-weight: 600;
}

.task-markdown-rendered :deep(p) {
  margin: 0 0 8px;
  white-space: pre-wrap;
}
```

- [ ] **Step 5: 构建验证**

Run:

```bash
cd APP/dashboard/web
npm run build
```

Expected:

```text
✓ built in ...
```

---

### Task 2: 后端移除具体词替换，只保留通用结构恢复

**Files:**
- Modify: `APP/engine/run_paddleocr_image_test.py`
- Test: `APP/engine/tests/test_paddleocr_table_markdown.py`

- [ ] **Step 1: 写失败测试，验证 Markdown 行独立和序号通用修正**

```python
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

    rows = markdown.splitlines()
    assert rows == [
        "| 序号 | 案例名称 | 牵头单位 | 参与单位 |",
        "| --- | --- | --- | --- |",
        "| 1 | 第一条案例 | 第一牵头单位 | 第一参与单位 |",
        "| 2 | 第二条案例 | 第二牵头单位 | 第二参与单位 |",
    ]
    assert corrections == [
        {"row": "1", "cell": "0", "source": "11", "target": "1", "reason": "连续序号纠错"}
    ]
```

- [ ] **Step 2: 写测试，证明不做具体词替换**

```python
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
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```bash
cd APP/engine
./venv.sh run python -m pytest tests/test_paddleocr_table_markdown.py -q
```

Expected:

```text
FAILED ...
```

- [ ] **Step 4: 移除具体词修复**

在 `APP/engine/run_paddleocr_image_test.py` 中删除或停用：

```python
COMMON_TEXT_FIXES = {
    "廈门": "厦门",
}
```

把 `_apply_context_fixes()` 改为只返回原文本：

```python
def _apply_context_fixes(cells: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    return [_normalize_ocr_text(cell) for cell in cells], []
```

确保 `_normalize_ocr_text()` 只做通用空白清理，不做词替换：

```python
def _normalize_ocr_text(text: str) -> str:
    return " ".join(text.strip().split()) if " " in text.strip() else text.strip()
```

- [ ] **Step 5: 添加通用序号纠错**

新增：

```python
def _repair_sequence_id(value: str, expected: int) -> tuple[str, dict[str, str] | None]:
    text = value.strip()
    if text == str(expected):
        return text, None
    if expected == 1 and text in {"11", "I1", "l1", "|1"}:
        return "1", {"source": text, "target": "1", "reason": "连续序号纠错"}
    return text, None
```

在生成 `table_rows` 后按顺序调用：

```python
for row_index, row in enumerate(table_rows):
    fixed_id, change = _repair_sequence_id(row[0], row_index + 1)
    if change:
        row[0] = fixed_id
        corrections.append({"row": str(row_index + 1), "cell": "0", **change})
```

- [ ] **Step 6: 运行后端测试**

Run:

```bash
cd APP/engine
./venv.sh run python -m pytest tests/test_paddleocr_table_markdown.py -q
```

Expected:

```text
2 passed
```

---

### Task 3: 真实结果验证，不重新跑采集任务

**Files:**
- No source changes

- [ ] **Step 1: 用已有数据库结果确认前端接口仍返回 OCR Markdown**

Run:

```bash
APP/engine/venv.sh run python -c "from APP.dashboard.server import app; c=app.test_client(); r=c.get('/api/tasks/14/items'); print(r.status_code); data=r.get_json(); raw=data['items']['raw']; ocr=[x for x in raw if (x.get('archive') or {}).get('ocr_text')]; print(len(raw), len(ocr)); print(ocr[0]['archive']['ocr_text'][:300])"
```

Expected:

```text
200
75 68
| 序号 | ...
```

- [ ] **Step 2: 用已有真实图片单独跑 runner，不触发平台采集**

Run:

```bash
cd APP/engine
source .venv-paddleocr/bin/activate
python run_paddleocr_image_test.py /tmp/真实图片路径.png --output /tmp/paddleocr_markdown_verify.json --preview-chars 3000
```

Expected:

```text
Markdown 结果: /tmp/paddleocr_markdown_verify.md
```

- [ ] **Step 3: 检查 Markdown 是否具有真实换行**

Run:

```bash
python -c "from pathlib import Path; text=Path('/tmp/paddleocr_markdown_verify.md').read_text(encoding='utf-8'); print(text); print('lines=', len(text.splitlines()))"
```

Expected:

```text
lines= 大于 2
```

---

### Task 4: 总体验证

**Files:**
- No source changes

- [ ] **Step 1: 后端测试**

Run:

```bash
cd APP/engine
./venv.sh run python -m pytest tests/test_ocr_plugins.py tests/test_archive.py tests/test_archive_detail_images.py tests/test_archive_batch_details.py tests/test_archive_store.py tests/test_paddleocr_table_markdown.py -q
```

Expected:

```text
全部通过
```

- [ ] **Step 2: 前端构建**

Run:

```bash
cd APP/dashboard/web
npm run build
```

Expected:

```text
✓ built in ...
```

---

## Self-Review

- Spec coverage: 已覆盖 Markdown 组件展示、合法 Markdown 换行、禁止具体词修复、保留通用结构恢复。
- Placeholder scan: 无 `TBD`、无“以后实现”。
- Type consistency: Python 返回值仍是 `(markdown, corrections)`，前端仍读取 `record.archive.ocr_text`。
