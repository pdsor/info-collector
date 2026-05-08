# 项目编码约束

## 技能使用规则

**收到任何编码任务，立即调用以下技能（禁止跳过）：**

1. `brainstorming` — 澄清需求和设计方案
2. `writing-plans` — 输出任务计划，用户批准后才能写代码
3. `verification-before-completion` — 完成后验证通过才能提交

**硬性规则：**

- 写代码前必须先有计划（禁止直接实现）
- 有测试的优先用 TDD
- 代码审查用 requesting-code-review
- 子代理驱动开发中，每个任务完成后必须请求审查

## 项目架构

```
APP/
  dashboard/       # Web 看板（Vue 3 CDN + Flask）
    apis/          # REST API（Flask blueprints）
    static/        # 前端（HTML/CSS/JS）
    migrations/    # SQLite 数据库迁移
  engine/          # YAML 驱动的信息采集引擎（CLI）
    engine_cli.py  # 主入口，subprocess 调用
    engines/       # 各平台采集逻辑
rules/             # YAML 规则文件
migrations/        # 全量数据库迁移脚本
```

## 开发环境

- Python 3.x + SQLite + Playwright
- Dashboard：`python server.py`（端口 5000）
- Engine CLI：`python engine_cli.py --rule rules/xxx.yaml`

## 验证流程（每次修改后必须执行）

任何代码修改后，必须按以下顺序验证：

### 1. 单元测试
```bash
cd /root/info-collector/APP/engine
pytest tests/ -v
```
关键测试必须全部通过。

### 2. 跑采集引擎
```bash
# 单条规则
cd /root/info-collector
python -m APP.engine.engine_cli run --rule rules/xxx.yaml

# 全部规则
python -m APP.engine.engine_cli run --all
```
观察日志输出，确认无异常。

### 3. 检查采集引擎输出
```bash
# 查看最新数据文件
ls -la APP/engine/engine/data/{subject}/{platform}/
cat APP/engine/engine/data/{subject}/{platform}/*.json | python3 -c "import sys,json; ..."

# 检查 dedup.db 记录数
sqlite3 dedup.db "SELECT COUNT(*) FROM dedup;"
```
确认文件写入正常、数据非空。

### 4. curl 看板接口验证
```bash
# 重启看板（加载最新代码）
pkill -f "python.*server.py"; sleep 1
cd /root/info-collector/APP/dashboard && python server.py &

# 验证数据预览接口
curl -s "http://localhost:5000/api/data/summary" | python3 -m json.tool
curl -s "http://localhost:5000/api/data/preview?subject=xxx" | python3 -m json.tool

# 验证其他关键接口
curl -s "http://localhost:5000/api/rules" | python3 -m json.tool
curl -s "http://localhost:5000/api/tasks" | python3 -m json.tool
```
确认接口返回数据正确。

### 5. 浏览器验证（可选）
打开 `http://localhost:5000`，检查 UI 样式、交互是否符合预期。

## 问题根因速查

- **数据预览 total=0**：检查 `APP/engine/engine/data/{subject}/{platform}/` 下是否有非空 json 文件；历史空文件需手动删除
- **去重后 0 条**：去重数据库 `dedup.db` 中已有相同 URL，是正常行为；观察日志中"采集N条"数字确认是否采到了数据
- **接口 404**：重启 Dashboard 服务加载最新代码
- **CSS 样式异常**：检查 CSS 变量是否正确定义，user-agent 样式是否被覆盖
