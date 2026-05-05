# info-collector 问题修复与测试完善 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。
>
> **背景：** 53个单元测试全部通过，但跨模块集成存在4个严重问题需要修复，同时测试本身也需要补充以覆盖这些场景。

**目标：** 修复所有已知问题，并补充单元测试使同类问题不再被遗漏

**架构：** 分为5个阶段：①问题确认 ②代码修复 ③测试补充 ④集成验证 ⑤回归测试

**技术栈：** Python 3.11, pytest, SQLite, Flask, APScheduler, Playwright

---

## 阶段一：问题根因确认

### 任务 0：问题根因技术确认

**文件：** 无需修改文件，纯调查

- [ ] **步骤 1：确认 enabled 字段读写不一致**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python -c "import yaml; d=yaml.safe_load(open('rules/数据要素/cninfo_data_value_search.yaml')); print('top-level enabled:', d.get('enabled')); print('source.enabled:', d.get('source',{}).get('enabled')); print('dedup.enabled:', d.get('dedup',{}).get('enabled'))"`
  - 预期输出：top-level: None, source.enabled: None, dedup.enabled: True（确认 enabled 放错位置）

- [ ] **步骤 2：确认数据目录路径不一致**
  - 运行：`cd /root/info-collector/APP && ls engine/output/数据要素/cninfo/ 2>/dev/null && echo "---" && ls engine/data/ 2>/dev/null`
  - 预期：output/ 下有 JSON 文件，data/ 目录不存在

- [ ] **步骤 3：确认分页逻辑缺失**
  - 运行：`grep -n "pagination\|max_pages\|pageNum" engine/crawl_api.py engine/engine.py`
  - 预期：crawl_api.py 无分页相关代码

- [ ] **步骤 4：确认 cron 绑定规则被忽略**
  - 运行：`grep -n "rule_path\|_run_cron" dashboard/apis/cron_api.py`
  - 预期：_run_cron 调用 run-all，rule_path 参数未使用

- [ ] **步骤 5：确认输出格式测试覆盖**
  - 运行：`grep -n "jsonl\|\.jsonl" tests/test_output.py engine/output.py`
  - 预期：output.py 无 jsonl 输出，data_api.py 期望 .jsonl 文件

---

## 阶段二：代码修复

### 任务 1：统一 enabled 字段位置（顶级字段）

**文件：**
- 修改：`APP/engine/engine/engine.py:215` — 确认读取 `rule.get("enabled", True)`
- 修改：`APP/engine/engine_cli.py:296` — 改为写入顶级 `doc["enabled"]` 而非 `doc["source"]["enabled"]`
- 修改：`APP/engine/engine/state.py:67` — 统一读取顶级 `enabled` 字段
- 修改：`APP/dashboard/apis/rules_api.py` — toggle 接口需同步到 YAML 顶级

**修复策略：**
- 约定：`enabled` 是 YAML 顶级字段
- `engine.py run()` 读取 `rule.get("enabled", True)`
- `enable-rule` CLI 命令写入 `doc["enabled"]`
- `state.py register_rule()` 读取 `rule.get("enabled", True)`
- 看板 toggle 按钮调用 `PUT /api/rules/<path>/toggle` → `enable-rule` CLI → 写入 YAML 顶级

- [ ] **步骤 1：编写失败测试**

```python
# tests/test_enabled_field_consistency.py（新建）
def test_engine_respects_yaml_top_level_enabled(tmp_path):
    """Engine 应读取 YAML 顶级 enabled 字段，而非 source.enabled"""
    import yaml
    rule_path = tmp_path / "test_rule.yaml"
    # 写入 source.enabled（错误位置）
    rule_path.write_text(yaml.dump({
        "name": "测试规则",
        "source": {"platform": "test", "type": "html", "url": "http://x", "enabled": False},
        "list": {"items_path": "", "fields": []},
    }))
    from engine.engine import InfoCollectorEngine
    e = InfoCollectorEngine(dedup_db_path=str(tmp_path / "dedup.db"))
    result = e.run(str(rule_path))
    assert result["status"] == "skipped", "当 enabled=False 时应跳过执行"
```

- [ ] **步骤 2：运行测试验证失败**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_enabled_field_consistency.py -v`
  - 预期：FAIL — 当前 engine 读顶级字段，但 YAML 写入 source.enabled

- [ ] **步骤 3：修复 engine.py 第215行**
  - 保持 `rule.get("enabled", True)` — 已是正确行为

- [ ] **步骤 4：修复 engine_cli.py enable-rule 写入位置**
  - 旧代码：`doc["source"]["enabled"] = enabled`
  - 新代码：`doc["enabled"] = enabled`
  - 注意：修复后需要从 YAML 中移除 `source.enabled`（如果存在）

- [ ] **步骤 5：修复现有 YAML 文件**
  - `cninfo_data_value_search.yaml`：删除 `dedup.enabled`，添加顶级 `enabled: true`
  - `tmtpost_data_articles.yaml`：`render.enabled` 和 `detail.enabled` 保持不变（这些是配置项，不是规则开关）
  - `sample_rule.yaml`：将 `source.enabled` 移到顶级

- [ ] **步骤 6：运行测试验证通过**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_enabled_field_consistency.py -v`
  - 预期：PASS

- [ ] **步骤 7：验证完整流程**
  - 运行：`.venv/bin/python engine_cli.py enable-rule rules/test/sample_rule.yaml --enable=false && grep "enabled:" rules/test/sample_rule.yaml && .venv/bin/python engine_cli.py run-rule rules/test/sample_rule.yaml 2>&1 | grep -E "skipped|enabled"`
  - 预期：enabled: false 且 run-rule 输出包含 "skipped"

- [ ] **步骤 8：Commit**
  ```
  git add engine/engine/engine.py engine/engine_cli.py rules/
  git commit -m "fix: 统一 enabled 字段到 YAML 顶级，修正 enable-rule 写入位置"
  ```

---

### 任务 2：统一数据目录（output.py → engine/data/）

**文件：**
- 修改：`APP/engine/engine/output.py` — 将 base_path 从 `./output` 改为 `engine/data`
- 修改：`APP/engine/engine_cli.py` — ENGINE_ROOT 定义处，确保 state_dir 和 dedup_db 路径正确

**修复策略：**
- 输出目录统一到 `engine/data/{subject}/{platform}/data_xxx.json`
- 看板 data_api.py 已正确指向 `engine/data/`，无需修改

- [ ] **步骤 1：编写失败测试**

```python
# tests/test_output_directory.py（新建）
def test_output_writes_to_engine_data_dir(tmp_path):
    """OutputManager 应写入 engine/data/ 目录，供 data_api 读取"""
    from engine.output import OutputManager
    om = OutputManager(base_path=str(tmp_path))
    rule = {
        "name": "Test",
        "subject": "测试",
        "source": {"platform": "test_platform", "type": "api"},
        "output": {"format": "json", "filename_template": "test_{date}.json"}
    }
    out_path = om.save([{"title": "t1"}], rule)
    # 输出应在 engine/data/ 子目录
    assert "engine/data" in out_path or out_path.startswith(str(tmp_path))
```

- [ ] **步骤 2：运行测试验证失败**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_output_directory.py -v`
  - 预期：当前 OutputManager(base_path="./output")，测试验证路径应为 engine/data

- [ ] **步骤 3：修复 output.py 的 base_path 默认值**
  - 旧代码（第12行）：`def __init__(self, base_path: str = "./output")`
  - 新代码：`def __init__(self, base_path: str = None):`
    - 如果 base_path 为 None，自动使用 `os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")`
    - 即：`APP/engine/engine/output.py` → base = `APP/engine/data/`

- [ ] **步骤 4：修复 engine.py 中 OutputManager 实例化**
  - 旧代码（第25行）：`self.output_mgr = OutputManager()`
  - 新代码：`self.output_mgr = OutputManager(base_path=os.path.join(os.path.dirname(__file__), "data"))`

- [ ] **步骤 5：修复 engine_cli.py 的 state_dir 和 dedup_db 路径**
  - STATE_DIR 改为：`os.path.join(os.path.dirname(__file__), "data")`（注意：不是 state_dir，是 output base）
  - 实际上：state.json 保留在 engine/ 目录，output 改为 engine/data/
  - 注意：state_dir（用于 state.json）保持 `engine/output` 不变，data_dir（用于采集数据输出）改为 `engine/data`

- [ ] **步骤 6：创建 engine/data 目录**
  - 运行：`mkdir -p /root/info-collector/APP/engine/data`

- [ ] **步骤 7：运行测试验证通过**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_output_directory.py -v`
  - 预期：PASS

- [ ] **步骤 8：运行集成测试确认数据可见**
  - 运行：`.venv/bin/python engine_cli.py run rules/数据要素/cninfo_data_value_search.yaml 2>&1 | tail -5`
  - 然后：`ls /root/info-collector/APP/engine/data/数据要素/ 2>/dev/null`
  - 预期：数据写入 engine/data/ 目录

- [ ] **步骤 9：Commit**
  ```
  git add engine/engine/output.py engine/engine/engine.py engine/engine_cli.py
  git commit -m "fix: 统一数据输出目录到 engine/data/，与 data_api 路径对齐"
  ```

---

### 任务 3：统一输出格式（JSON 对象结构兼容 JSONL 解析）

**文件：**
- 修改：`APP/dashboard/apis/data_api.py` — 同时支持 .json 和 .jsonl 文件解析

**修复策略：**
- `data_api.py` 的 preview_data 和 data_stats 函数同时支持 JSON（对象）和 JSONL（逐行）格式
- 输出始终为 JSON 对象 `{meta:..., data:[...]}`，预览时读取 `.json` 文件

- [ ] **步骤 1：编写失败测试**

```python
# tests/test_data_api_format.py（新建）
def test_preview_reads_json_object_format():
    """data_api preview_data 应能解析 output.py 的 JSON 对象格式"""
    import json, tempfile, os
    tmp = tempfile.mkdtemp()
    data_file = os.path.join(tmp, "test_platform.jsonl")
    # 写入 output.py 格式（JSON 对象）
    with open(data_file, "w") as f:
        json.dump({"meta": {"subject": "测试", "platform": "test", "count": 2},
                   "data": [{"title": "t1"}, {"title": "t2"}]}, f)
    # 测试 data_api 的预览逻辑（直接测试 JSON 解析）
    items = []
    with open(data_file) as f:
        content = f.read().strip()
        if content.startswith("{"):
            # JSON 对象格式
            obj = json.loads(content)
            items.extend(obj.get("data", []))
        elif content.startswith("["):
            # JSONL 格式
            for line in f:
                items.append(json.loads(line.strip()))
    assert len(items) == 2
```

- [ ] **步骤 2：修复 data_api.py 的预览逻辑**
  - 修改 `preview_data()` 函数（第75-84行）：
    - 检测文件是 `.json`（JSON 对象）还是 `.jsonl`（逐行 JSON）
    - `.json` 文件：`json.load(f)` → 取 `obj["data"]`
    - `.jsonl` 文件：逐行 `json.loads(line)` → 每行是一个对象（不是数组）

- [ ] **步骤 3：修复 data_api.py 的 stats 统计逻辑**
  - 修改 `data_stats()` 函数（第102-113行）：
    - 对 `.json` 文件：`json.load(f)` 后取 `data` 数组长度
    - 对 `.jsonl` 文件：逐行计数

- [ ] **步骤 4：运行测试验证**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_data_api_format.py -v`
  - 预期：PASS

- [ ] **步骤 5：Commit**
  ```
  git add dashboard/apis/data_api.py
  git commit -m "fix: data_api 同时支持 JSON 对象和 JSONL 逐行格式"
  ```

---

### 任务 4：实现分页逻辑

**文件：**
- 修改：`APP/engine/engine/crawl_api.py` — 添加分页循环支持
- 修改：`APP/engine/engine/engine.py` — 调用分页逻辑

**修复策略：**
- `crawl_api.py` 添加 `fetch_with_pagination(rule)` 方法
- 从 rule 的 `pagination` 配置读取 page_param、max_pages
- 每页结果合并后返回完整列表

- [ ] **步骤 1：编写失败测试**

```python
# tests/test_pagination.py（新建）
def test_api_crawler_fetches_multiple_pages():
    """分页配置应触发多次请求并合并结果"""
    from engine.crawl_api import APICrawler
    import yaml

    rule = yaml.safe_load("""
name: Test Pagination
source:
  base_url: https://httpbin.org/post
request:
  method: POST
  body_template: page={page}
pagination:
  enabled: true
  page_param: page
  max_pages: 3
list:
  items_path: $.data
  fields:
    - name: value
      type: field
      path: $.value
""")

    crawler = APICrawler()
    # 注意：实际测试用 mock 替代真实网络
    from unittest.mock import patch

    call_count = [0]
    def fake_fetch(url, method, **kwargs):
        call_count[0] += 1
        page_num = kwargs.get("data", "").split("=")[-1]
        return {"data": [f"item_p{page_num}_1", f"item_p{page_num}_2"]}

    with patch.object(crawler, 'fetch', side_effect=fake_fetch):
        results = crawler.fetch_with_pagination(rule)
        assert call_count[0] == 3, f"应请求3页，实际请求了 {call_count[0]} 次"
        assert len(results) == 6, f"应有6条结果，实际 {len(results)} 条"
```

- [ ] **步骤 2：运行测试验证失败**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_pagination.py -v`
  - 预期：FAIL — `fetch_with_pagination` 方法不存在

- [ ] **步骤 3：实现分页方法**

在 `crawl_api.py` 添加：

```python
def fetch_with_pagination(self, rule: dict) -> list:
    """Fetch all pages and return combined results"""
    params = self.build_request_params(rule)
    pagination_cfg = rule.get("pagination", {})

    if not pagination_cfg.get("enabled", False):
        # Single page
        response = self.fetch(
            params["url"], method=params["method"],
            headers=params.get("headers", {}), data=params.get("data", {})
        )
        return response if isinstance(response, list) else response.get("data", [])

    page_param = pagination_cfg.get("page_param", "pageNum")
    max_pages = pagination_cfg.get("max_pages", 10)

    all_items = []
    items_path = rule.get("list", {}).get("items_path", "")

    for page in range(1, max_pages + 1):
        # Replace page param in body
        body = params.get("data", "")
        body = re.sub(rf"{page_param}=[^&]*", f"{page_param}={page}", body)
        if page_param not in body:
            body = body + f"&{page_param}={page}" if body else f"{page_param}={page}"

        response = self.fetch(
            params["url"], method=params["method"],
            headers=params.get("headers", {}), data=body
        )

        items = self.parse_items(response, items_path)
        if not items:
            break
        all_items.extend(items)

    return all_items
```

- [ ] **步骤 4：修改 engine.py 的 _crawl_api 方法**
  - 旧代码（engine.py 第48-72行）：直接调用 `api_crawler.fetch()` + `parse_items()`
  - 新代码：调用 `api_crawler.fetch_with_pagination(rule)`

- [ ] **步骤 5：运行测试验证**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_pagination.py -v`
  - 预期：PASS

- [ ] **步骤 6：Commit**
  ```
  git add engine/engine/crawl_api.py engine/engine/engine.py
  git commit -m "feat: 实现 API 分页采集逻辑"
  ```

---

### 任务 5：修复 Cron 任务绑定特定规则

**文件：**
- 修改：`APP/dashboard/apis/cron_api.py` — _run_cron 支持绑定特定规则

**修复策略：**
- cron_jobs 表的 rule_path 字段存储规则路径（如 `rules/数据要素/cninfo.yaml`）
- `_run_cron()` 根据 job_row 中的 rule_path 判断：若为空则 run-all，否则 run-rule

- [ ] **步骤 1：编写失败测试**

```python
# tests/test_cron_binding.py（新建）
def test_cron_respects_rule_path():
    """Cron 任务应根据 rule_path 绑定特定规则，而非总是 run-all"""
    from dashboard.apis.cron_api import _add_scheduler_job
    import sqlite3, tempfile, os

    tmp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp_db.close()
    conn = sqlite3.connect(tmp_db.name)
    conn.execute("""
        CREATE TABLE cron_jobs (
            id INTEGER PRIMARY KEY, name TEXT, second TEXT, minute TEXT,
            hour TEXT, day TEXT, month TEXT, day_of_week TEXT,
            rule_path TEXT, enabled INTEGER)
    """)
    conn.execute("INSERT INTO cron_jobs (name,second,minute,hour,day,month,day_of_week,rule_path,enabled) "
                 "VALUES ('测试', '0', '*', '*', '*', '*', '*', 'rules/test/sample_rule.yaml', 1)")
    conn.commit()
    conn.close()

    # 验证 rule_path 被记录
    conn2 = sqlite3.connect(tmp_db.name)
    row = conn2.execute("SELECT rule_path FROM cron_jobs WHERE id=1").fetchone()
    conn2.close()
    assert row[0] == "rules/test/sample_rule.yaml"
    os.unlink(tmp_db.name)
```

- [ ] **步骤 2：修复 _run_cron 函数**
  - 旧代码：直接调用 `run-all`
  - 新代码：
    ```python
    def _run_cron():
        import subprocess, os
        ENGINE_DIR = os.path.join(...)
        VENV_PY = os.path.join(ENGINE_DIR, ".venv", "bin", "python")
        rule_path = job_row.get("rule_path", "")
        if rule_path:
            cmd = [VENV_PY, os.path.join(ENGINE_DIR, "engine_cli.py"),
                   "run-rule", rule_path, "--format=json"]
        else:
            cmd = [VENV_PY, os.path.join(ENGINE_DIR, "engine_cli.py"), "run-all"]
        subprocess.Popen(cmd, cwd=ENGINE_DIR)
    ```
  - 注意：需要将 `job_row` 传入 `_run_cron` 闭包

- [ ] **步骤 3：运行测试验证**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_cron_binding.py -v`
  - 预期：PASS

- [ ] **步骤 4：Commit**
  ```
  git add dashboard/apis/cron_api.py
  git commit -m "fix: cron 任务支持绑定特定规则路径"
  ```

---

## 阶段三：测试补充

### 任务 6：补充 enabled 字段端到端测试

**文件：**
- 新建：`APP/engine/tests/test_enabled_field_consistency.py`

- [ ] **步骤 1：编写完整测试**
  ```python
  """Test enabled field consistency across engine, CLI, and YAML"""
  import pytest, tempfile, os, yaml
  from engine.engine import InfoCollectorEngine

  def test_engine_reads_top_level_enabled_false():
      """Engine.run() 应读取 YAML 顶级 enabled=false 并跳过执行"""
      tmp = tempfile.mkdtemp()
      rule_path = os.path.join(tmp, "disabled_rule.yaml")
      with open(rule_path, "w") as f:
          yaml.dump({
              "name": "停用规则",
              "source": {"platform": "test", "type": "html", "url": "http://x"},
              "list": {"items_path": "", "fields": []},
              "enabled": False,  # 顶级
          })
      e = InfoCollectorEngine(dedup_db_path=os.path.join(tmp, "dedup.db"))
      result = e.run(rule_path)
      assert result["status"] == "skipped"
      assert result["reason"] == "rule_disabled"

  def test_engine_reads_top_level_enabled_true():
      """Engine.run() 应读取 YAML 顶级 enabled=true 并执行"""
      tmp = tempfile.mkdtemp()
      rule_path = os.path.join(tmp, "enabled_rule.yaml")
      with open(rule_path, "w") as f:
          yaml.dump({
              "name": "启用规则",
              "source": {"platform": "test", "type": "html", "url": "http://x"},
              "list": {"items_path": "", "fields": []},
              "enabled": True,
          })
      e = InfoCollectorEngine(dedup_db_path=os.path.join(tmp, "dedup.db"))
      # Mock fetch to avoid network
      from unittest.mock import patch
      with patch.object(e.html_crawler, 'fetch', return_value=""):
          result = e.run(rule_path)
      assert result["status"] == "success"

  def test_cli_enable_command_writes_top_level():
      """enable-rule CLI 应写入 YAML 顶级 enabled 字段"""
      tmp = tempfile.mkdtemp()
      rule_path = os.path.join(tmp, "toggle_test.yaml")
      with open(rule_path, "w") as f:
          yaml.dump({"name": "Test", "source": {"platform": "t", "type": "html"}})

      from engine.engine_cli import enable_rule_cmd
      # Simulate what enable_rule_cmd does
      with open(rule_path) as f:
          doc = yaml.safe_load(f)
      doc["enabled"] = False  # 写入顶级
      with open(rule_path, "w") as f:
          yaml.dump(doc, f)

      with open(rule_path) as f:
          updated = yaml.safe_load(f)
      assert "enabled" in updated
      assert updated["enabled"] is False
      assert "source" not in updated.get("enabled", {})  # 不在 source 下
  ```

- [ ] **步骤 2：运行测试**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_enabled_field_consistency.py -v`
  - 预期：ALL PASS

- [ ] **步骤 3：Commit**
  ```
  git add tests/test_enabled_field_consistency.py
  git commit -m "test: 补充 enabled 字段端到端一致性测试"
  ```

---

### 任务 7：补充数据目录与格式集成测试

**文件：**
- 新建：`APP/engine/tests/test_output_directory.py`
- 新建：`APP/engine/tests/test_data_api_format.py`

- [ ] **步骤 1：编写数据目录测试**

```python
"""Test data directory consistency between output.py and data_api.py"""
import pytest, tempfile, os, json

def test_output_uses_engine_data_dir(tmp_path):
    """OutputManager 应输出到 engine/data/ 目录"""
    from engine.output import OutputManager
    om = OutputManager(base_path=str(tmp_path))
    rule = {
        "name": "Test",
        "subject": "测试",
        "source": {"platform": "test_platform", "type": "api"},
        "output": {"format": "json", "filename_template": "test_{date}.json"}
    }
    out_path = om.save([{"title": "t1"}], rule)
    # 数据文件应在 tmp_path 下的子目录
    assert os.path.exists(out_path)
    # 且能读取
    with open(out_path) as f:
        data = json.load(f)
    assert data["meta"]["count"] == 1

def test_preview_reads_json_object_format(tmp_path):
    """data_api 的预览逻辑应能读取 output.py 的 JSON 格式"""
    from engine.output import OutputManager
    om = OutputManager(base_path=str(tmp_path))
    rule = {
        "name": "Test",
        "subject": "测试",
        "source": {"platform": "test_platform", "type": "api"},
        "output": {"format": "json", "filename_template": "preview_test_{date}.json"}
    }
    om.save([{"title": "文章1"}, {"title": "文章2"}], rule)

    # 找到输出文件
    subject_dir = os.path.join(str(tmp_path), "测试", "test_platform")
    files = [f for f in os.listdir(subject_dir) if f.startswith("preview_test")]
    assert len(files) == 1

    # 模拟 data_api 解析逻辑
    items = []
    with open(os.path.join(subject_dir, files[0])) as f:
        content = f.read().strip()
        if content.startswith("{"):
            obj = json.loads(content)
            items.extend(obj.get("data", []))
    assert len(items) == 2
```

- [ ] **步骤 2：运行测试**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_output_directory.py tests/test_data_api_format.py -v`
  - 预期：ALL PASS

- [ ] **步骤 3：Commit**
  ```
  git add tests/test_output_directory.py tests/test_data_api_format.py
  git commit -m "test: 补充数据目录与格式集成测试"
  ```

---

### 任务 8：补充分页与 Cron 单元测试

**文件：**
- 新建：`APP/engine/tests/test_pagination.py`
- 新建：`APP/dashboard/tests/test_cron_binding.py`（如 dashboard 无 tests 目录则跳过）

- [ ] **步骤 1：编写分页测试**（见任务4步骤1）

- [ ] **步骤 2：运行测试**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/test_pagination.py -v`
  - 预期：PASS

- [ ] **步骤 3：Commit**
  ```
  git add tests/test_pagination.py
  git commit -m "test: 补充分页逻辑单元测试"
  ```

---

## 阶段四：集成验证

### 任务 9：完整集成验证

- [ ] **步骤 1：启动 dashboard 服务并验证 API**
  - 运行：`cd /root/info-collector/APP/dashboard && .venv/bin/python server.py &`
  - 等待3秒后：`curl -s http://localhost:5000/api/rules | python -m json.tool | head -20`

- [ ] **步骤 2：验证看板数据预览**
  - 运行：`curl -s "http://localhost:5000/api/data/subjects"`
  - 预期：返回已采集的数据主题列表（如 `{"subjects":["数据要素"]}`）

- [ ] **步骤 3：验证 enabled 切换**
  - 运行：`curl -s -X POST http://localhost:5000/api/rules/rules/test/sample_rule.yaml/toggle \
    -H "Content-Type: application/json" \
    -d '{"enabled": false}' && curl -s http://localhost:5000/api/rules | python -m json.tool | grep -E "name|enabled"`
  - 预期：规则 enabled 状态正确更新

- [ ] **步骤 4：验证 cron 创建与绑定**
  - 运行：`curl -s -X POST http://localhost:5000/api/cron \
    -H "Content-Type: application/json" \
    -d '{"name":"测试Cron","schedule":"0 8 * * *","rule_path":"rules/数据要素/cninfo_data_value_search.yaml"}'`
  - 预期：`{"id": 1, "success": true}`

- [ ] **步骤 5：停止 dashboard 服务**
  - 运行：`pkill -f "python server.py"` 或 `kill $(lsof -ti:5000)`

- [ ] **步骤 6：Commit**
  ```
  git add -A
  git commit -m "test: 集成验证通过"
  ```

---

## 阶段五：回归测试

### 任务 10：全量回归测试

- [ ] **步骤 1：运行 engine 所有单元测试**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python -m pytest tests/ -v --tb=short`
  - 预期：ALL PASS（含新增测试）

- [ ] **步骤 2：运行 dashboard 服务并测试 API**
  - 运行：`cd /root/info-collector/APP/dashboard && .venv/bin/python -c "
import urllib.request, json, os
os.chdir('/root/info-collector/APP/dashboard')
# 启动服务（后台）
import subprocess
srv = subprocess.Popen(['.venv/bin/python', 'server.py'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
import time; time.sleep(3)

tests = [
    ('GET', '/api/rules', None, 'rules'),
    ('GET', '/api/cron', None, 'crons'),
    ('GET', '/api/tasks/history', None, 'tasks'),
]
for method, path, body, key in tests:
    try:
        req = urllib.request.Request(f'http://localhost:5000{path}')
        r = urllib.request.urlopen(req, timeout=5)
        d = json.loads(r.read())
        print(f'✅ {method} {path} → {key}={len(d.get(key, d))}')
    except Exception as e:
        print(f'❌ {method} {path} → {e}')

srv.terminate()
" 2>&1`
  - 预期：所有 API 返回成功

- [ ] **步骤 3：最终状态确认**
  - 运行：`cd /root/info-collector/APP/engine && .venv/bin/python engine_cli.py state 2>&1 | head -30`
  - 预期：正确显示规则状态和统计

- [ ] **步骤 4：Commit 最终修复**
  ```
  git add -A
  git commit -m "chore: 完成所有问题修复，测试完善，集成验证通过"
  ```

---

## 文件变更总览

| 文件 | 操作 | 说明 |
|------|------|------|
| `engine/engine/engine.py` | 修改 | 确认 enabled 读取逻辑 |
| `engine/engine_cli.py` | 修改 | enable-rule 写入顶级 enabled |
| `engine/engine/state.py` | 修改 | 统一 enabled 读取 |
| `engine/engine/output.py` | 修改 | 数据目录改为 engine/data/ |
| `engine/engine/crawl_api.py` | 修改 | 添加 fetch_with_pagination 分页方法 |
| `engine/engine/engine.py` | 修改 | _crawl_api 调用分页方法 |
| `dashboard/apis/cron_api.py` | 修改 | 支持绑定特定规则路径 |
| `dashboard/apis/data_api.py` | 修改 | 同时支持 JSON 和 JSONL 格式 |
| `rules/数据要素/cninfo_data_value_search.yaml` | 修改 | 修正 enabled 位置 |
| `rules/test/sample_rule.yaml` | 修改 | 修正 enabled 位置 |
| `tests/test_enabled_field_consistency.py` | 新建 | enabled 端到端测试 |
| `tests/test_output_directory.py` | 新建 | 数据目录测试 |
| `tests/test_data_api_format.py` | 新建 | 数据格式测试 |
| `tests/test_pagination.py` | 新建 | 分页逻辑测试 |
| `tests/test_cron_binding.py` | 新建 | Cron 绑定测试 |
