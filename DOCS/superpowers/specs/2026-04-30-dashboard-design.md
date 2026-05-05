# info-collector 看板设计文档

> **状态：** 待用户审批
> **创建日期：** 2026-04-30

---

## 1. 系统定位与目标

**定位：** info-collector 的图形化管理界面，面向本地用户。

**目标：** 替代 CLI 操作，提供规则管理、Cron 调度、任务执行、日志查看、数据预览五大功能，部署方式为本地启动（`python server.py`）。

**不做什么：**
- 不是数据可视化平台（那是模块三的事）
- 不做数据统计分析
- 不做用户权限管理（本地单用户）

---

## 2. 整体架构

```
┌─────────────────────────────────────────┐
│  浏览器  (Vue 3 CDN, 纯前端)            │
│  localhost:5000                         │
└──────────────┬──────────────────────────┘
               │ HTTP JSON / SSE
┌──────────────▼──────────────────────────┐
│  Flask server (APP/dashboard/server.py) │
│  port 5000, debug=True, reloader=True   │
│  APScheduler (内置调度)                  │
│                                          │
│  apis/                                   │
│    rules_api.py   ← 规则 CRUD           │
│    cron_api.py    ← Cron 任务管理       │
│    tasks_api.py   ← 手动触发 + 状态      │
│    logs_api.py    ← 日志读取 + SSE      │
│    data_api.py    ← 数据预览            │
│                                          │
│  dashboard.db (SQLite)                   │
│    - cron_jobs 表                       │
│    - task_history 表                    │
└──────────────────┬──────────────────────┘
                   │ subprocess (CLI JSON)
        ┌──────────▼──────────┐
        │  engine_cli.py       │
        │  JSON stdout/stderr  │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │  采集引擎执行         │
        │  YAML 规则读写        │
        │  日志写入 engine/logs │
        └─────────────────────┘
```

---

## 3. 文件结构

```
APP/dashboard/
  server.py              ← Flask 入口 + APScheduler 初始化
  requirements.txt       ← flask, flask-cors, apscheduler
  dashboard.db           ← SQLite 数据库
  dashboard.log          ← dashboard 自身日志
  
  apis/
    __init__.py          ← 蓝图注册
    rules_api.py         ← 规则 CRUD API
    cron_api.py          ← Cron 任务 API
    tasks_api.py         ← 任务执行 API（含 SSE）
    logs_api.py         ← 日志 API（含 SSE）
    data_api.py         ← 数据预览 API
  
  migrations/
    001_init.sql         ← 初始 schema（cron_jobs + task_history）
  
  static/
    index.html           ← Vue 3 单页应用入口
    css/
      style.css          ← 全局样式
    js/
      app.js             ← Vue 主应用 + 路由
      api.js             ← HTTP 客户端封装
      components/
        DashboardHome.vue     ← 首页
        RuleList.vue          ← 规则列表
        RuleEditor.vue        ← 规则编辑器（表单 + YAML 双模式）
        CronManager.vue       ← Cron 管理
        TaskRunner.vue        ← 任务执行（实时日志）
        LogViewer.vue         ← 日志查看（实时流）
        DataPreview.vue       ← 数据预览（表格 + JSON）
```

**与 engine 的边界：**
- dashboard server.py 通过 `subprocess.run(['python', '-m', 'engine.cli', ...], capture_output=True, text=True)` 调用 engine
- 所有 engine → dashboard 的数据通过 CLI stdout JSON 传递
- engine 不知道 dashboard 的存在，完全解耦

---

## 4. API 设计

### 4.1 规则管理

```
GET    /api/rules
  → 200: { "rules": [{ subject, platform, name, path, enabled, last_run, last_status }] }

GET    /api/rules/<subject>/<platform>/<name>.yaml
  → 200: { "yaml": "...", "path": "..." }
  → 404: { "error": "规则不存在" }

PUT    /api/rules/<subject>/<platform>/<name>.yaml
  Body: { "yaml": "..." }
  → 200: { "success": true }
  → 400: { "error": "YAML 格式错误" }

DELETE /api/rules/<subject>/<platform>/<name>.yaml
  → 200: { "success": true }
  → 404: { "error": "规则不存在" }

PATCH  /api/rules/<subject>/<platform>/<name>.yaml/enable
  Body: { "enabled": true/false }
  → 200: { "success": true }
  注：enabled 字段存储在 YAML 顶层 source.enabled

POST   /api/rules
  Body: { "subject", "platform", "name", "yaml" }
  → 201: { "success": true, "path": "..." }
  → 400: { "error": "参数错误" }
```

**engine_cli.py 需要扩展的命令：**
```
python -m engine.cli list-rules --format=json
  → JSON: { rules: [{ subject, platform, name, path, enabled }] }

python -m engine.cli get-rule <path.yaml> --format=json
  → JSON: { yaml: "...", path: "..." }

python -m engine.cli put-rule <path.yaml> [--yaml-content "..."]
  → 读取 stdin 或 --yaml-content 参数

python -m engine.cli delete-rule <path.yaml>
  → { success: true }

python -m engine.cli enable-rule <path.yaml> [--enable=true|false]
  → 修改 YAML 中 source.enabled 字段
```

### 4.2 Cron 管理

```
GET    /api/cron
  → 200: { "jobs": [{ id, name, rule_path, schedule, enabled, next_run, last_run, last_status }] }

POST   /api/cron
  Body: { "name", "rule_path", "schedule" }
  schedule 格式: "0 9 * * *"（标准 cron 表达式，5段）
  → 201: { "success": true, "id": "uuid" }
  → 400: { "error": "cron 表达式格式错误" }

PATCH  /api/cron/<job_id>
  Body: { "schedule"?, "enabled"?, "name"? }
  → 200: { "success": true }

DELETE /api/cron/<job_id>
  → 200: { "success": true }
  → 404: { "error": "任务不存在" }

POST   /api/cron/<job_id>/run
  → 200: { "task_id": "uuid" }

GET    /api/cron/<job_id>/history
  → 200: { "history": [{ id, started_at, ended_at, status, new_count, error_msg, duration }] }
  参数: ?limit=20&offset=0
```

### 4.3 任务执行

```
GET    /api/tasks/running
  → 200: { "running": [{ task_id, rule_path, job_id, started_at }] }

POST   /api/tasks/run
  Body: { "rule_path": "rules/数据要素/tmtpost_data_articles.yaml" }
  → 201: { "task_id": "uuid" }

GET    /api/tasks/<task_id>/stream
  → Content-Type: text/event-stream (SSE)
  事件:
    event: log
    data: {"level": "INFO", "message": "开始采集...", "ts": "ISO8601"}
    event: log
    data: {"level": "INFO", "message": "采集完成，新增 1 条", "ts": "ISO8601"}
    event: done
    data: {"status": "success", "new_count": 1, "duration": 3.2, "error_msg": null}
    event: error
    data: {"message": "任务执行失败"}

GET    /api/tasks/history
  → 200: { "history": [...], "total": N }
  参数: ?limit=50&offset=0&rule_path=&status=

POST   /api/tasks/<task_id>/stop
  → 200: { "success": true }
  → 400: { "error": "任务不在运行中" }
```

### 4.4 日志查看

```
GET    /api/logs
  → 200: { "logs": [{ name, size, modified_at }] }
  说明: 列出 engine/logs/ 下的所有 .log 文件

GET    /api/logs/<log_name>
  → 200: text/plain（日志内容）
  → 404: { "error": "日志文件不存在" }

GET    /api/logs/stream
  → Content-Type: text/event-stream (SSE)
  说明: tail -f engine.log 的实时流
  event: log
  data: {"message": "行内容", "ts": "ISO8601"}
```

### 4.5 数据预览

```
GET    /api/data
  → 200: { "subjects": ["数据要素", ...] }

GET    /api/data/<subject>
  → 200: { "platforms": [{ name, latest_file, record_count, updated_at }] }

GET    /api/data/<subject>/latest
  → 200: { "platforms": { "tmtpost": { "records": [...], "count": N }, ... } }
  说明: 读取 output/<subject>/combined_latest.json

GET    /api/data/<subject>/<platform>/<date>.json
  → 200: { "records": [...], "source": "...", "platform": "...", "count": N }
```

---

## 5. 数据库设计

### 5.1 Schema

```sql
-- Cron 任务表
CREATE TABLE cron_jobs (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    rule_path   TEXT NOT NULL,
    schedule    TEXT NOT NULL,
    enabled     INTEGER DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

-- 任务执行历史表
CREATE TABLE task_history (
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

CREATE INDEX idx_task_history_job_id ON task_history(job_id);
CREATE INDEX idx_task_history_started_at ON task_history(started_at);
```

### 5.2 迁移文件

`migrations/001_init.sql` — 初始 schema

```sql
-- 初始版本：cron_jobs + task_history
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

未来迁移：`migrations/002_xxx.sql`，按序号递增。

**迁移执行：** server.py 启动时检查 `migrations/` 目录，按序号依次执行未执行过的 SQL 文件。

---

## 6. 前端页面结构

### 6.1 导航

顶部 Tab 导航，6 个模块：

```
┌──────────────────────────────────────────────────────────────────┐
│  📊 首页  |  规则管理  |  Cron调度  |  任务执行  |  日志查看  |  数据预览  │
└──────────────────────────────────────────────────────────────────┘
```

### 6.2 各模块功能

| 模块 | 路由 | 功能 |
|------|------|------|
| 首页 | `/` | 统计卡片 + 最近任务 + 快速操作 |
| 规则管理 | `/rules` | 列表/查看/编辑/新建/启用停用/删除 |
| Cron调度 | `/cron` | Cron 任务 CRUD + 执行历史 |
| 任务执行 | `/tasks` | 实时任务卡 + 手动触发 + 历史 |
| 日志查看 | `/logs` | 实时日志窗口（tail -f 风格）+ 历史切换 |
| 数据预览 | `/data` | subject → 平台 → combined_latest 结构化展示 + JSON 展开 |

### 6.3 组件说明

| 组件 | 功能 |
|------|------|
| `RuleList.vue` | 规则列表，按 subject 分组，支持搜索、启用/停用 toggle |
| `RuleEditor.vue` | 双模式：表单项（字段生成 YAML）+ YAML 编辑器（代码高亮） |
| `CronManager.vue` | Cron 任务列表 + cron 表达式图形选择器 |
| `TaskRunner.vue` | 实时任务卡片（滚动日志）+ 手动触发表单 |
| `LogViewer.vue` | 实时日志窗口，滚动输出，暂停/恢复 |
| `DataPreview.vue` | 结构化表格 + 行展开原始 JSON |
| `DashboardHome.vue` | 统计卡片 + 最近任务 + 健康状态 |

### 6.4 实时更新机制

- 任务执行和日志查看使用 SSE（Server-Sent Events）
- Vue 组件通过 `EventSource` 订阅 `/api/tasks/<task_id>/stream` 和 `/api/logs/stream`
- 首页和列表页每 30 秒轮询一次

---

## 7. 日志策略

| 日志 | 位置 | 内容 |
|------|------|------|
| dashboard 自身日志 | `APP/dashboard/dashboard.log` | 启动记录、API 错误、APScheduler 触发 |
| engine 执行日志 | `APP/engine/logs/*.log` | 采集执行过程（已有） |
| dashboard access log | 不记录 | 简化 |

日志格式：`[%(asctime)s] %(levelname)s [%(name)s] %(message)s`

---

## 8. 开发模块顺序

按优先级分 3 个阶段：

### Phase 1：基础设施（P0）
1. `server.py` 骨架 + 启动脚本
2. `migrations/001_init.sql` + 数据库初始化
3. `apis/__init__.py` 蓝图注册
4. `static/index.html` + Vue 3 引入 + 顶部 Tab 导航骨架
5. `api.js` HTTP 客户端封装

### Phase 2：核心功能（P1）
6. `rules_api.py` + `RuleList.vue`
7. `engine_cli.py` 扩展（list-rules, get-rule, put-rule, enable-rule JSON 输出）
8. `tasks_api.py`（手动触发 + SSE）+ `TaskRunner.vue`
9. `logs_api.py`（SSE 实时流）+ `LogViewer.vue`

### Phase 3：增强功能（P2）
10. `cron_api.py` + `CronManager.vue`
11. `RuleEditor.vue`（表单向导 + YAML 编辑双模式）
12. `DataPreview.vue` + `data_api.py`
13. `DashboardHome.vue`（首页统计卡片）

---

## 9. 关键技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 前端框架 | Vue 3 CDN | 无需构建，组件化好 |
| 后端框架 | Flask | 轻量，足够满足需求 |
| 数据库 | SQLite | 本地单用户足够 |
| 调度器 | APScheduler | Flask 生态好，无需额外服务 |
| 实时通信 | Server-Sent Events | 简单，单向实时推送够用 |
| YAML 编辑器 | 原生 textarea 或轻量库 | 避免引入过重依赖 |
| 端口 | 5000 | Flask 默认 |
| 启动模式 | debug=True + reloader | 开发友好 |

---

## 10. engine_cli.py 扩展清单

为支持 dashboard，需要在 `engine_cli.py` 中新增的命令（均以 JSON 输出）：

```bash
# 规则列表
python -m engine.cli list-rules --format=json
  输出: {"rules": [{ "subject", "platform", "name", "path", "enabled", "last_run", "last_status" }]}

# 读取规则 YAML
python -m engine.cli get-rule <path.yaml> --format=json
  输出: {"yaml": "...", "path": "..."}

# 写入规则 YAML
python -m engine.cli put-rule <path.yaml> --yaml-content "..."
  输出: {"success": true}

# 删除规则
python -m engine.cli delete-rule <path.yaml>
  输出: {"success": true}

# 启用/停用规则
python -m engine.cli enable-rule <path.yaml> --enable=true|false
  输出: {"success": true, "enabled": true}

# 手动执行规则（JSON 输出，不输出实时日志）
python -m engine.cli run-rule <path.yaml> --format=json
  输出: {"success": true, "new_count": 1, "duration": 3.2}

# 列出日志文件
python -m engine.cli list-logs --format=json
  输出: {"logs": [{ "name", "size", "modified_at" }]}

# 读取日志内容
python -m engine.cli read-log <log_name> [--lines=100] --format=json
  输出: {"lines": [...], "total": N}
```

---

> **请审查此设计文档。如有修改意见请告知，批准后我将调用 writing-plans 技能创建实现计划。**
