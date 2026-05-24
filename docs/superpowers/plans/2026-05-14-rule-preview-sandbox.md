# 规则沙箱试采实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Rule Center 中加入不落正式输出、不创建正式任务历史的规则沙箱试采功能。

**Architecture:** 引擎提供 `preview_rule()` 作为无状态预览入口；Dashboard `rules_api.py` 接收编辑器 YAML，写入临时文件后调用引擎预览；前端 Rule Center 调用 `/api/rules/preview` 并展示结构化结果。

**Tech Stack:** Flask、Vue 3 CDN、pytest、Python tempfile、现有 `InfoCollectorEngine` 与 `GovernancePipeline`。

---

### Task 1: 引擎预览入口

**Files:**
- Modify: `APP/engine/engine/engine.py`
- Test: `APP/engine/tests/test_rule_preview.py`

- [ ] **Step 1: 写失败测试**

创建 `APP/engine/tests/test_rule_preview.py`，覆盖：

```python
import os
import textwrap

from engine.engine import InfoCollectorEngine


def test_preview_rule_returns_limited_governed_items_without_saving(tmp_path):
    html_path = tmp_path / "page.html"
    html_path.write_text(
        """
        <html><body>
          <article><h1>第一条</h1><a href="/a">链接</a></article>
          <article><h1>第二条</h1><a href="/b">链接</a></article>
        </body></html>
        """,
        encoding="utf-8",
    )
    rule_path = tmp_path / "rule.yaml"
    rule_path.write_text(
        textwrap.dedent(
            f"""
            rule_id: "preview-rule"
            source_id: "preview-source"
            version: 1
            status: DRAFT
            source:
              platform: "preview"
              type: "html"
              url: "file://{html_path}"
            list:
              items_path: "css:article"
            extract:
              title: {{ selector: "h1", type: "text" }}
              url: {{ selector: "a", type: "attribute", attribute: "href" }}
            output:
              fields: ["title", "url"]
              save_raw: false
            governance:
              sanitize: true
            """
        ).strip(),
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    engine = InfoCollectorEngine(state_dir=str(output_dir))

    result = engine.preview_rule(str(rule_path), limit=1)

    assert result["success"] is True
    assert result["status"] in {"success", "partial_success"}
    assert result["total_collected"] == 2
    assert result["preview_count"] == 1
    assert result["items"][0]["title"] == "第一条"
    assert not list(output_dir.glob("**/*.json"))
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_preview.py -q`

Expected: FAIL，提示 `InfoCollectorEngine` 没有 `preview_rule`。

- [ ] **Step 3: 实现最小预览入口**

在 `InfoCollectorEngine` 中新增：

```python
def preview_rule(self, rule_path: str, limit: int = 5) -> dict:
    rule = self.load_rule(rule_path)
    top_enabled = rule.get("enabled", True)
    source_enabled = rule.get("source", {}).get("enabled", True)
    if not top_enabled or not source_enabled:
        return {
            "success": True,
            "status": "skipped",
            "reason": "rule_disabled",
            "total_collected": 0,
            "preview_count": 0,
            "items": [],
            "governance": {},
        }
    safe_limit = max(1, min(int(limit or 5), 20))
    items = self.crawl(rule)
    governance_result = GovernancePipeline(rule).process(items)
    governed_items = governance_result.items
    return {
        "success": True,
        "status": "partial_success" if governance_result.status == "PARTIAL_SUCCESS" else "success",
        "total_collected": len(governed_items),
        "preview_count": min(len(governed_items), safe_limit),
        "items": governed_items[:safe_limit],
        "governance": governance_result.summary,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd APP/engine && .venv/bin/python -m pytest tests/test_rule_preview.py -q`

Expected: PASS。

### Task 2: Dashboard 预览 API

**Files:**
- Modify: `APP/dashboard/apis/rules_api.py`
- Test: `APP/dashboard/tests/test_rules_preview_api.py`

- [ ] **Step 1: 写失败测试**

创建 `APP/dashboard/tests/test_rules_preview_api.py`，覆盖空 YAML 和未保存 YAML 预览：

```python
import os
import sys
import textwrap

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

from APP.dashboard.server import app


def test_preview_rule_rejects_empty_yaml():
    client = app.test_client()
    response = client.post("/api/rules/preview", json={"yaml": ""})
    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_preview_rule_accepts_unsaved_yaml(tmp_path):
    html_path = tmp_path / "page.html"
    html_path.write_text("<article><h1>沙箱</h1></article>", encoding="utf-8")
    yaml_content = textwrap.dedent(
        f"""
        rule_id: "preview-api-rule"
        source_id: "preview-api-source"
        version: 1
        status: DRAFT
        source:
          platform: "preview-api"
          type: "html"
          url: "file://{html_path}"
        list:
          items_path: "css:article"
        extract:
          title: {{ selector: "h1", type: "text" }}
        output:
          fields: ["title"]
          save_raw: false
        governance:
          sanitize: true
        """
    ).strip()
    client = app.test_client()

    response = client.post("/api/rules/preview", json={"yaml": yaml_content, "limit": 5})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["items"][0]["title"] == "沙箱"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `APP/engine/.venv/bin/python -m pytest APP/dashboard/tests/test_rules_preview_api.py -q`

Expected: FAIL，提示 `/api/rules/preview` 不存在。

- [ ] **Step 3: 实现 API**

在 `rules_api.py` 新增路由：

```python
@rules_bp.route("/preview", methods=["POST"])
def preview_rule():
    body = request.get_json() or {}
    yaml_content = body.get("yaml") or ""
    if not yaml_content.strip():
        return jsonify({"success": False, "error": "YAML 内容不能为空"}), 400
    try:
        limit = int(body.get("limit", 5))
    except (TypeError, ValueError):
        limit = 5
    limit = max(1, min(limit, 20))
    try:
        import tempfile
        import sys
        sys.path.insert(0, ENGINE_DIR)
        from engine.engine import InfoCollectorEngine
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", encoding="utf-8", delete=False) as tmp:
            tmp.write(yaml_content)
            tmp_path = tmp.name
        try:
            engine = InfoCollectorEngine(state_dir=os.path.join(ENGINE_DIR, ".preview-output"))
            try:
                result = engine.preview_rule(tmp_path, limit=limit)
            finally:
                engine.close()
        finally:
            os.unlink(tmp_path)
        return jsonify(result)
    except ValueError as exc:
        return jsonify({"success": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 200
```

- [ ] **Step 4: 运行 API 测试确认通过**

Run: `APP/engine/.venv/bin/python -m pytest APP/dashboard/tests/test_rules_preview_api.py -q`

Expected: PASS。

### Task 3: Rule Center 前端

**Files:**
- Modify: `APP/dashboard/static/js/app.js`

- [ ] **Step 1: 增加状态和方法**

在 `RuleCenter.setup()` 增加 `previewing`、`previewResult` 和 `previewRule()`。`previewRule()` 调用：

```javascript
const data = await API.post('/rules/preview', { yaml: yaml.value, limit: 5 });
```

- [ ] **Step 2: 增加按钮和结果面板**

在编辑器按钮区增加：

```html
<button :disabled="!selected || loading || previewing" @click="previewRule">试采</button>
```

在 textarea 下方增加结果展示：

```html
<div class="preview-panel" v-if="previewResult">
  <h3>试采结果</h3>
  <div v-if="previewResult.success">
    <p>状态：{{ previewResult.status }}，采集 {{ previewResult.total_collected }} 条，展示 {{ previewResult.preview_count }} 条</p>
    <pre>{{ JSON.stringify(previewResult.items, null, 2) }}</pre>
  </div>
  <div v-else class="message error">{{ previewResult.error }}</div>
</div>
```

- [ ] **Step 3: 前端语法检查**

Run: `node --check APP/dashboard/static/js/app.js`

Expected: PASS。

### Task 4: 综合验证

**Files:**
- No new files.

- [ ] **Step 1: 运行相关测试**

Run:

```bash
cd APP/engine && .venv/bin/python -m pytest tests/test_rule_preview.py -q
cd ../.. && APP/engine/.venv/bin/python -m pytest APP/dashboard/tests/test_rules_preview_api.py -q
node --check APP/dashboard/static/js/app.js
APP/engine/.venv/bin/python -m py_compile APP/dashboard/server.py APP/dashboard/apis/*.py
```

Expected: 全部 exit 0。

- [ ] **Step 2: 检查副作用**

Run: `find APP/engine/output -maxdepth 3 -type f -name '*.json' | wc -l`

Expected: 手动对比执行前后数量不增加。
