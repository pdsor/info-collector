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
