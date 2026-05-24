# Info Collector NG MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将旧版本地信息采集项目改造成符合 `DOCS/LatestRequirementDocument.md` v2.2 的无 AI 规则驱动 MVP。

**Architecture:** 保留当前 Flask、Vue 3 CDN、SQLite、后台线程和 YAML 引擎底座，先落地 Source、Rule、Task、Governance 四类业务模型。引擎层移除 Crawl4AI/LLM 路由，采集只通过 HTTP、Playwright 和确定性选择器输出结构化数据。

**Tech Stack:** Python、Flask、SQLite、Vue 3 CDN、Playwright、parsel、pytest。

---

### Task 1: 引擎去 AI 化

**Files:**
- Modify: `APP/engine/engine/rule_parser.py`
- Modify: `APP/engine/engine/crawl_browser.py`
- Modify: `APP/engine/engine/engine.py`
- Modify: `APP/engine/requirements.txt`
- Modify: `APP/engine/tests/test_crawl4ai_routing.py`
- Modify: `APP/engine/tests/test_rule_parser.py`

- [ ] **Step 1: 写失败测试**

新增断言：`client: browser` 默认走 Playwright；`client: crawl4ai` 和 `source.extraction.enabled` 必须被拒绝。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_crawl4ai_routing.py tests/test_rule_parser.py -q`
Expected: FAIL，旧实现仍允许 Crawl4AI。

- [ ] **Step 3: 实现最小代码**

移除 Crawl4AI 路由；规则解析拒绝 AI 字段；引擎删除 `_crawl_with_extraction` 分支。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_crawl4ai_routing.py tests/test_rule_parser.py -q`
Expected: PASS。

### Task 2: 规则 v2 与治理管道 MVP

**Files:**
- Create: `APP/engine/engine/governance.py`
- Modify: `APP/engine/engine/rule_parser.py`
- Modify: `APP/engine/engine/engine.py`
- Modify: `APP/engine/engine/output.py`
- Create: `APP/engine/tests/test_governance.py`
- Create: `APP/engine/tests/test_rule_v2.py`

- [ ] **Step 1: 写失败测试**

覆盖 Rule v2 基础字段、`extract` 字段转换、默认不保存 raw、字段完整率、HTML 清洗和注入风险标记。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_v2.py tests/test_governance.py -q`
Expected: FAIL，相关模块尚不存在。

- [ ] **Step 3: 实现最小代码**

添加 `GovernancePipeline`，在 `InfoCollectorEngine.run()` 保存前处理数据，输出 meta 中写入治理摘要。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_v2.py tests/test_governance.py -q`
Expected: PASS。

### Task 3: Dashboard 元数据 API

**Files:**
- Create: `APP/dashboard/migrations/003_ng_mvp.sql`
- Create: `APP/dashboard/apis/source_api.py`
- Create: `APP/dashboard/apis/governance_api.py`
- Modify: `APP/dashboard/apis/__init__.py`
- Modify: `APP/dashboard/apis/tasks_api.py`
- Modify: `APP/dashboard/apis/rules_api.py`

- [ ] **Step 1: 写失败测试或接口冒烟脚本**

使用 Flask test client 覆盖 `/api/sources`、`/api/governance/summary`、`/api/tasks/history` 的 NG 字段。

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/dashboard && ../engine/.venv/bin/python -m pytest tests -q`
Expected: FAIL 或无测试目录时用接口冒烟脚本确认 404。

- [ ] **Step 3: 实现最小代码**

迁移 SQLite 表；从 state、YAML 和输出文件派生 Source/Governance 摘要；任务状态映射为 v2.2 状态机。

- [ ] **Step 4: 运行接口冒烟确认通过**

Run: `cd APP/dashboard && ../engine/.venv/bin/python - <<'PY' ... PY`
Expected: API 返回 200。

### Task 4: 前端四中心改版

**Files:**
- Modify: `APP/dashboard/static/index.html`
- Modify: `APP/dashboard/static/js/api.js`
- Modify: `APP/dashboard/static/js/app.js`
- Modify: `APP/dashboard/static/css/style.css`

- [ ] **Step 1: 定义四中心页面结构**

保留单文件 Vue 3 CDN，标签改为 Source Center、Rule Center、Task Center、Governance Center。

- [ ] **Step 2: 实现高密度控制台样式**

使用紧凑表格、状态徽标、指标条和日志抽屉；删除装饰性 HUD 文案和图标字符。

- [ ] **Step 3: 连接 API**

Source Center 调 `/api/sources`；Rule Center 复用 `/api/rules`；Task Center 调 `/api/tasks/history`；Governance Center 调 `/api/governance/summary`。

- [ ] **Step 4: 浏览器冒烟**

Run: `cd APP/dashboard && ../engine/.venv/bin/python server.py`
Expected: 页面加载，四中心可切换，控制台无接口级 500。

### Task 5: 文档、依赖和全量验证

**Files:**
- Modify: `README.md`
- Modify: `APP/engine/requirements.txt`
- Modify: `docs/superpowers/manuals/yaml-rule-writing-handbook.md`

- [ ] **Step 1: 更新中文文档**

删除 Crawl4AI/AI 依赖说明，说明 NG MVP 的本地部署方式和 Rule v2 约束。

- [ ] **Step 2: 运行引擎测试**

Run: `cd APP/engine && .venv/bin/python -m pytest tests -q`
Expected: PASS 或列出剩余外部网络/浏览器环境限制。

- [ ] **Step 3: 运行 Dashboard 冒烟**

Run: `cd APP/dashboard && ../engine/.venv/bin/python -m py_compile server.py apis/*.py`
Expected: exit 0。

- [ ] **Step 4: 核对需求清单**

逐项核对无 AI、规则驱动、结构化输出、任务状态、治理摘要和四中心页面。
