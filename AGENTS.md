# 项目编码约束

## 技能使用规则

**收到任何编码任务，立即调用以下技能（禁止跳过）：**


1. `writing-plans` — 输出任务计划，用户批准后才能写代码
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


## 语言

- Git commit message 必须使用中文。
- 项目文档必须使用中文，除专有名词、命令、代码标识符、文件路径、API 路径外不使用英文正文。
- 代码注释必须使用中文；仅在引用第三方 API、框架约定或专有名词时保留英文。
- 面向用户的界面文案默认使用中文。

## 开发要求

- 当前项目目标以 `DOCS/LatestRequirementDocument.md` 为需求来源。
- 管理后台采用高密度、强状态、强审计的企业控制台风格，避免营销页、装饰性大屏和低信息密度布局。