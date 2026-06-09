# 发布就绪清理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清理旧 YAML 测试、发布文件范围和 OCR 质量状态，让当前唯一 NDA 规则链路具备可验证的发版基础。

**Architecture:** 不恢复已删除旧规则，测试改为使用当前唯一规则或临时 fixture。OCR 质量状态在统一 `OcrResult` 层表达，PaddleOCR 插件根据通用指标标记低置信度，持久化和前端沿用现有字段展示。

**Tech Stack:** Python、pytest、Flask、PostgreSQL、Vue 3、Vite、npm audit、PaddleOCR。

---

### Task 1: 修正旧 YAML 相关测试

**Files:**
- Modify: `APP/engine/tests/test_rule_parser.py`
- Modify: `APP/engine/tests/test_integration.py`
- Modify: `APP/engine/tests/test_hubei_image_ocr_rule.py`

- [ ] **Step 1: 将规则解析测试从旧规则路径切换到唯一 NDA 规则**

把 `test_rule_parser.py` 中 `cninfo_data_value_search.yaml` 和 `tmtpost_data_articles.yaml` 的硬编码路径改为：

```python
NDA_RULE_PATH = "rules/数据要素/nda_gov_data_element_cases.yaml"
```

断言改为当前规则真实结构：`source.type == "html"`、`source.platform` 为规则文件实际平台值、`list.items_path` 为当前规则实际配置、字段中包含 `title`、`url`、`raw_id`。

- [ ] **Step 2: 将集成测试中的实际规则加载改为 NDA 规则**

把 `test_integration.py::test_load_rule_from_file` 和 `test_engine_crawl_html_integration` 改为加载 `rules/数据要素/nda_gov_data_element_cases.yaml`。网络抓取仍使用 mock HTML，只验证引擎 HTML 管线能执行，不依赖旧站点结构。

- [ ] **Step 3: 删除湖北规则专属断言或改为 NDA 图片 OCR 配置测试**

把 `test_hubei_image_ocr_rule.py` 改名或改内容为 NDA 规则测试，断言 `archive.image_ocr.enabled is True`、`archive.image_ocr.ocr.plugin == "paddleocr"`，并确认不再引用 `hubei_gov_image_ocr_article.yaml`。

- [ ] **Step 4: 验证测试目标**

Run:

```bash
cd APP/engine
./venv.sh run python -m pytest tests/test_rule_parser.py tests/test_integration.py tests/test_hubei_image_ocr_rule.py -q
```

Expected: 相关测试全部通过。

### Task 2: 清理发布文件范围

**Files:**
- Modify: `.gitignore`
- Create: `APP/engine/config.example.yaml`

- [ ] **Step 1: 更新忽略规则**

在 `.gitignore` 增加：

```gitignore
node_modules/
APP/dashboard/web/node_modules/
APP/engine/.venv-paddleocr/
APP/engine/config.yaml
```

保留已有 `venv/`、`.venv/` 规则，避免真实依赖目录和真实数据库配置进入版本库。

- [ ] **Step 2: 新增示例配置，不包含真实密码**

新增 `APP/engine/config.example.yaml`，内容使用占位符：

```yaml
database:
  url: "postgresql://postgres:<password>@<host>:5432/info_collector"
```

如果代码实际配置结构不同，以 `APP/engine/engine/config.py` 当前读取结构为准，但必须避免写入真实内网地址或密码。

- [ ] **Step 3: 确认发布范围**

Run:

```bash
git status --short
git status --ignored --short APP/dashboard/web/node_modules APP/engine/.venv-paddleocr APP/engine/config.yaml
```

Expected: 依赖目录、PaddleOCR 虚拟环境、真实 `config.yaml` 显示为 ignored，不再作为未跟踪发布文件出现。

### Task 3: 处理 npm audit 风险

**Files:**
- Create: `APP/dashboard/web/AUDIT_RISK.md`

- [ ] **Step 1: 记录当前风险**

新增审计说明，记录当前 `npm audit --audit-level=moderate` 报告的 `vitest/vite/esbuild` 链路漏洞、影响范围为前端构建和测试依赖、当前自动修复需要 `npm audit fix --force` 并升级到 `vitest@4.x`，属于破坏性升级。

- [ ] **Step 2: 不在本轮强制升级**

本轮不执行 `npm audit fix --force`，避免在发版清理中引入测试框架大版本升级。文档中明确后续处理路径：单独分支升级 `vitest/vite` 并跑前端测试和构建。

- [ ] **Step 3: 重新审计并保留证据**

Run:

```bash
cd APP/dashboard/web
npm audit --audit-level=moderate
```

Expected: 如果仍报告漏洞，最终说明中标记为已记录但未消除的发布风险。

### Task 4: OCR 质量状态

**Files:**
- Modify: `APP/engine/engine/ocr_plugins/base.py`
- Modify: `APP/engine/engine/ocr_plugins/paddleocr.py`
- Modify: `APP/engine/tests/test_ocr_plugins.py`

- [ ] **Step 1: 扩展统一 OCR 结果**

给 `OcrResult` 增加可选字段：

```python
quality_status: str = "usable"
quality_reasons: list[str] | None = None
```

`manual_review_required` 改为当 `status != "success"`、空文本、或 `quality_status != "usable"` 时返回 `True`。`to_item_fields()` 增加 `ocr_quality_status` 和 `ocr_quality_reasons`。

- [ ] **Step 2: PaddleOCR 使用通用质量规则**

在 `PaddleOcrPlugin.recognize()` 中根据通用指标设置状态：

```python
if not text.strip():
    status = "empty"
    quality_status = "empty"
elif len(text.strip()) < min_text_length:
    status = "success_low_confidence"
    quality_status = "manual_review_required"
elif line_count < min_line_count and image_pixels >= large_image_pixels:
    status = "success_low_confidence"
    quality_status = "manual_review_required"
else:
    status = "success"
    quality_status = "usable"
```

阈值来自配置，默认 `min_text_length=20`、`min_line_count=2`、`large_image_pixels=200000`。只用长度、行数、图片像素等通用信号，不做词典式修复。

- [ ] **Step 3: 增加单元测试**

在 `test_ocr_plugins.py` 增加或更新测试：PaddleOCR 子进程 payload 文本很短时，插件返回 `status == "success_low_confidence"`，`manual_review_required is True`，`to_item_fields()` 包含质量字段。

- [ ] **Step 4: 验证 OCR 测试**

Run:

```bash
cd APP/engine
./venv.sh run python -m pytest tests/test_ocr_plugins.py -q
```

Expected: OCR 插件测试通过。

### Task 5: 全量验证

**Files:**
- No code changes.

- [ ] **Step 1: Engine 全量测试**

Run:

```bash
cd APP/engine
./venv.sh run python -m pytest tests -q
```

Expected: 不再因旧 YAML 缺失失败；如仍失败，记录真实剩余失败并修复属于本计划范围的问题。

- [ ] **Step 2: Dashboard API 测试**

Run:

```bash
APP/engine/venv.sh run python -m pytest APP/dashboard/tests -q
```

Expected: 通过。

- [ ] **Step 3: 前端构建**

Run:

```bash
cd APP/dashboard/web
npm run build
```

Expected: 构建通过；chunk size warning 可记录但不阻断。

- [ ] **Step 4: 发布判断**

最终输出必须包含：已修复项、验证命令和结果、仍存在的风险项，特别是 npm audit 是否仍未消除、OCR 低置信度只是标记不是质量完全解决。

---

## Self-Review

- Spec coverage: 覆盖旧 YAML 测试、发布忽略、npm audit 风险记录、OCR 质量状态四项。
- Placeholder scan: 无待填占位符；阈值和文件路径已给定。
- Type consistency: `ocr_quality_status`、`ocr_quality_reasons` 从 `OcrResult` 贯穿到 item fields，PaddleOCR 只负责赋值。
