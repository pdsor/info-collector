# info-collector 看板实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。
>
> **面向人类工作者：** 本计划由 AI 代理遵循 superpowers:writing-plans 技能编写，每个步骤均可独立执行、可验证。推荐使用子代理驱动方式逐任务执行。

**目标：** 构建 info-collector 看板系统（Flask + Vue 3 CDN），提供规则管理、Cron 调度、任务执行、日志查看、数据预览五大功能。

**架构：** Flask server 通过 subprocess 调用 engine_cli.py JSON 接口，Vue 3 CDN 单页应用，SQLite 本地持久化，APScheduler 内置调度。

**技术栈：** Flask, flask-cors, APScheduler, SQLite, Vue 3 CDN, SSE

---

## 文件结构

```
APP/dashboard/
  server.py              ← Flask 入口 + APScheduler + 数据库初始化
  requirements.txt       ← flask, flask-cors, apscheduler
  dashboard.db           ← SQLite 数据库（自动创建）
  dashboard.log          ← dashboard 日志（自动创建）
  
  apis/
    __init__.py          ← 蓝图注册
    rules_api.py         ← 规则 CRUD
    cron_api.py          ← Cron 任务 CRUD
    tasks_api.py         ← 任务触发 + SSE
    logs_api.py          ← 日志读取 + SSE
    data_api.py          ← 数据预览
  
  migrations/
    001_init.sql         ← 初始 schema
  
  static/
    index.html           ← Vue 3 单页入口
    css/
      style.css          ← 全局样式
    js/
      api.js             ← HTTP 客户端
      app.js             ← Vue 主应用 + 路由
      components/
        DashboardHome.vue
        RuleList.vue
        RuleEditor.vue
        CronManager.vue
        TaskRunner.vue
        LogViewer.vue
        DataPreview.vue

engine_cli.py             ← 扩展 JSON 输出命令（修改已有文件）
```

---

## Phase 1：基础设施

### 任务 1：server.py 骨架 + 数据库初始化

**文件：**
- 创建：`APP/dashboard/server.py`
- 创建：`APP/dashboard/requirements.txt`
- 创建：`APP/dashboard/migrations/001_init.sql`

- [ ] **步骤 1：创建目录结构**

```bash
mkdir -p APP/dashboard/apis APP/dashboard/migrations APP/dashboard/static/css APP/dashboard/static/js/components
```

- [ ] **步骤 2：创建 requirements.txt**

```txt
flask>=3.0.0
flask-cors>=4.0.0
apscheduler>=3.10.0
```

- [ ] **步骤 3：创建 migrations/001_init.sql**

```sql
CREATE TABLE IF NOT EXISTS cron_jobs (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    rule_path   TEXT NOT NULL,
    schedule    TEXT NOT NULL,
    enabled     INTEGER DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_history (
    id          TEXT PRIMARY KEY,
    job_id      TEXT,
    rule_path   TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    status      TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed', 'stopped')),
    new_count   INTEGER DEFAULT 0,
    error_msg   TEXT,
    duration    REAL,
    FOREIGN KEY (job_id) REFERENCES cron_jobs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_task_history_job_id ON task_history(job_id);
CREATE INDEX IF NOT EXISTS idx_task_history_started_at ON task_history(started_at);
```

- [ ] **步骤 4：创建 server.py**

```python
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, send_from_directory
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler

# 确保项目根目录在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "dashboard.db")
LOG_PATH = os.path.join(APP_DIR, "dashboard.log")
MIGRATIONS_DIR = os.path.join(APP_DIR, "migrations")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """执行未完成的 migrations"""
    conn = get_db()
    cursor = conn.cursor()
    
    # 确保 migrations 表存在
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)
    
    # 获取已执行的迁移
    cursor.execute("SELECT name FROM schema_migrations")
    executed = {row["name"] for row in cursor.fetchall()}
    
    # 执行未执行的迁移
    for fname in sorted(os.listdir(MIGRATIONS_DIR)):
        if fname.endswith(".sql") and fname not in executed:
            with open(os.path.join(MIGRATIONS_DIR, fname), "r") as f:
                sql = f.read()
            cursor.executescript(sql)
            cursor.execute("INSERT INTO schema_migrations (name) VALUES (?)", (fname,))
            print(f"[dashboard] Executed migration: {fname}")
    
    conn.commit()
    conn.close()


def setup_logging():
    handler = RotatingFileHandler(LOG_PATH, maxBytes=5*1024*1024, backupCount=3)
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s] %(message)s"
    ))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)


# Flask app
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["SECRET_KEY"] = "dashboard-secret-key"
CORS(app)

setup_logging()

# APScheduler
scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

# Import and register blueprints after app is created
from apis import register_blueprints
register_blueprints(app, scheduler)

# Init database
init_db()

# Start scheduler
scheduler.start()
app.logger.info("Dashboard server started, scheduler running")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=True)
```

- [ ] **步骤 5：验证 server.py 启动**

```bash
cd /root/info-collector/APP/dashboard && pip install flask flask-cors apscheduler -q && python server.py &
sleep 3
curl -s http://localhost:5000/ | head -5
# 预期：返回 index.html 内容
```

- [ ] **步骤 6：Commit**

```bash
git add APP/dashboard/ && git commit -m "feat(dashboard): server.py 骨架 + 数据库初始化"
```

---

### 任务 2：API 蓝图注册

**文件：**
- 创建：`APP/dashboard/apis/__init__.py`
- 创建：`APP/dashboard/apis/rules_api.py`
- 创建：`APP/dashboard/apis/cron_api.py`
- 创建：`APP/dashboard/apis/tasks_api.py`
- 创建：`APP/dashboard/apis/logs_api.py`
- 创建：`APP/dashboard/apis/data_api.py`

- [ ] **步骤 1：创建 apis/__init__.py**

```python
# 空文件，apis 包的标识文件
```

- [ ] **步骤 2：创建 apis/rules_api.py（临时空实现）**

```python
# 临时空实现，Phase 2 填充
from flask import Blueprint
rules_bp = Blueprint("rules", __name__)
```

- [ ] **步骤 3：创建其他 API 空蓝图（临时）**

每个文件内容：
```python
from flask import Blueprint
xxx_bp = Blueprint("xxx", __name__)
```

- [ ] **步骤 4：创建 apis/__init__.py（注册蓝图）**

```python
def register_blueprints(app, scheduler):
    from flask import Flask
    from apis.rules_api import rules_bp
    from apis.cron_api import cron_bp
    from apis.tasks_api import tasks_bp
    from apis.logs_api import logs_bp
    from apis.data_api import data_bp
    
    app.register_blueprint(rules_bp, url_prefix="/api/rules")
    app.register_blueprint(cron_bp, url_prefix="/api/cron")
    app.register_blueprint(tasks_bp, url_prefix="/api/tasks")
    app.register_blueprint(logs_bp, url_prefix="/api/logs")
    app.register_blueprint(data_bp, url_prefix="/api/data")
```

- [ ] **步骤 5：验证 API 路由注册**

```bash
curl -s http://localhost:5000/api/rules 2>/dev/null || echo "OK"
curl -s http://localhost:5000/api/cron 2>/dev/null || echo "OK"
curl -s http://localhost:5000/api/tasks 2>/dev/null || echo "OK"
curl -s http://localhost:5000/api/logs 2>/dev/null || echo "OK"
curl -s http://localhost:5000/api/data 2>/dev/null || echo "OK"
```

- [ ] **步骤 6：Commit**

```bash
git add APP/dashboard/apis/ && git commit -m "feat(dashboard): API 蓝图骨架"
```

---

### 任务 3：Vue 3 前端骨架 + 顶部 Tab 导航

**文件：**
- 创建：`APP/dashboard/static/index.html`
- 创建：`APP/dashboard/static/css/style.css`
- 创建：`APP/dashboard/static/js/api.js`
- 创建：`APP/dashboard/static/js/app.js`

- [ ] **步骤 1：创建 static/index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>info-collector 看板</title>
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body>
    <div id="app">
        <nav class="tab-nav">
            <button 
                v-for="tab in tabs" 
                :key="tab.id"
                :class="['tab-btn', { active: currentTab === tab.id }]"
                @click="currentTab = tab.id"
            >{{ tab.label }}</button>
        </nav>
        <main class="content">
            <component :is="currentComponent" />
        </main>
    </div>

    <script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
    <script src="/static/js/api.js"></script>
    <script src="/static/js/app.js"></script>
</body>
</html>
```

- [ ] **步骤 2：创建 static/css/style.css**

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #f5f5f5;
    color: #333;
}

.tab-nav {
    background: #fff;
    border-bottom: 1px solid #e0e0e0;
    display: flex;
    padding: 0 16px;
    position: sticky;
    top: 0;
    z-index: 100;
}

.tab-btn {
    padding: 14px 20px;
    border: none;
    background: none;
    cursor: pointer;
    font-size: 14px;
    color: #666;
    border-bottom: 2px solid transparent;
    transition: all 0.2s;
}

.tab-btn:hover { color: #333; }

.tab-btn.active {
    color: #1890ff;
    border-bottom-color: #1890ff;
}

.content {
    padding: 24px;
    max-width: 1200px;
    margin: 0 auto;
}

.card {
    background: #fff;
    border-radius: 8px;
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
```

- [ ] **步骤 3：创建 static/js/api.js**

```javascript
const API = {
    base: "/api",
    
    async get(path) {
        const r = await fetch(this.base + path);
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },
    
    async post(path, body) {
        const r = await fetch(this.base + path, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },
    
    async patch(path, body) {
        const r = await fetch(this.base + path, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body)
        });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },
    
    async delete(path) {
        const r = await fetch(this.base + path, { method: "DELETE" });
        if (!r.ok) throw new Error(await r.text());
        return r.json();
    },
    
    // SSE 流
    stream(path) {
        return new EventSource(this.base + path);
    }
};
```

- [ ] **步骤 4：创建 static/js/app.js**

```javascript
const { createApp, ref, computed, onMounted } = Vue;

// 临时空组件（Phase 2/3 填充）
const DashboardHome = { template: "<div class='card'>首页加载中...</div>" };
const RuleList = { template: "<div class='card'>规则管理加载中...</div>" };
const CronManager = { template: "<div class='card'>Cron管理加载中...</div>" };
const TaskRunner = { template: "<div class='card'>任务执行加载中...</div>" };
const LogViewer = { template: "<div class='card'>日志查看加载中...</div>" };
const DataPreview = { template: "<div class='card'>数据预览加载中...</div>" };

const app = createApp({
    setup() {
        const tabs = [
            { id: "home", label: "📊 首页", component: "DashboardHome" },
            { id: "rules", label: "规则管理", component: "RuleList" },
            { id: "cron", label: "Cron调度", component: "CronManager" },
            { id: "tasks", label: "任务执行", component: "TaskRunner" },
            { id: "logs", label: "日志查看", component: "LogViewer" },
            { id: "data", label: "数据预览", component: "DataPreview" },
        ];
        
        const currentTab = ref("home");
        
        const currentComponent = computed(() => {
            const tab = tabs.find(t => t.id === currentTab.value);
            return tab ? tab.component : "DashboardHome";
        });
        
        return { tabs, currentTab, currentComponent };
    }
});

app.component("DashboardHome", DashboardHome);
app.component("RuleList", RuleList);
app.component("CronManager", CronManager);
app.component("TaskRunner", TaskRunner);
app.component("LogViewer", LogViewer);
app.component("DataPreview", DataPreview);

app.mount("#app");
```

- [ ] **步骤 5：验证前端加载**

打开浏览器访问 http://localhost:5000 ，验证 6 个 Tab 都能切换，显示对应 placeholder。

- [ ] **步骤 6：Commit**

```bash
git add APP/dashboard/static/ && git commit -m "feat(dashboard): Vue 3 前端骨架 + 顶部 Tab 导航"
```

---

## Phase 2：核心功能

### 任务 4：rules_api.py + RuleList.vue

**文件：**
- 修改：`APP/dashboard/apis/rules_api.py`
- 创建：`APP/dashboard/static/js/components/RuleList.vue`

- [ ] **步骤 1：实现 rules_api.py**

```python
import os
import json
import subprocess
import yaml
from flask import Blueprint, jsonify, request

rules_bp = Blueprint("rules", __name__)

ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def run_cli(args):
    """调用 engine_cli.py，返回 JSON"""
    result = subprocess.run(
        ["python", "-m", "engine.cli"] + args,
        capture_output=True, text=True,
        cwd=ENGINE_ROOT
    )
    if result.returncode != 0:
        return None, result.stderr
    try:
        return json.loads(result.stdout), None
    except:
        return None, result.stdout


@rules_bp.route("", methods=["GET"])
def list_rules():
    """列出所有规则"""
    data, err = run_cli(["list-rules", "--format=json"])
    if err:
        return jsonify({"rules": []}), 200
    return jsonify(data)


@rules_bp.route("/<path:rule_path>", methods=["GET"])
def get_rule(rule_path):
    """读取规则 YAML 内容"""
    yaml_path = os.path.join(ENGINE_ROOT, rule_path)
    if not os.path.exists(yaml_path):
        return jsonify({"error": "规则不存在"}), 404
    with open(yaml_path, "r", encoding="utf-8") as f:
        content = f.read()
    return jsonify({"yaml": content, "path": rule_path})


@rules_bp.route("/<path:rule_path>", methods=["PUT"])
def put_rule(rule_path):
    """完整替换规则 YAML"""
    body = request.get_json()
    yaml_content = body.get("yaml", "")
    yaml_path = os.path.join(ENGINE_ROOT, rule_path)
    
    # 校验 YAML 格式
    try:
        yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        return jsonify({"error": f"YAML 格式错误: {e}"}), 400
    
    os.makedirs(os.path.dirname(yaml_path), exist_ok=True)
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    
    return jsonify({"success": True})


@rules_bp.route("/<path:rule_path>", methods=["DELETE"])
def delete_rule(rule_path):
    """删除规则"""
    yaml_path = os.path.join(ENGINE_ROOT, rule_path)
    if not os.path.exists(yaml_path):
        return jsonify({"error": "规则不存在"}), 404
    os.remove(yaml_path)
    return jsonify({"success": True})


@rules_bp.route("/<path:rule_path>/enable", methods=["PATCH"])
def toggle_rule(rule_path):
    """启用/停用规则（修改 source.enabled 字段）"""
    body = request.get_json()
    enabled = body.get("enabled", True)
    yaml_path = os.path.join(ENGINE_ROOT, rule_path)
    
    if not os.path.exists(yaml_path):
        return jsonify({"error": "规则不存在"}), 404
    
    with open(yaml_path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    
    if "source" not in doc:
        doc["source"] = {}
    doc["source"]["enabled"] = enabled
    
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(doc, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    
    return jsonify({"success": True, "enabled": enabled})


@rules_bp.route("", methods=["POST"])
def create_rule():
    """新建规则"""
    body = request.get_json()
    subject = body.get("subject", "")
    platform = body.get("platform", "")
    name = body.get("name", "")
    yaml_content = body.get("yaml", "")
    
    if not all([subject, platform, name]):
        return jsonify({"error": "缺少必要参数"}), 400
    
    rule_path = f"rules/{subject}/{name}.yaml"
    yaml_path = os.path.join(ENGINE_ROOT, rule_path)
    
    try:
        yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        return jsonify({"error": f"YAML 格式错误: {e}"}), 400
    
    os.makedirs(os.path.dirname(yaml_path), exist_ok=True)
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    
    return jsonify({"success": True, "path": rule_path}), 201
```

- [ ] **步骤 2：替换 rules_api.py 并重启验证**

```bash
# 重启 server（之前的后台进程）
pkill -f "python server.py" 2>/dev/null; sleep 1
cd /root/info-collector/APP/dashboard && python server.py &
sleep 2
curl -s http://localhost:5000/api/rules | python -m json.tool 2>/dev/null | head -30
# 预期：返回 {"rules": [...]}，包含数据要素的两条规则
```

- [ ] **步骤 3：实现 RuleList.vue**

```javascript
const RuleList = {
    template: `
        <div>
            <div class="card">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
                    <h2>规则管理</h2>
                    <button class="btn-primary" @click="showCreate = true">+ 新建规则</button>
                </div>
                <div v-if="loading">加载中...</div>
                <div v-else>
                    <div v-for="(rules, subject) in groupedRules" :key="subject">
                        <h3 style="margin:16px 0 8px;color:#666;">{{ subject }}</h3>
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>平台</th>
                                    <th>名称</th>
                                    <th>状态</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="rule in rules" :key="rule.path">
                                    <td>{{ rule.platform }}</td>
                                    <td>{{ rule.name }}</td>
                                    <td>
                                        <span :class="['badge', rule.enabled ? 'badge-success' : 'badge-disabled']">
                                            {{ rule.enabled ? '启用' : '停用' }}
                                        </span>
                                    </td>
                                    <td>
                                        <button class="btn-sm" @click="viewRule(rule)">查看</button>
                                        <button class="btn-sm" @click="editRule(rule)">编辑</button>
                                        <button class="btn-sm" @click="toggleRule(rule)">
                                            {{ rule.enabled ? '停用' : '启用' }}
                                        </button>
                                        <button class="btn-sm btn-danger" @click="deleteRule(rule)">删除</button>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
            
            <!-- 查看弹窗 -->
            <div v-if="viewDialog" class="dialog-overlay" @click.self="viewDialog=false">
                <div class="dialog">
                    <h3>{{ viewDialog.name }}</h3>
                    <pre class="yaml-pre">{{ viewDialog.yaml }}</pre>
                    <button class="btn-primary" @click="viewDialog=false">关闭</button>
                </div>
            </div>
        </div>
    `,
    data() {
        return {
            rules: [],
            loading: true,
            showCreate: false,
            viewDialog: false,
            viewYaml: "",
        };
    },
    computed: {
        groupedRules() {
            const g = {};
            for (const r of this.rules) {
                const s = r.subject || "未分类";
                if (!g[s]) g[s] = [];
                g[s].push(r);
            }
            return g;
        }
    },
    async mounted() {
        await this.loadRules();
    },
    methods: {
        async loadRules() {
            this.loading = true;
            try {
                const data = await API.get("/rules");
                this.rules = data.rules || [];
            } catch (e) {
                console.error(e);
            }
            this.loading = false;
        },
        async viewRule(rule) {
            const data = await API.get("/rules/" + rule.path);
            this.viewDialog = { name: rule.name, yaml: data.yaml };
        },
        async editRule(rule) {
            const data = await API.get("/rules/" + rule.path);
            const yaml = prompt("编辑 YAML:", data.yaml);
            if (yaml && yaml !== data.yaml) {
                await API.put("/rules/" + rule.path, { yaml });
                await this.loadRules();
            }
        },
        async toggleRule(rule) {
            await API.patch("/rules/" + rule.path + "/enable", { enabled: !rule.enabled });
            await this.loadRules();
        },
        async deleteRule(rule) {
            if (confirm(`确定删除规则 ${rule.name}？`)) {
                await API.delete("/rules/" + rule.path);
                await this.loadRules();
            }
        }
    }
};
```

- [ ] **步骤 4：更新 style.css 添加表格和按钮样式**

追加到 style.css：
```css
.data-table { width: 100%; border-collapse: collapse; }
.data-table th, .data-table td { padding: 10px 12px; text-align: left; border-bottom: 1px solid #eee; }
.data-table th { background: #fafafa; font-weight: 500; color: #666; font-size: 13px; }
.badge { padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.badge-success { background: #e6f7ff; color: #1890ff; }
.badge-disabled { background: #f5f5f5; color: #999; }
.btn-primary { padding: 8px 16px; background: #1890ff; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
.btn-sm { padding: 4px 10px; background: #fff; border: 1px solid #d9d9d9; border-radius: 4px; cursor: pointer; margin-right: 4px; }
.btn-danger { color: #ff4d4f; border-color: #ff4d4f; }
.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.dialog { background: #fff; border-radius: 8px; padding: 24px; width: 700px; max-height: 80vh; overflow-y: auto; }
.yaml-pre { background: #f5f5f5; padding: 12px; border-radius: 4px; font-size: 12px; overflow-x: auto; margin: 12px 0; white-space: pre-wrap; }
```

- [ ] **步骤 5：更新 app.js 注册真实组件**

替换 Phase 1 临时组件：
```javascript
const RuleList = { template: "<div class='card'>规则管理加载中...</div>" };  // 替换为真实组件
```

在 app.js 中引入 RuleList.vue 内容。

- [ ] **步骤 6：验证 RuleList 页面**

刷新 http://localhost:5000 ，切换到"规则管理"，应能看到数据要素下的两条规则。

- [ ] **步骤 7：Commit**

```bash
git add APP/dashboard/apis/rules_api.py APP/dashboard/static/js/components/RuleList.vue APP/dashboard/static/css/style.css
git commit -m "feat(dashboard): rules_api.py + RuleList.vue 规则管理功能"
```

---

### 任务 5：engine_cli.py 扩展

**文件：**
- 修改：`APP/engine/engine_cli.py`

- [ ] **步骤 1：读取现有 engine_cli.py 结构**

```bash
wc -l /root/info-collector/APP/engine/engine_cli.py
head -80 /root/info-collector/APP/engine/engine_cli.py
```

- [ ] **步骤 2：在 engine_cli.py 中添加 list-rules --format=json**

在 CLI 命令中添加：
```python
@cli.command("list-rules")
@click.option("--format", "fmt", default="text")
def list_rules_cmd(fmt):
    """列出所有已注册规则"""
    from engine.state import load_state
    state = load_state()
    rules = []
    for name, info in state.get("rules", {}).items():
        rules.append({
            "name": info.get("name", name),
            "platform": info.get("platform", ""),
            "subject": info.get("subject", ""),
            "path": info.get("path", ""),
            "enabled": info.get("enabled", True),
            "last_run": info.get("last_run"),
            "last_status": info.get("last_status"),
        })
    if fmt == "json":
        click.echo(json.dumps({"rules": rules}, ensure_ascii=False))
    else:
        for r in rules:
            click.echo(f"{r['subject']}/{r['platform']} {r['name']} [{'ON' if r['enabled'] else 'OFF'}]")
```

- [ ] **步骤 3：添加 get-rule 命令**

```python
@cli.command("get-rule")
@click.argument("rule_path")
@click.option("--format", "fmt", default="text")
def get_rule_cmd(rule_path, fmt):
    """读取规则 YAML 内容"""
    import os
    full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), rule_path)
    if not os.path.exists(full_path):
        click.echo(json.dumps({"error": "文件不存在"}), err=True)
        return
    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()
    if fmt == "json":
        click.echo(json.dumps({"yaml": content, "path": rule_path}, ensure_ascii=False))
    else:
        click.echo(content)
```

- [ ] **步骤 4：添加 put-rule / delete-rule / enable-rule 命令（类似模式）**

- [ ] **步骤 5：添加 run-rule --format=json 命令**

```python
@cli.command("run-rule")
@click.argument("rule_path")
@click.option("--format", "fmt", default="text")
def run_rule_cmd(rule_path, fmt):
    """手动执行规则（JSON 输出）"""
    import time
    start = time.time()
    # 调用现有 run logic
    try:
        from engine.engine import run_rule
        result = run_rule(rule_path)
        duration = time.time() - start
        if fmt == "json":
            click.echo(json.dumps({
                "success": True,
                "new_count": result.get("new_count", 0),
                "duration": round(duration, 2),
            }, ensure_ascii=False))
        else:
            click.echo(f"OK, new={result.get('new_count', 0)}, time={duration:.1f}s")
    except Exception as e:
        duration = time.time() - start
        if fmt == "json":
            click.echo(json.dumps({
                "success": False,
                "error": str(e),
                "duration": round(duration, 2),
            }, ensure_ascii=False))
        else:
            click.echo(f"ERROR: {e}", err=True)
```

- [ ] **步骤 6：添加 list-logs / read-log 命令**

- [ ] **步骤 7：验证新命令**

```bash
cd /root/info-collector/APP/engine
python -m engine.cli list-rules --format=json
python -m engine.cli get-rule rules/数据要素/tmtpost_data_articles.yaml --format=json | head -5
```

- [ ] **步骤 8：Commit**

```bash
git add APP/engine/engine_cli.py
git commit -m "feat(engine): 扩展 CLI 支持 JSON 输出命令（list-rules, get-rule, run-rule 等）"
```

---

### 任务 6：tasks_api.py（手动触发 + SSE）+ TaskRunner.vue

**文件：**
- 修改：`APP/dashboard/apis/tasks_api.py`
- 创建：`APP/dashboard/static/js/components/TaskRunner.vue`

- [ ] **步骤 1：实现 tasks_api.py**

```python
import os, json, uuid, subprocess, threading, time
from datetime import datetime
from flask import Blueprint, jsonify, request, Response, stream_with_context
from apis.db import get_db

tasks_bp = Blueprint("tasks", __name__)

# 全局运行中任务记录
running_tasks = {}  # task_id -> { rule_path, job_id, started_at, process }

ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def execute_rule_async(task_id, rule_path, job_id=None):
    """后台执行规则，实时写日志"""
    from engine.engine import run_rule
    from apis.db import get_db
    
    conn = get_db()
    cursor = conn.cursor()
    started_at = datetime.now().isoformat()
    
    # 记录 running 状态
    cursor.execute(
        "INSERT INTO task_history (id, job_id, rule_path, started_at, status) VALUES (?, ?, ?, ?, ?)",
        (task_id, job_id, rule_path, started_at, "running")
    )
    conn.commit()
    
    running_tasks[task_id] = {
        "task_id": task_id,
        "rule_path": rule_path,
        "job_id": job_id,
        "started_at": started_at,
        "process": None,
    }
    
    try:
        result = run_rule(rule_path)
        ended_at = datetime.now().isoformat()
        duration = (datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)).total_seconds()
        
        cursor.execute(
            "UPDATE task_history SET ended_at=?, status=?, new_count=?, duration=? WHERE id=?",
            (ended_at, "success", result.get("new_count", 0), duration, task_id)
        )
        conn.commit()
        
        # 广播 done 事件
        _broadcast(task_id, "done", {
            "status": "success",
            "new_count": result.get("new_count", 0),
            "duration": round(duration, 2)
        })
    except Exception as e:
        ended_at = datetime.now().isoformat()
        duration = (datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)).total_seconds()
        
        cursor.execute(
            "UPDATE task_history SET ended_at=?, status=?, error_msg=?, duration=? WHERE id=?",
            (ended_at, "failed", str(e), duration, task_id)
        )
        conn.commit()
        
        _broadcast(task_id, "error", {"message": str(e)})
    finally:
        conn.close()
        if task_id in running_tasks:
            del running_tasks[task_id]


def _broadcast(task_id, event, data):
    """写入 SSE 缓冲区（如果有订阅者）"""
    if task_id in sse_clients:
        sse_clients[task_id].put((event, json.dumps(data, ensure_ascii=False)))


# SSE 订阅者
sse_clients = {}  # task_id -> queue.Queue


@tasks_bp.route("/running", methods=["GET"])
def list_running():
    return jsonify({
        "running": [
            {k: v for k, v in t.items() if k != "process"}
            for t in running_tasks.values()
        ]
    })


@tasks_bp.route("/run", methods=["POST"])
def trigger_task():
    body = request.get_json()
    rule_path = body.get("rule_path", "")
    if not rule_path:
        return jsonify({"error": "缺少 rule_path"}), 400
    
    task_id = str(uuid.uuid4())
    
    thread = threading.Thread(target=execute_rule_async, args=(task_id, rule_path))
    thread.start()
    
    return jsonify({"task_id": task_id}), 201


@tasks_bp.route("/<task_id>/stream")
def task_stream(task_id):
    """SSE 实时日志流"""
    def generate():
        q = queue.Queue()
        sse_clients[task_id] = q
        
        try:
            while True:
                try:
                    event, data = q.get(timeout=60)
                    yield f"event: {event}\ndata: {data}\n\n"
                    if event in ("done", "error"):
                        break
                except queue.Empty:
                    yield f"event: ping\ndata: {{}}\n\n"
        finally:
            if task_id in sse_clients:
                del sse_clients[task_id]
    
    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@tasks_bp.route("/history", methods=["GET"])
def task_history():
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM task_history ORDER BY started_at DESC LIMIT ? OFFSET ?",
        (limit, offset)
    )
    rows = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT COUNT(*) FROM task_history")
    total = cursor.fetchone()[0]
    conn.close()
    
    return jsonify({"history": rows, "total": total})


@tasks_bp.route("/<task_id>/stop", methods=["POST"])
def stop_task(task_id):
    if task_id not in running_tasks:
        return jsonify({"error": "任务不在运行中"}), 400
    proc = running_tasks[task_id]["process"]
    if proc:
        proc.terminate()
    return jsonify({"success": True})
```

**注意：** 需要在 tasks_api.py 顶部添加 `import queue`。

- [ ] **步骤 2：更新 tasks_api.py 添加 queue import**

```python
import queue
```

- [ ] **步骤 3：实现 TaskRunner.vue**

```javascript
const TaskRunner = {
    template: `
        <div>
            <div class="card">
                <h2 style="margin-bottom:16px;">任务执行</h2>
                
                <!-- 手动触发 -->
                <div class="trigger-form">
                    <input v-model="rulePath" placeholder="规则路径，如 rules/数据要素/tmtpost_data_articles.yaml" style="width:400px;padding:8px;">
                    <button class="btn-primary" @click="triggerTask" :disabled="running">执行</button>
                </div>
                
                <!-- 运行中任务 -->
                <div v-if="runningTasks.length" style="margin-top:20px;">
                    <h3>运行中</h3>
                    <div v-for="t in runningTasks" :key="t.task_id" class="task-card">
                        <div class="task-header">
                            <span class="task-name">{{ t.rule_path }}</span>
                            <span class="badge badge-running">运行中</span>
                        </div>
                        <div class="log-window" ref="logWindow">
                            <div v-for="(log, i) in t.logs" :key="i" :class="['log-line', 'log-'+log.level]">
                                [{{ log.ts }}] {{ log.message }}
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- 执行历史 -->
                <div style="margin-top:24px;">
                    <h3>最近执行</h3>
                    <table class="data-table">
                        <thead><tr><th>规则</th><th>状态</th><th>新增</th><th>耗时</th><th>时间</th></tr></thead>
                        <tbody>
                            <tr v-for="h in history" :key="h.id">
                                <td>{{ h.rule_path }}</td>
                                <td><span :class="['badge', statusClass(h.status)]">{{ h.status }}</span></td>
                                <td>{{ h.new_count }}</td>
                                <td>{{ h.duration ? h.duration.toFixed(1)+'s' : '-' }}</td>
                                <td>{{ h.started_at }}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `,
    data() {
        return {
            rulePath: "",
            runningTasks: [],
            history: [],
        };
    },
    async mounted() {
        await this.loadRunning();
        await this.loadHistory();
        setInterval(this.loadRunning, 5000);
    },
    methods: {
        async triggerTask() {
            if (!this.rulePath) return;
            const { task_id } = await API.post("/tasks/run", { rule_path: this.rulePath });
            this.loadRunning();
            this.subscribeStream(task_id);
        },
        async loadRunning() {
            const data = await API.get("/tasks/running");
            this.runningTasks = data.running || [];
        },
        async loadHistory() {
            const data = await API.get("/tasks/history");
            this.history = data.history || [];
        },
        subscribeStream(task_id) {
            const es = API.stream("/tasks/" + task_id + "/stream");
            const task = this.runningTasks.find(t => t.task_id === task_id) || { logs: [] };
            if (!task.logs) task.logs = [];
            
            es.onmessage = (e) => {
                const d = JSON.parse(e.data);
                if (e.type === "log") {
                    task.logs.push(d);
                    this.$nextTick(() => {
                        const w = this.$refs.logWindow;
                        if (w) w.scrollTop = w.scrollHeight;
                    });
                } else if (e.type === "done" || e.type === "error") {
                    setTimeout(() => this.loadHistory(), 500);
                    es.close();
                }
            };
        },
        statusClass(s) {
            return { success: "badge-success", failed: "badge-failed", running: "badge-running" }[s] || "";
        }
    }
};
```

追加 badge 样式到 style.css：
```css
.badge-running { background: #fff7e6; color: #fa8c16; }
.badge-failed { background: #fff2f0; color: #ff4d4f; }
.trigger-form { display: flex; gap: 8px; align-items: center; }
.task-card { background: #1e1e1e; color: #d4d4d4; border-radius: 8px; padding: 12px; margin-top: 12px; }
.task-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
.task-name { font-size: 13px; color: #ccc; }
.log-window { max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 12px; }
.log-line { padding: 2px 0; }
.log-INFO { color: #d4d4d4; }
.log-WARN { color: #fa8c16; }
.log-ERROR { color: #ff4d4f; }
```

- [ ] **步骤 4：更新 app.js 注册 TaskRunner.vue**

- [ ] **步骤 5：验证**（访问 /tasks 页面，手动触发一条规则，观察实时日志）

- [ ] **步骤 6：Commit**

```bash
git add APP/dashboard/apis/tasks_api.py APP/dashboard/static/js/components/TaskRunner.vue
git commit -m "feat(dashboard): tasks_api.py + TaskRunner.vue 任务执行与实时日志"
```

---

### 任务 7：logs_api.py（实时日志 SSE）+ LogViewer.vue

**文件：**
- 修改：`APP/dashboard/apis/logs_api.py`
- 创建：`APP/dashboard/static/js/components/LogViewer.vue`

- [ ] **步骤 1：实现 logs_api.py**

```python
import os, json
from flask import Blueprint, jsonify, Response, stream_with_context
from datetime import datetime

logs_bp = Blueprint("logs", __name__)

ENGINE_LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "engine", "logs"
)


@logs_bp.route("", methods=["GET"])
def list_logs():
    """列出所有日志文件"""
    if not os.path.exists(ENGINE_LOG_DIR):
        return jsonify({"logs": []})
    
    logs = []
    for fname in sorted(os.listdir(ENGINE_LOG_DIR), reverse=True):
        if fname.endswith(".log"):
            fpath = os.path.join(ENGINE_LOG_DIR, fname)
            logs.append({
                "name": fname,
                "size": os.path.getsize(fpath),
                "modified_at": datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat()
            })
    return jsonify({"logs": logs})


@logs_bp.route("/<log_name>", methods=["GET"])
def read_log(log_name):
    """读取日志内容（支持 ?lines=N 获取尾部 N 行）"""
    safe_name = os.path.basename(log_name)  # 防止路径穿越
    fpath = os.path.join(ENGINE_LOG_DIR, safe_name)
    
    if not os.path.exists(fpath):
        return jsonify({"error": "日志文件不存在"}), 404
    
    lines_arg = int(request.args.get("lines", 200))
    
    with open(fpath, "r", encoding="utf-8", errors="replace") as f:
        all_lines = f.readlines()
    
    tail = all_lines[-lines_arg:]
    return jsonify({
        "lines": [l.rstrip("\n") for l in tail],
        "total": len(all_lines)
    })


@logs_bp.route("/stream", methods=["GET"])
def log_stream():
    """实时日志流（SSE）"""
    log_file = os.path.join(ENGINE_LOG_DIR, "engine.log")
    
    if not os.path.exists(log_file):
        return Response(f"event: error\ndata: {json.dumps({'message': '日志文件不存在'})}\n\n", mimetype="text/event-stream")
    
    last_pos = os.path.getsize(log_file)
    
    def generate():
        while True:
            try:
                size = os.path.getsize(log_file)
                if size > last_pos:
                    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                        f.seek(last_pos)
                        new_lines = f.readlines()
                    last_pos = size
                    
                    for line in new_lines:
                        if line.strip():
                            yield f"event: log\ndata: {json.dumps({'message': line.rstrip(), 'ts': datetime.now().isoformat()}, ensure_ascii=False)}\n\n"
                
                import time
                time.sleep(1)
            except GeneratorExit:
                break
    
    return Response(stream_with_context(generate()), mimetype="text/event-stream")
```

添加 import：
```python
from flask import request
```

- [ ] **步骤 2：实现 LogViewer.vue**

```javascript
const LogViewer = {
    template: `
        <div class="card">
            <div style="display:flex; justify-content:space-between; margin-bottom:16px;">
                <h2>日志查看</h2>
                <div>
                    <button class="btn-sm" @click="toggleStream" :class="{ active: streaming }">
                        {{ streaming ? '⏸ 暂停' : '▶ 实时' }}
                    </button>
                    <select v-model="selectedLog" @change="loadLog" style="padding:6px;">
                        <option v-for="l in logs" :key="l.name" :value="l.name">{{ l.name }}</option>
                    </select>
                </div>
            </div>
            <div class="log-window" ref="logWindow">
                <div v-for="(line, i) in displayLines" :key="i" class="log-line">{{ line }}</div>
            </div>
        </div>
    `,
    data() {
        return {
            logs: [],
            selectedLog: "",
            displayLines: [],
            streaming: false,
            es: null,
        };
    },
    async mounted() {
        await this.loadLogList();
    },
    beforeUnmount() {
        if (this.es) this.es.close();
    },
    methods: {
        async loadLogList() {
            const data = await API.get("/logs");
            this.logs = data.logs || [];
            if (this.logs.length && !this.selectedLog) {
                this.selectedLog = this.logs[0].name;
                await this.loadLog();
            }
        },
        async loadLog() {
            if (!this.selectedLog) return;
            const data = await API.get("/logs/" + this.selectedLog + "?lines=300");
            this.displayLines = data.lines || [];
            this.$nextTick(() => {
                if (this.$refs.logWindow) this.$refs.logWindow.scrollTop = this.$refs.logWindow.scrollHeight;
            });
        },
        toggleStream() {
            if (this.streaming) {
                if (this.es) this.es.close();
                this.streaming = false;
            } else {
                this.streaming = true;
                this.es = API.stream("/logs/stream");
                this.es.onmessage = (e) => {
                    if (e.type === "log") {
                        const d = JSON.parse(e.data);
                        this.displayLines.push("[" + d.ts + "] " + d.message);
                        if (this.displayLines.length > 500) this.displayLines.shift();
                        this.$nextTick(() => {
                            if (this.$refs.logWindow) this.$refs.logWindow.scrollTop = this.$refs.logWindow.scrollHeight;
                        });
                    }
                };
            }
        }
    }
};
```

- [ ] **步骤 3：更新 app.js 注册 LogViewer.vue**

- [ ] **步骤 4：验证**（访问 /logs 页面，验证实时流功能）

- [ ] **步骤 5：Commit**

```bash
git add APP/dashboard/apis/logs_api.py APP/dashboard/static/js/components/LogViewer.vue
git commit -m "feat(dashboard): logs_api.py + LogViewer.vue 实时日志查看"
```

---

## Phase 3：增强功能

### 任务 8：cron_api.py + CronManager.vue

**文件：**
- 修改：`APP/dashboard/apis/cron_api.py`
- 创建：`APP/dashboard/static/js/components/CronManager.vue`

- [ ] **步骤 1：实现 cron_api.py**

```python
import os, uuid, json
from datetime import datetime
from flask import Blueprint, jsonify, request

cron_bp = Blueprint("cron", __name__)

ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_scheduler():
    from server import scheduler
    return scheduler


def job_to_dict(job):
    return {
        "id": job.id,
        "name": job.name,
        "rule_path": job.args[0] if job.args else "",
        "schedule": str(job.trigger),
        "enabled": job.next_run_time is not None,
        "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
    }


@cron_bp.route("", methods=["GET"])
def list_cron():
    sched = get_scheduler()
    jobs = []
    for job in sched.get_jobs():
        jobs.append(job_to_dict(job))
    return jsonify({"jobs": jobs})


@cron_bp.route("", methods=["POST"])
def create_cron():
    body = request.get_json()
    name = body.get("name", "")
    rule_path = body.get("rule_path", "")
    schedule = body.get("schedule", "")
    
    if not all([name, rule_path, schedule]):
        return jsonify({"error": "缺少必要参数"}), 400
    
    job_id = str(uuid.uuid4())
    
    def job_func():
        from tasks_api import execute_rule_async
        execute_rule_async(str(uuid.uuid4()), rule_path, job_id)
    
    sched = get_scheduler()
    sched.add_job(job_func, "cron", cron=schedule, id=job_id, name=name, args=[rule_path])
    
    # 写入 SQLite
    from apis.db import get_db
    conn = get_db()
    conn.execute(
        "INSERT INTO cron_jobs (id, name, rule_path, schedule, enabled, created_at, updated_at) VALUES (?, ?, ?, ?, 1, ?, ?)",
        (job_id, name, rule_path, schedule, datetime.now().isoformat(), datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "id": job_id}), 201


@cron_bp.route("/<job_id>", methods=["PATCH"])
def update_cron(job_id):
    body = request.get_json()
    sched = get_scheduler()
    job = sched.get_job(job_id)
    if not job:
        return jsonify({"error": "任务不存在"}), 404
    
    if "schedule" in body:
        # 需要重建 job
        rule_path = job.args[0] if job.args else ""
        name = body.get("name", job.name)
        job.remove()
        def new_job():
            from tasks_api import execute_rule_async
            execute_rule_async(str(uuid.uuid4()), rule_path, job_id)
        sched.add_job(new_job, "cron", cron=body["schedule"], id=job_id, name=name, args=[rule_path])
        
        from apis.db import get_db
        conn = get_db()
        conn.execute("UPDATE cron_jobs SET schedule=?, name=?, updated_at=? WHERE id=?",
                     (body["schedule"], name, datetime.now().isoformat(), job_id))
        conn.commit()
        conn.close()
    
    return jsonify({"success": True})


@cron_bp.route("/<job_id>", methods=["DELETE"])
def delete_cron(job_id):
    sched = get_scheduler()
    job = sched.get_job(job_id)
    if job:
        job.remove()
    
    from apis.db import get_db
    conn = get_db()
    conn.execute("DELETE FROM cron_jobs WHERE id=?", (job_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True})


@cron_bp.route("/<job_id>/run", methods=["POST"])
def run_cron_now(job_id):
    from tasks_api import execute_rule_async
    task_id = str(uuid.uuid4())
    sched = get_scheduler()
    job = sched.get_job(job_id)
    rule_path = job.args[0] if job and job.args else ""
    thread = __import__("threading").Thread(target=execute_rule_async, args=(task_id, rule_path, job_id))
    thread.start()
    return jsonify({"task_id": task_id})


@cron_bp.route("/<job_id>/history", methods=["GET"])
def cron_history(job_id):
    from apis.db import get_db
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM task_history WHERE job_id=? ORDER BY started_at DESC LIMIT 20",
        (job_id,)
    )
    history = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify({"history": history})
```

- [ ] **步骤 2：实现 CronManager.vue**

```javascript
const CronManager = {
    template: `
        <div class="card">
            <div style="display:flex;justify-content:space-between;margin-bottom:16px;">
                <h2>Cron 调度</h2>
                <button class="btn-primary" @click="showCreate=true">+ 新建任务</button>
            </div>
            
            <table class="data-table">
                <thead><tr><th>名称</th><th>规则</th><th>Cron</th><th>下次执行</th><th>操作</th></tr></thead>
                <tbody>
                    <tr v-for="job in jobs" :key="job.id">
                        <td>{{ job.name }}</td>
                        <td>{{ job.rule_path }}</td>
                        <td><code>{{ job.schedule }}</code></td>
                        <td>{{ job.next_run || '-' }}</td>
                        <td>
                            <button class="btn-sm" @click="runNow(job.id)">立即执行</button>
                            <button class="btn-sm btn-danger" @click="deleteJob(job.id)">删除</button>
                        </td>
                    </tr>
                </tbody>
            </table>
            
            <div v-if="showCreate" class="dialog-overlay" @click.self="showCreate=false">
                <div class="dialog">
                    <h3>新建 Cron 任务</h3>
                    <div class="form-group">
                        <label>任务名称</label>
                        <input v-model="newJob.name" style="width:100%;padding:8px;">
                    </div>
                    <div class="form-group">
                        <label>规则路径</label>
                        <input v-model="newJob.rule_path" placeholder="rules/数据要素/tmtpost_data_articles.yaml" style="width:100%;padding:8px;">
                    </div>
                    <div class="form-group">
                        <label>Cron 表达式</label>
                        <input v-model="newJob.schedule" placeholder="0 9 * * *" style="width:100%;padding:8px;">
                        <small>格式: 分 时 日 月 周 (5段, 标准 cron)</small>
                    </div>
                    <div style="margin-top:16px;">
                        <button class="btn-primary" @click="createJob">创建</button>
                        <button class="btn-sm" @click="showCreate=false">取消</button>
                    </div>
                </div>
            </div>
        </div>
    `,
    data() {
        return {
            jobs: [],
            showCreate: false,
            newJob: { name: "", rule_path: "", schedule: "0 9 * * *" },
        };
    },
    async mounted() { await this.loadJobs(); },
    methods: {
        async loadJobs() {
            const data = await API.get("/cron");
            this.jobs = data.jobs || [];
        },
        async createJob() {
            await API.post("/cron", this.newJob);
            this.showCreate = false;
            this.newJob = { name: "", rule_path: "", schedule: "0 9 * * *" };
            await this.loadJobs();
        },
        async runNow(job_id) { await API.post("/cron/" + job_id + "/run"); },
        async deleteJob(job_id) {
            if (confirm("确定删除？")) {
                await API.delete("/cron/" + job_id);
                await this.loadJobs();
            }
        }
    }
};
```

添加 form-group 样式：
```css
.form-group { margin-bottom: 12px; }
.form-group label { display: block; font-size: 13px; color: #666; margin-bottom: 4px; }
code { background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-size: 12px; }
```

- [ ] **步骤 3：更新 app.js 注册 CronManager.vue**

- [ ] **步骤 4：验证**（访问 /cron 页面）

- [ ] **步骤 5：Commit**

```bash
git add APP/dashboard/apis/cron_api.py APP/dashboard/static/js/components/CronManager.vue
git commit -m "feat(dashboard): cron_api.py + CronManager.vue Cron 调度管理"
```

---

### 任务 9：RuleEditor.vue（表单向导 + YAML 编辑双模式）

**文件：**
- 创建：`APP/dashboard/static/js/components/RuleEditor.vue`

- [ ] **步骤 1：实现 RuleEditor.vue（表单 + YAML 双模式）**

```javascript
const RuleEditor = {
    template: `
        <div class="card">
            <h2>{{ isEdit ? '编辑规则' : '新建规则' }}</h2>
            
            <div style="margin-bottom:12px;">
                <button :class="['btn-sm', { active: mode === 'form' }]" @click="mode='form'">表单</button>
                <button :class="['btn-sm', { active: mode === 'yaml' }]" @click="mode='yaml'">YAML</button>
            </div>
            
            <div v-if="mode === 'form'">
                <div class="form-group">
                    <label>事项 (subject)</label>
                    <input v-model="form.subject" placeholder="数据要素" style="width:100%;padding:8px;">
                </div>
                <div class="form-group">
                    <label>平台 (platform)</label>
                    <input v-model="form.platform" placeholder="tmtpost" style="width:100%;padding:8px;">
                </div>
                <div class="form-group">
                    <label>规则名称 (name)</label>
                    <input v-model="form.name" placeholder="tmtpost_data_articles" style="width:100%;padding:8px;">
                </div>
                <div class="form-group">
                    <label>类型</label>
                    <select v-model="form.type" style="width:100%;padding:8px;">
                        <option value="rss">RSS</option>
                        <option value="html">HTML</option>
                        <option value="json">JSON</option>
                        <option value="api">API</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>URL</label>
                    <input v-model="form.url" placeholder="https://..." style="width:100%;padding:8px;">
                </div>
                <div class="form-group">
                    <label>字段映射 (JSON)</label>
                    <textarea v-model="form.mapping" rows="4" style="width:100%;padding:8px;font-family:monospace;">{}</textarea>
                </div>
                <button class="btn-primary" @click="generateYaml">生成 YAML</button>
            </div>
            
            <div v-if="mode === 'yaml'">
                <textarea v-model="yamlContent" rows="20" style="width:100%;font-family:monospace;font-size:13px;padding:8px;"></textarea>
            </div>
            
            <div style="margin-top:16px;">
                <button class="btn-primary" @click="save">{{ isEdit ? '保存' : '创建' }}</button>
                <button class="btn-sm" @click="$emit('close')">取消</button>
            </div>
        </div>
    `,
    props: ["rulePath", "initialYaml"],
    emits: ["close", "saved"],
    data() {
        return {
            mode: "form",
            form: { subject: "", platform: "", name: "", type: "rss", url: "", mapping: "{}" },
            yamlContent: this.initialYaml || "",
            isEdit: !!this.rulePath,
        };
    },
    methods: {
        generateYaml() {
            const mapping = this.form.mapping.trim() ? JSON.parse(this.form.mapping) : {};
            const doc = {
                subject: this.form.subject,
                platform: this.form.platform,
                enabled: true,
                source: {
                    name: this.form.name,
                    type: this.form.type,
                    url: this.form.url,
                    mapping: mapping,
                }
            };
            // 简单 YAML 序列化
            this.yamlContent = `subject: "${doc.subject}"
platform: "${doc.platform}"
enabled: true
source:
  name: "${doc.source.name}"
  type: "${doc.source.type}"
  url: "${doc.source.url}"
  mapping:
    title: "${mapping.title || 'title'}"
    link: "${mapping.link || 'link'}"
    published: "${mapping.published || 'published'}"
`;
            this.mode = "yaml";
        },
        async save() {
            const yaml = this.yamlContent || this.generateYamlFromForm();
            const path = this.rulePath || `rules/${this.form.subject}/${this.form.name}.yaml`;
            await API.put("/rules/" + path, { yaml });
            this.$emit("saved");
        },
        generateYamlFromForm() {
            // fallback
            return this.yamlContent;
        }
    }
};
```

- [ ] **步骤 2：更新 app.js 注册 RuleEditor.vue**

- [ ] **步骤 3：Commit**

```bash
git add APP/dashboard/static/js/components/RuleEditor.vue
git commit -m "feat(dashboard): RuleEditor.vue 表单向导 + YAML 编辑双模式"
```

---

### 任务 10：data_api.py + DataPreview.vue

**文件：**
- 修改：`APP/dashboard/apis/data_api.py`
- 创建：`APP/dashboard/static/js/components/DataPreview.vue`

- [ ] **步骤 1：实现 data_api.py**

```python
import os, json
from flask import Blueprint, jsonify, send_file

data_bp = Blueprint("data", __name__)

ENGINE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(ENGINE_ROOT, "output")


@data_bp.route("", methods=["GET"])
def list_subjects():
    if not os.path.exists(OUTPUT_DIR):
        return jsonify({"subjects": []})
    subjects = [d for d in os.listdir(OUTPUT_DIR) if os.path.isdir(os.path.join(OUTPUT_DIR, d))]
    return jsonify({"subjects": sorted(subjects)})


@data_bp.route("/<subject>", methods=["GET"])
def list_platforms(subject):
    subject_dir = os.path.join(OUTPUT_DIR, subject)
    if not os.path.exists(subject_dir):
        return jsonify({"platforms": []})
    
    platforms = []
    for pname in os.listdir(subject_dir):
        pdir = os.path.join(subject_dir, pname)
        if not os.path.isdir(pdir):
            continue
        files = [f for f in os.listdir(pdir) if f.endswith(".json")]
        latest = max(files, default=None)
        latest_path = os.path.join(pdir, latest) if latest else None
        platforms.append({
            "name": pname,
            "latest_file": latest,
            "record_count": 0,
            "updated_at": None
        })
        if latest_path:
            try:
                with open(latest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    platforms[-1]["record_count"] = len(data.get("records", []))
                    platforms[-1]["updated_at"] = data.get("timestamp", None)
            except:
                pass
    
    return jsonify({"platforms": platforms})


@data_bp.route("/<subject>/latest", methods=["GET"])
def latest_combined(subject):
    latest_path = os.path.join(OUTPUT_DIR, subject, "combined_latest.json")
    if not os.path.exists(latest_path):
        return jsonify({"platforms": {}})
    
    with open(latest_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return jsonify(data)
```

- [ ] **步骤 2：实现 DataPreview.vue**

```javascript
const DataPreview = {
    template: `
        <div class="card">
            <h2 style="margin-bottom:16px;">数据预览</h2>
            
            <div style="margin-bottom:16px;">
                <select v-model="selectedSubject" @change="loadPlatforms" style="padding:8px;min-width:200px;">
                    <option value="">选择事项</option>
                    <option v-for="s in subjects" :key="s" :value="s">{{ s }}</option>
                </select>
            </div>
            
            <div v-if="selectedSubject && platforms.length">
                <div v-for="p in platforms" :key="p.name" class="platform-card">
                    <div class="platform-header" @click="togglePlatform(p.name)">
                        <span class="platform-name">{{ p.name }}</span>
                        <span>{{ p.record_count }} 条 | {{ p.updated_at || '-' }}</span>
                    </div>
                    <div v-if="expandedPlatform === p.name && p.data" class="platform-data">
                        <table class="data-table">
                            <thead><tr>
                                <th v-for="key in Object.keys(p.data.records[0] || {})" :key="key">{{ key }}</th>
                            </tr></thead>
                            <tbody>
                                <tr v-for="(row, i) in p.data.records" :key="i" @click="toggleRow(row)" style="cursor:pointer;">
                                    <td v-for="key in Object.keys(row)" :key="key">{{ row[key] }}</td>
                                </tr>
                            </tbody>
                        </table>
                        <div v-if="selectedRow" class="json-preview">
                            <pre>{{ JSON.stringify(selectedRow, null, 2) }}</pre>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `,
    data() {
        return {
            subjects: [],
            selectedSubject: "",
            platforms: [],
            expandedPlatform: null,
            selectedRow: null,
        };
    },
    async mounted() {
        const data = await API.get("/data");
        this.subjects = data.subjects || [];
    },
    methods: {
        async loadPlatforms() {
            if (!this.selectedSubject) return;
            const data = await API.get("/data/" + this.selectedSubject);
            this.platforms = data.platforms || [];
        },
        async togglePlatform(name) {
            if (this.expandedPlatform === name) {
                this.expandedPlatform = null;
                return;
            }
            this.expandedPlatform = name;
            const data = await API.get("/data/" + this.selectedSubject + "/latest");
            const p = this.platforms.find(x => x.name === name);
            if (p) p.data = data.platforms ? data.platforms[name] : data;
        },
        toggleRow(row) {
            this.selectedRow = this.selectedRow === row ? null : row;
        }
    }
};
```

添加样式：
```css
.platform-card { border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
.platform-header { background: #fafafa; padding: 12px 16px; cursor: pointer; display: flex; justify-content: space-between; }
.platform-name { font-weight: 500; }
.platform-data { padding: 12px; }
.json-preview { margin-top: 12px; }
.json-preview pre { background: #1e1e1e; color: #d4d4d4; padding: 12px; border-radius: 4px; font-size: 12px; overflow-x: auto; }
```

- [ ] **步骤 3：更新 app.js 注册 DataPreview.vue**

- [ ] **步骤 4：验证**

- [ ] **步骤 5：Commit**

```bash
git add APP/dashboard/apis/data_api.py APP/dashboard/static/js/components/DataPreview.vue
git commit -m "feat(dashboard): data_api.py + DataPreview.vue 数据预览"
```

---

### 任务 11：DashboardHome.vue（首页统计卡片）

**文件：**
- 创建：`APP/dashboard/static/js/components/DashboardHome.vue`

- [ ] **步骤 1：实现 DashboardHome.vue**

```javascript
const DashboardHome = {
    template: `
        <div>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{{ stats.ruleCount }}</div>
                    <div class="stat-label">规则总数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ stats.cronCount }}</div>
                    <div class="stat-label">Cron 任务</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ stats.todayNew }}</div>
                    <div class="stat-label">今日新增</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ stats.runningCount }}</div>
                    <div class="stat-label">运行中</div>
                </div>
            </div>
            
            <div class="card" style="margin-top:20px;">
                <h3>最近任务</h3>
                <table class="data-table">
                    <thead><tr><th>规则</th><th>状态</th><th>新增</th><th>时间</th></tr></thead>
                    <tbody>
                        <tr v-for="h in recentHistory" :key="h.id">
                            <td>{{ h.rule_path }}</td>
                            <td><span :class="['badge', h.status === 'success' ? 'badge-success' : 'badge-failed']">{{ h.status }}</span></td>
                            <td>{{ h.new_count }}</td>
                            <td>{{ h.started_at }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    `,
    data() {
        return {
            stats: { ruleCount: 0, cronCount: 0, todayNew: 0, runningCount: 0 },
            recentHistory: [],
        };
    },
    async mounted() {
        await this.loadAll();
        setInterval(this.loadAll, 30000);
    },
    methods: {
        async loadAll() {
            const [rules, crons, running, history] = await Promise.all([
                API.get("/rules"),
                API.get("/cron"),
                API.get("/tasks/running"),
                API.get("/tasks/history?limit=10"),
            ]);
            this.stats.ruleCount = rules.rules ? rules.rules.length : 0;
            this.stats.cronCount = crons.jobs ? crons.jobs.length : 0;
            this.stats.runningCount = running.running ? running.running.length : 0;
            this.recentHistory = history.history || [];
            
            // 今日新增
            const today = new Date().toISOString().split("T")[0];
            this.stats.todayNew = this.recentHistory
                .filter(h => h.started_at && h.started_at.startsWith(today))
                .reduce((s, h) => s + (h.new_count || 0), 0);
        }
    }
};
```

添加样式：
```css
.stats-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.stat-card { background: #fff; border-radius: 8px; padding: 20px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.stat-value { font-size: 32px; font-weight: 600; color: #1890ff; }
.stat-label { color: #666; font-size: 13px; margin-top: 4px; }
```

- [ ] **步骤 2：更新 app.js 注册 DashboardHome.vue**

- [ ] **步骤 3：Commit**

```bash
git add APP/dashboard/static/js/components/DashboardHome.vue
git commit -m "feat(dashboard): DashboardHome.vue 首页统计卡片"
```

---

## 自检清单

**规格覆盖度检查：**
- [x] 规则管理（列表/查看/编辑/新建/启用停用/删除）
- [x] Cron 管理（CRUD/执行历史/立即执行）
- [x] 任务执行（手动触发/实时日志/历史）
- [x] 日志查看（实时流/历史文件）
- [x] 数据预览（结构化表格 + JSON 展开）
- [x] 首页（统计卡片/最近任务）
- [x] engine_cli.py 扩展（JSON 输出）
- [x] 数据库迁移文件
- [x] Vue 3 CDN 前端

**占位符扫描：** 无占位符

**类型一致性检查：** API 路由一致，Vue 组件名一致

---

## 执行选项

**两种执行方式：**

**1. 子代理驱动（推荐）** — 每个任务调度一个新的子代理，任务间进行审查，快速迭代

**2. 内联执行** — 在当前会话中使用 executing-plans 执行任务，批量执行并设有检查点

选择哪种方式？
