# info-collector 看板需求文档 v0.1

> 用于收集你对看板系统的需求反馈。
> 回复时注明 [A/B/C/D] 选择，或直接写意见。

---

## 1. 系统定位

**看板定位**：info-collector 的图形化管理界面，替代 CLI 操作。

**不做什么**：不是数据可视化平台（那是模块三的事），核心是运维控制台。

---

## 2. 功能模块规划

### 模块 1：规则管理（RM - Rule Manager）

**功能清单：**
- 规则列表：按 subject 分组，显示平台、名称、enabled 状态、触发方式、上次运行时间
- 查看规则：只读查看 YAML 内容
- 编辑规则：完整 YAML 在线编辑（代码编辑器风格，支持语法高亮）
- 新建规则：两种方式
  - 表单向导（填字段，生成 YAML）
  - YAML 模板（空白模板 + 典型示例）
- 启用/停用：一键 toggle，无需删除 YAML
- 删除规则：二次确认
- 导入/导出：单个或批量导出 YAML 包

**enabled 字段设计：**
```yaml
# 在 source 同级加一个顶层字段（不是 source.enable）
subject: "数据要素"
platform: "tmtpost"
enabled: true          # ← 新增，默认 true
source:
  name: "tmtpost_data_articles"
  type: "rss"
  # ...
```

**API 设计：**
```
GET    /api/rules                     → 规则列表（元数据，不含 content）
GET    /api/rules/<path>.yaml         → 单个规则完整 YAML
PUT    /api/rules/<path>.yaml         → 完整替换 YAML
DELETE /api/rules/<path>.yaml         → 删除规则
PATCH  /api/rules/<path>.yaml/enable  → { enabled: true/false }
POST   /api/rules                     → 新建规则（body: { path, yaml_content }）
POST   /api/rules/import              → 批量导入（form-data: zip of YAMLs）
GET    /api/rules/export              → 打包下载所有规则
```

---

### 模块 2：Cron 调度管理（CM - Cron Manager）

**功能清单：**
- Cron 任务列表：显示规则名称、cron 表达式、启用状态、下次执行时间、最近状态
- 创建 Cron 任务：选择规则 + 填写 cron 表达式（或图形化选择：每天/每周等）
- 启用/停用：toggle
- 编辑 cron 表达式
- 删除 Cron 任务
- 执行日志：最近 N 次执行的开始/结束时间、成功/失败

**与 Hermes cronjob 的关系：**
- Cron 任务以 YAML 配置存在 `~/.hermes/cron/`（现有 Hermes 机制）
- 看板提供图形化界面来读写这些 cron 配置
- 不改变 Hermes 自身的 cron 执行逻辑

**API 设计：**
```
GET    /api/cron                      → Cron 任务列表
POST   /api/cron                      → 创建 Cron（body: { rule_path, schedule, name }）
PATCH  /api/cron/<job_id>             → 更新 cron 表达式或 enabled
DELETE /api/cron/<job_id>             → 删除
POST   /�/cron/<job_id>/run           → 立即触发一次（不改变下次执行时间）
GET    /api/cron/<job_id>/history     → 执行历史
```

---

### 模块 3：任务执行与状态（TS - Task Status）

**功能清单：**
- 实时状态：当前正在执行的任务（如果有）
- 执行历史：规则名、执行时间、耗时、成功/失败、去重新增数、错误信息
- 单条规则手动执行（调试用）：点击即运行，实时输出日志流
- 去重统计：显示本次新增数 vs 历史库总数

**API 设计：**
```
GET    /api/tasks/running             → 当前正在执行的任务
GET    /api/tasks/history             → 执行历史（分页，支持按规则/时间过滤）
POST   /api/tasks/run/<rule_path>     → 手动触发规则执行
GET    /api/tasks/run/<rule_path>/log → 实时日志流（Server-Sent Events）
```

---

### 模块 4：日志查看（LM - Log Manager）

**功能清单：**
- 实时日志：当前执行任务的实时输出
- 历史日志：按任务/时间查找
- 日志级别过滤：INFO/WARN/ERROR
- 日志下载：导出为 .log 文件

**日志存储位置：**
- 现有 `APP/engine/logs/` + Hermes cron 输出
- 考虑统一写到 `logs/` 子目录

**API 设计：**
```
GET    /api/logs                      → 日志列表（分页，按时间/级别过滤）
GET    /api/logs/<log_id>             → 单个日志内容
GET    /api/logs/stream               → 实时日志流（SSE）
```

---

### 模块 5：数据预览（DP - Data Preview）

**功能清单：**
- 按 subject 查看最新采集数据
- 按规则/平台过滤
- 直接在看板内预览原始 JSON 数据
- 显示字段映射结果

**API 设计：**
```
GET    /api/data/<subject>/latest     → 各平台最新合并数据
GET    /api/data/<subject>/<platform>/<date>.json  → 单个文件
```

---

### 模块 6：仪表盘首页（Dashboard Home）

**功能清单：**
- 统计概览卡片：规则总数、正在运行、今日新增数据条数、错误数
- 最近任务执行列表（最近 10 条）
- 最近错误列表
- Cron 健康状态（哪些任务很久没跑了）
- 快速操作：立即执行规则、跳转各模块

---

## 3. 技术架构

### 后端：Flask API Server

```
APP/dashboard/
  server.py           # Flask 主服务
  requirements.txt    # flask, flask-cors, apscheduler
  rules_api.py        # 规则管理 API
  cron_api.py         # Cron 管理 API
  tasks_api.py        # 任务执行 API
  logs_api.py         # 日志 API
  data_api.py         # 数据预览 API
  static/
    index.html
    css/
      style.css
    js/
      app.js           # 主应用逻辑
      components/      # 可选：各模块的 JS
```

**为什么不 FastAPI？** Flask 更轻量，这个场景不需要 FastAPI 的自动 OpenAPI 文档等特性。

**复用 engine_cli.py 逻辑？** server.py 直接 import engine 的 Python 模块（state.py, output.py），不通过 CLI subprocess。

---

### 前端：Vue 3（CDN）

**选型理由：**
- 规则编辑、模块切换、多组件协同 → 需要状态管理和组件化
- CDN 引入（`https://unpkg.com/vue@3/dist/vue.global.prod.js`）→ 无需构建工具
- 比 React 轻量，比 Vanilla JS 可维护性好

**单文件 HTML 还是多文件？**
- 方案 A：单 `index.html` + 内联 CSS/JS（简单，但大后难维护）
- 方案 B：`static/index.html` + `static/css/style.css` + `static/js/app.js`（推荐，清晰）
- 方案 C：Vue 单文件组件（.vue）→ 需要 Vite 构建（违背轻量原则）

---

### 数据存储

**SQLite（现有）继续用：**
- 规则元数据（`~/.hermes/info-collector/state.db` 或新库）
- Cron 任务配置（`~/.hermes/cron/` YAML）
- 执行历史 → 写到 SQLite 或 JSON 文件

**不需要 PostgreSQL**，SQLite 足够。

---

## 4. 关键设计决策（待确认）

### D1：前端用 CDN Vue 还是纯 HTML+Vanilla JS？

- [A] 纯 HTML + Vanilla JS（保持现状，简单，但规则编辑/多组件协同难维护）
- [B] Vue 3 CDN（CDN 引入无需构建，组件化好，维护性高）
- [C] Svelte CDN（比 Vue 更轻，但生态稍弱）
- [D] 继续探索其他方案

### D2：server.py 和 engine 的关系？

- [A] server.py 直接 import engine Python 模块（推荐，最干净）
- [B] server.py 通过 subprocess 调用 engine_cli.py（改动小但有进程开销）

### D3：日志实时流方案？

- [A] Server-Sent Events（SSE）— 简单，Flask 支持好
- [B] WebSocket — 复杂度高，除非有多人实时协作需求

### D4：enabled 字段放在 YAML 顶层还是 source 下？

- [A] 顶层 `enabled: true`（推荐，结构清晰，不侵入 source）
- [B] `source.enabled: true`（避免新增顶层字段）

### D5：Cron 任务配置存在哪？

- [A] `~/.hermes/cron/` YAML（复用 Hermes机制，看板只做图形化管理）
- [B] 独立 `APP/dashboard/cron/` 目录
- [C] SQLite（不推荐，增加复杂度）

---

## 5. 模块优先级

| 优先级 | 模块 | 理由 |
|--------|------|------|
| P0 | 模块 1 规则管理 + 模块 6 首页 | 核心价值 |
| P1 | 模块 3 任务执行状态 | 调试刚需 |
| P1 | 模块 4 日志查看 | 调试刚需 |
| P2 | 模块 2 Cron 管理 | 自动化运维 |
| P2 | 模块 5 数据预览 | 数据确认 |
| P3 | 导入导出、通知等 | 锦上添花 |

---

## 6. 开发策略

**单模块开发、验证、上线：**
1. 先做 server.py 基础框架 + Vue 前端骨架
2. 模块 1 规则管理（RM）：API + 前端 CRUD，完整走通
3. 模块 6 首页仪表盘：接 RM 数据
4. 模块 3 任务执行：接 engine 直接 run
5. 模块 4 日志查看
6. 模块 2 Cron 管理
7. 模块 5 数据预览

**每个模块**：后端 API → Postman 或 curl 验证 → 前端接入 → 完整测试

---

> **请回复你的选择（A/B/C/D）和任何补充意见，我会据此更新文档并开始开发。**
