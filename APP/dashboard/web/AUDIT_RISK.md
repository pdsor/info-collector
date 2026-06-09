# 前端依赖审计风险记录

## 当前结论

`npm audit --audit-level=moderate` 仍报告 `vitest`、`vite`、`vite-node`、`@vitest/mocker`、`esbuild` 开发依赖链路漏洞，共 5 项，其中 4 项中危、1 项严重。

## 影响范围

风险集中在前端构建和测试依赖链路。当前生产运行代码不直接依赖 `vitest`，但开发服务器、测试运行和构建工具链仍需要在发版风险中记录。

## 未在本轮自动修复的原因

`npm audit fix --force` 会安装 `vitest@4.1.8`，属于测试框架大版本升级，可能引入测试配置、快照、类型检查和 Vite 插件兼容性变化。本轮目标是发布就绪清理，不在同一批变更中引入破坏性依赖升级。

## 后续处理路径

单独创建依赖升级分支，升级 `vitest`、`vite` 及相关锁文件后，至少运行：

```bash
npm run test:run
npm run build
npm audit --audit-level=moderate
```

只有测试、构建和审计全部通过后，才能移除此风险记录。
