# Rule Center YAML 格式化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 Rule Center 新建规则时右侧 YAML 内容排版错乱的问题，并增加手动格式化按钮。

**Architecture:** 在现有 Vue 3 CDN 单页控制台内增加前端纯函数，不引入新依赖。Rule Center 使用统一的模板生成函数创建 Rule v2 YAML，格式化按钮调用同一组轻量格式化工具处理常见行内对象、行内数组和缩进。格式化失败时保留原文并给出提示。

**Tech Stack:** Flask 静态页面、Vue 3 CDN、原生 JavaScript、pytest 调用 Node VM 做前端静态行为测试。

---

### Task 1: Rule Center YAML 模板与格式化工具

**Files:**
- Modify: `APP/dashboard/static/js/app.js`
- Modify: `APP/dashboard/static/css/style.css`
- Test: `APP/dashboard/tests/test_rule_center_editor_static.py`

- [ ] **Step 1: Write the failing test**

新增测试加载真实 `app.js`，通过 Node VM 注入 Vue/API 桩，断言：
- `getNewRuleYaml()` 输出 Rule v2 分层 YAML；
- `formatYamlText()` 能把行内对象和数组展开为多行 YAML；
- Rule Center 模板包含“格式化”按钮。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest APP/dashboard/tests/test_rule_center_editor_static.py -q`

Expected: FAIL，原因是 `getNewRuleYaml` 或 `formatYamlText` 尚未定义。

- [ ] **Step 3: Implement minimal code**

在 `APP/dashboard/static/js/app.js` 中增加：
- `getNewRuleYaml()`：生成符合 Rule v2 DSL 的多行 YAML 模板；
- `formatYamlText()`：格式化常见行内对象、行内数组并统一结尾换行；
- `formatRuleYaml()`：Rule Center 按钮事件，成功后替换编辑器内容，失败时设置中文错误消息。

在 Rule Center 工具栏增加“格式化”按钮，并在 `style.css` 中补充编辑器排版和消息状态样式。

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest APP/dashboard/tests/test_rule_center_editor_static.py -q`

Expected: PASS。

- [ ] **Step 5: Run dashboard regression tests**

Run: `python -m pytest APP/dashboard/tests -q`

Expected: PASS。

- [ ] **Step 6: Syntax verification**

Run: `node --check APP/dashboard/static/js/app.js`

Expected: exit 0。
