# 数据预览模块改版设计

## 1. 概述

将数据预览从「主题+平台二级下拉」改为「主题列表页 → 主题详情页」模式，支持主题内跨来源搜索和数据详情查看。

## 2. 页面结构

```
/data                    → 主题列表页（入口）
/data/:subject           → 主题详情页（该主题下所有来源数据）
```

URL 采用 hash 模式（`/#/data`、`/#/data/:subject`），可分享、可收藏。

## 3. 后端 API

### 3.1 现有接口（无需改动）

| 接口 | 用途 |
|---|---|
| `GET /api/data/subjects` | 返回主题列表 `["数据要素", "测试"]` |
| `GET /api/data/platforms?subject=X` | 返回某主题下的平台列表 |
| `GET /api/data/stats` | 返回 `{subject: {platform: {count, latest_file}}}` |

### 3.2 改动接口

**`GET /api/data/preview`**
- 现状：`subject` 和 `platform` 均为必填
- 改动：`platform` 改为可选，空则返回该主题全量数据（跨所有来源）
- 返回：`{"items": [...], "total": N, "file": "..."}`

### 3.3 新增接口

**`GET /api/data/summary`** — 主题摘要，供列表页使用
- 返回结构：
```json
[{
  "subject": "数据要素",
  "platforms": [
    {"name": "cninfo", "count": 120, "latest_file": "cninfo_data_value_20260430.json"},
    {"name": "tmtpost", "count": 85, "latest_file": "tmtpost_data_articles_20260430.json"}
  ]
}]
```

## 4. 前端组件

### 4.1 路由

在 `app.js` 的 router 中新增两个 route：
- `#/data` → `DataSubjectList`
- `#/data/:subject` → `DataSubjectDetail`

### 4.2 DataSubjectList（主题列表页）

- 调用 `GET /api/data/summary`
- 布局：卡片列表或表格，每行显示：
  - 主题名
  - 来源数量（平台数）
  - 该主题总条数（platforms 求和）
  - 「查看」按钮 → 跳转 `/#/data/{subject}`
- 无数据时显示空状态

### 4.3 DataSubjectDetail（主题详情页）

- 调用 `GET /api/data/preview?subject=X`（不传 platform）
- 顶部：返回按钮 + 主题名 + 总条数
- 搜索框：来源内全文搜索（客户端筛选 `title`、`platform` 字段）
- 表格列：`来源`、`标题`、`时间`、操作
- 每行点击「展开」：以手风琴模式展开原始 JSON（折叠其他行）
- 分页：每页 50 条，后端支持 `page` + `page_size` 参数

## 5. 交互细节

| 交互 | 行为 |
|---|---|
| 点击主题卡「查看」| 跳转 `/#/data/{subject}`，页面加载时请求 `preview?subject=X` |
| 搜索框输入 | 客户端过滤（title / platform 字段包含关键字），防抖 300ms |
| 点击「展开」某行 | 展开该行 JSON，同时折叠其他已展开行（手风琴） |
| 点击「收起」或其他行「展开」 | 当前行折叠 |
| 数据为空 | 显示空状态提示「该主题下暂无数据」 |

## 6. 分页 API 约定

前端传参：`?subject=X&page=1&page_size=50`
后端返回：`{"items": [...], "total": N, "page": 1, "page_size": 50}`

## 7. 验收标准

1. 主题列表页正确显示所有主题、来源数、总条数
2. 详情页正确显示该主题下所有来源数据
3. 搜索框能正确过滤主题内数据
4. 展开行显示原始 JSON，手风琴行为正确
5. 分页正常工作
6. URL 可分享，刷新页面状态保持
