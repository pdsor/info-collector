# 规则沙箱试采设计

## 目标

在 Rule Center 中增加“试采”能力，使用户可以直接用编辑器里的 YAML 规则抓取少量数据并查看结果，不需要先保存为正式规则，也不污染正式输出、任务历史和治理中心。

## 范围

- 前端 Rule Center 增加 `试采` 按钮和结果面板。
- 后端新增 `POST /api/rules/preview`。
- 引擎增加副作用受控的预览入口，只执行规则解析、采集、治理和结果截断。
- 第一版不做实时 SSE，不写入 `APP/engine/output`，不创建正式 `task_history` 记录。

## 交互设计

用户在 Rule Center 中新建或编辑 YAML 后，点击 `试采`。按钮在没有选中规则或正在保存/试采时禁用。请求完成后，编辑器下方显示：

- 成功或失败状态。
- 采集到的总条数。
- 本次展示条数，默认最多 5 条。
- 治理摘要。
- 前 5 条结构化数据。
- 失败时显示错误信息。

试采不改变规则列表状态。用户确认结果可用后，再点击 `保存` 保存规则。

## 后端接口

`POST /api/rules/preview`

请求：

```json
{
  "yaml": "rule_id: ...",
  "limit": 5
}
```

响应成功：

```json
{
  "success": true,
  "status": "success",
  "total_collected": 12,
  "preview_count": 5,
  "items": [],
  "governance": {}
}
```

响应失败：

```json
{
  "success": false,
  "error": "错误信息"
}
```

`limit` 只影响返回展示条数，不改变采集行为。后端将 `limit` 限制在 1 到 20 之间。

## 引擎设计

在 `InfoCollectorEngine` 中新增 `preview_rule(rule_path, limit=5)`：

1. 读取并校验 YAML。
2. 检查顶层和 `source.enabled`，禁用规则返回 `skipped`。
3. 调用现有 `crawl(rule)`。
4. 调用 `GovernancePipeline(rule).process(items)`。
5. 返回治理后的前 N 条数据、总条数和治理摘要。

该方法不调用：

- `state_mgr.register_rule`
- `state_mgr.record_start`
- `deduplicate`
- `save_output`
- `state_mgr.record_finish`

这样可以避免状态、去重库和输出目录副作用。

## Dashboard 设计

`rules_api.py` 新增 `preview_rule()` 路由。为了复用引擎校验和采集逻辑，Dashboard 将当前 YAML 写入 `tempfile.NamedTemporaryFile`，调用 `InfoCollectorEngine.preview_rule()`，执行后删除临时文件。

Rule Center 前端增加：

- `previewing` 状态。
- `previewResult` 结果对象。
- `previewRule()` 方法。
- 编辑器按钮区的 `试采` 按钮。
- 结果面板，使用 `<pre>` 展示结构化 JSON。

## 错误处理

- YAML 为空：返回 400。
- YAML 解析或规则校验失败：返回 400，并展示错误。
- 采集异常：返回 200，`success=false`，前端展示错误内容。
- 后端内部异常：返回 500。

## 测试策略

- 新增引擎单测，验证 `preview_rule()` 返回采集和治理后的前 N 条数据，并且不调用保存输出。
- 新增 Dashboard API 单测，验证 `/api/rules/preview` 可以接受未保存 YAML 并返回预览结构。
- 新增 API 错误测试，验证空 YAML 返回 400。
- 前端用 `node --check` 做语法验证。
