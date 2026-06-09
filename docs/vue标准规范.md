# SROP Vue 前端标准规范

更新时间：2026-05-25

本文档基于当前 `src` 目录、配置文件和已实现页面整理，用于 SROP 控制台后续 Vue 页面开发、组件扩展和重构验收。新增代码优先遵循本文档；当局部业务页面已有稳定模式时，以“复用现有模式、减少例外”为原则。

## 1. 项目定位

SROP 控制台是桌面端管理后台，核心体验是高密度、可审计、可维护的数据管理界面。

设计与开发目标：

- 以列表、搜索、详情、抽屉表单、状态标签和图表看板为主要界面形态。
- 页面信息密度要适合运维和安全管理场景，避免营销式大标题、装饰性模块和无业务价值的视觉噪声。
- 新增页面优先复用通用组件、全局样式、统一服务层和领域类型。
- 权限、状态、接口、分页和异步反馈必须可追踪，不能散落在页面里临时拼装。

## 2. 技术栈

| 类型 | 当前选型 | 规范用途 |
| --- | --- | --- |
| 构建工具 | Vite 6 | 本地开发、生产构建、开发代理 |
| 核心框架 | Vue 3.5 | 单文件组件、组合式 API |
| 语言 | TypeScript 5.8 | 领域模型、服务契约、组件参数 |
| 路由 | Vue Router 4 | 页面路由、登录守卫、菜单选中 |
| 状态管理 | Pinia 2 | 登录态、权限菜单、少量运行态 |
| UI 组件 | Ant Design Vue 4 | Layout、Menu、Table、Card、Drawer、Form 等 |
| 图标 | `@ant-design/icons-vue` | 菜单、按钮、状态辅助图标 |
| HTTP | Axios | 统一 API 客户端 |
| 图表 | ECharts、vue-echarts、AntV G2 | 看板图、趋势图、画像图 |
| 日期 | dayjs | 时间格式化 |
| 测试 | Vitest + jsdom | 服务契约、纯函数、组件辅助逻辑 |

命令规范：

- 开发：`npm run dev`
- 构建：`npm run build`
- 单元测试：`npm run test:run`
- 类型检查随构建执行：`vue-tsc --noEmit`
- 当前仓库未提供 ESLint 配置文件，新增 lint 规则前需同步补齐配置。

## 3. 目录规范

当前源码目录如下：

| 目录 | 职责 |
| --- | --- |
| `src/assets` | 静态资源，例如登录图 |
| `src/components` | 跨页面通用组件 |
| `src/composables` | 可复用组合式逻辑 |
| `src/directives` | 全局指令，例如 `v-permission` |
| `src/layouts` | 应用骨架、侧栏、顶栏 |
| `src/mock` | 无后端或演示场景的 fallback 数据 |
| `src/router` | 路由定义和路由守卫 |
| `src/services` | API 服务函数和请求封装 |
| `src/stores` | Pinia store |
| `src/styles` | 全局样式、主题 token、状态映射 |
| `src/types` | API、领域模型、枚举类型 |
| `src/views` | 页面级组件，按业务模块拆分 |

页面目录规则：

- 页面文件统一放在 `src/views/{module}/{controller}/{page}.vue`。
- 列表页优先使用 `index.vue`，详情页使用 `detail.vue`，编辑页使用 `edit.vue`。
- 路由路径保持后端模块语义，例如 `/business/index/index`、`/resource/device/index`、`/network/area/detail`。
- 新增通用能力先判断是否可进入 `components` 或 `composables`，不要在多个页面复制同一套实现。

## 4. 编码规范

Vue 组件规范：

- 新增 Vue 文件默认使用 `<script setup lang="ts">`。
- 引入顺序建议为：Vue API、第三方库、图标和 Ant Design、项目组件、composables、services、types。
- 组件参数必须使用 `defineProps` 声明类型；事件必须使用 `defineEmits` 声明。
- 页面状态使用 `ref`、`reactive`、`computed`，复杂业务逻辑优先抽到 composable 或 service。
- `onMounted` 只负责触发初始化，不堆积复杂数据转换。

TypeScript 规范：

- 领域对象优先维护在 `src/types/domain.ts`，通用 API 包装维护在 `src/types/api.ts`。
- 不新增隐式 `any`。确实遇到后端动态结构时，用局部 `Record<string, any>` 并限制作用域。
- 表格列、表单对象、接口参数应尽量引用领域类型，避免页面里反复声明不一致字段。
- 时间字段兼容 `number | string` 时，统一在页面辅助函数或 service adapter 中格式化。

样式规范：

- 页面级公共样式放在 `src/styles/global.css`。
- 单页特有样式使用 `<style scoped>`。
- 不使用 viewport width 缩放字号，不使用负字距。
- 避免在模板上大量内联样式；宽度、间距等一次性微调可接受，重复样式必须抽类名。

## 5. 主题与视觉

主题定义在 `src/styles/theme.ts`，通过 Ant Design Vue `ConfigProvider` 注入。新增页面必须优先使用主题 token 和全局类。

### 5.1 色彩

| 语义 | 色值 | 使用场景 |
| --- | --- | --- |
| 主色 / 信息 | `#2563EB` | 主按钮、链接、选中状态、关键强调 |
| 成功 | `#0E9F6E` | 启用、在线、正常、健康 |
| 错误 | `#DC2626` | 删除、失败、异常、离线 |
| 警告 | `#D97706` | 待处理、中危、告警、积压 |
| 强调橙 | `#EA580C` | 高危、阶段性强调 |
| 紫色 | `#7C3AED` | 演示环境等辅助状态 |
| 主文本 | `#111827` | 标题、正文重点 |
| 正文文本 | `#1F2937` | 表格和内容文本 |
| 次级文本 | `#4B5563`、`#6B7280` | 描述、标签、辅助信息 |
| 边框 | `#E5E7EB`、`#EEF2F7` | 容器、表格、分割线 |
| 页面背景 | `#F3F6FB` | Layout 内容区 |
| 容器背景 | `#FFFFFF` | Card、Drawer、Header |
| 侧栏背景 | `#001529` | 左侧导航 |

状态色和状态文案统一维护在 `statusColors`、`statusLabels`。业务状态展示优先使用 `StatusTag`，不要在页面里重新写颜色映射。

### 5.2 圆角、阴影、密度

- 全局基础圆角为 `8px`。
- `Tag` 小圆角为 `4px`。
- `Button`、`Input`、`Select` 控件高度为 `34px`。
- Card 可以使用轻量阴影，当前主题为 `0 8px 24px rgba(15, 23, 42, 0.05)`。
- 后台页面保持紧凑，不做大面积留白和嵌套卡片。

### 5.3 字体

全局字体定义在 `src/styles/global.css`：

```css
"Hiragino Sans GB", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC",
-apple-system, BlinkMacSystemFont, "Helvetica Neue", "Noto Sans SC", sans-serif
```

字号规范：

| 层级 | 规格 | 使用场景 |
| --- | --- | --- |
| 页面标题 | `20px / 28px`，字重 `600` | `.srop-page-title` |
| 页面描述 | `13px / 20px` | `.srop-page-description` |
| 表格标题 | `15px`，字重 `600` | `.srop-table-header-title`、`.srop-table-total` |
| 表格正文 | `13px` | Ant Design Table |
| 详情标签 | `13px` | `.srop-info-label` |
| 代码块 | `12px / 1.6` | `.srop-code-block` |

## 6. 布局规范

应用骨架：

- 外层使用 Ant Design `Layout`。
- 左侧侧栏宽度 `220px`，折叠宽度 `64px`。
- 顶栏高度 `56px`。
- 内容区使用 `.srop-page-content`，最小视口宽度 `1180px`。
- 控制台以桌面端为主，低于 `1280px` 只做必要间距收敛，不按移动端重排完整功能。

标准页面结构：

```vue
<template>
  <SropPage>
    <SropPageHeader title="页面名称" description="页面能力说明">
      <a-button type="primary">
        <PlusOutlined /> 新增
      </a-button>
    </SropPageHeader>

    <a-card class="srop-search-card" :bordered="false">
      <!-- 搜索表单 -->
    </a-card>

    <a-card class="srop-table-card" :bordered="false">
      <!-- 表格 -->
    </a-card>
  </SropPage>
</template>
```

全局类名职责：

| 类名 | 用途 |
| --- | --- |
| `.srop-page` | 页面内边距 |
| `.srop-page-content` | 内容区背景和最小高度 |
| `.srop-page-header` | 页面标题和页面级操作 |
| `.srop-page-title` | 页面标题 |
| `.srop-page-description` | 页面说明 |
| `.srop-title-group` | 返回按钮和标题组合 |
| `.srop-search-card` | 列表页搜索条件容器 |
| `.srop-search-form` | 行内搜索表单 |
| `.srop-table-card` | 列表页表格容器 |
| `.srop-table-header` | 表格上方标题和操作区 |
| `.srop-table-total` | 表格标题或总量提示 |
| `.srop-section` | 区块间距 |
| `.srop-code-block` | JSON、日志、代码展示 |
| `.srop-info-grid` | 详情信息网格 |
| `.srop-text-block` | 详情长文本块 |
| `.srop-fixed-actions` | 编辑页底部固定操作栏 |

## 7. 路由与导航

路由规范：

- 路由统一维护在 `src/router/routes.ts`。
- 私有页面必须挂在 `MainLayout` 的 `children` 下。
- 公开页面设置 `meta.public = true`，当前公开页面为 `/login`。
- 页面 `meta.title` 必填，用于顶栏、浏览器标题或后续面包屑扩展。
- 详情页使用 `/detail?id=xxx`，编辑页使用 `/edit?id=xxx` 或无 id 新增。

菜单规范：

- 菜单源维护在 `src/stores/permission.ts` 的 `defaultMenuList`，由权限路由过滤。
- 菜单图标必须使用 `@ant-design/icons-vue` 的图标名。
- 新增页面进入菜单前先判断是否为独立功能入口；详情、编辑、流程内页面不作为一级菜单。
- `route_edit`、`route_delete` 用于按钮权限判断，不作为实际页面入口时也要保持语义清晰。
- 详情页菜单选中应回落到对应列表页。

权限规范：

- 按钮权限优先使用 `v-permission="'/module/controller/action'"`。
- 需要在脚本中判断权限时使用 `usePermission()`。
- 超级管理员绕过权限检查；普通用户只允许访问权限路由。
- 新增后端接口权限路径时，必要时同步维护 `routeAliases`，保证旧路径和新路径能正确映射。

## 8. 列表页规范

列表页是当前项目最主要页面形态，推荐结构为“搜索卡片 + 表格卡片 + Drawer 或跳转操作”。

搜索区：

- 使用 `a-card.srop-search-card` 包裹。
- 表单使用 `a-form layout="inline"` 和 `.srop-search-form`。
- 文本搜索使用 `a-input`，枚举使用 `a-select`，时间范围使用 `a-range-picker`。
- 输入框应设置 `allow-clear` 和 `autocomplete="off"`。
- 查询按钮使用 `type="primary"` 并配 `SearchOutlined`。
- 重置按钮必须清空筛选条件并重新拉取列表。

表格区：

- 使用 `a-card.srop-table-card` 包裹。
- 表格上方使用 `.srop-table-header` 放标题、总量和新增按钮。
- `a-table` 必须设置 `row-key`。
- 分页优先复用 `useTable`，默认 `pageSize = 8`，展示 `共 n 条`。
- 列宽建议：状态 `90-120px`，时间 `160-180px`，操作 `120-180px`。
- 状态列使用 `StatusTag`。
- 空值展示统一使用 `--` 或页面内 `textValue()` 辅助函数。

操作列：

- 使用 `a-space` 包裹操作按钮。
- 表格内按钮使用 `size="small"`。
- 编辑、详情使用普通或 `type="primary" ghost`。
- 删除使用 `danger`，并配 `a-popconfirm`。
- 异步操作成功后提示并刷新列表。

## 9. 表单、Drawer 与编辑页

Drawer 使用场景：

- 新增、编辑、模板、简单配置等不需要离开列表上下文的任务。
- 常用宽度：普通表单 `520-600px`，复杂表单 `700-920px`。
- Drawer footer 放“取消”和“保存”，保存按钮绑定明确 loading。
- Drawer body 可用 `a-divider orientation="left"` 分组。

独立编辑页使用场景：

- 表单字段多、需要跨区块编辑、需要底部固定操作栏。
- 使用 `.srop-form-card` 分组，底部操作使用 `.srop-fixed-actions`。
- 新增和编辑可共用 `edit.vue`，通过 query `id` 判断模式。

表单规范：

- 表单统一使用 `layout="vertical"` 或列表搜索的 `layout="inline"`。
- 必填字段必须写 Ant Design `rules`。
- 数字使用 `a-input-number`，枚举使用 `a-select`，长文本使用 `a-textarea`。
- 复杂联动字段要在变更时清理下游字段，避免提交过期值。
- 提交前调用 `formRef.value?.validate()`，不要只依赖按钮点击。
- 提交成功后关闭 Drawer 或跳回列表，并刷新数据。

## 10. 详情页规范

详情页适合展示只读业务信息、关联列表、图表和原始数据。

推荐规则：

- 顶部使用 `SropPageHeader showBack` 或页面内返回按钮。
- 详情数据加载时使用 `a-spin`；缺少 id 或加载失败使用 `a-alert`。
- 标准详情信息优先使用 `.srop-info-grid`、`.srop-info-item`、`.srop-info-label`、`.srop-info-value`。
- Ant Design `Descriptions`、`Tabs`、`Table` 可用于复杂详情。
- 长文本使用 `.srop-text-block`，JSON 或日志使用 `.srop-code-block`。
- 时间格式化统一使用 dayjs，输出 `YYYY-MM-DD HH:mm:ss`。
- 详情页不要承担新增编辑流程，编辑应跳转 `edit.vue` 或打开 Drawer。

## 11. 通用组件规范

当前已沉淀组件：

| 组件 | 用途 |
| --- | --- |
| `SropPage` | 页面容器，输出 `.srop-page` |
| `SropPageHeader` | 标题、描述、返回按钮、页面级操作 |
| `SropToolbar` | 兼容旧列表工具栏 |
| `StatusTag` | 按业务域输出状态标签 |
| `BackButton` | 返回上一页 |
| `TrendChart` | ECharts 图表容器 |
| `G2Chart` | AntV G2 图表容器 |

新增组件要求：

- 只封装跨页面复用且职责清晰的能力。
- props 命名使用 camelCase，模板中按 Vue 规范写 kebab-case。
- 组件不直接读页面路由，除非它就是路由相关组件。
- 组件不直接调用业务 service，除非它是业务组件且命名体现业务范围。
- 通用组件不得写死具体业务状态和接口路径。

## 12. 数据、服务与 API

API 客户端：

- 统一使用 `src/services/apiClient.ts`。
- 页面不得直接引入 Axios。
- `apiClient` 统一处理 token、登录跳转、响应 code、错误提示。
- `postFormUrlEncoded` 用于后端要求 `application/x-www-form-urlencoded` 的接口。
- 真实接口基准由 `VITE_API_BASE_URL` 和 Vite `/api` proxy 共同支持。

服务函数：

- 每个业务域在 `src/services/{domain}.ts` 中维护接口函数。
- 函数命名使用动宾结构，例如 `getAssetsList`、`updateAssets`、`deleteBusiness`。
- 列表接口参数使用 `ListParams`，返回遵循 `ApiResponse<PaginatedData<T>>` 或现有后端结构。
- 页面层只关心 service 的业务返回，不拼接后端 URL，不处理 token。
- mock fallback 只能作为无后端演示或兼容手段，生产路径不能依赖 mock store 表示真实后端状态。

列表查询约定：

```ts
search({
  name: { value: filters.name, operator: '~' },
  status: filters.status,
})
```

使用模糊搜索时沿用 `{ value, operator: '~' }` 结构；精确枚举直接传值。

## 13. 状态与反馈

加载状态：

- 表格使用 `Table loading`。
- 页面详情使用 `a-spin`。
- 按钮异步操作使用独立 loading，例如 `submitLoading` 或当前记录 id。
- 避免多个按钮共享同一个无法区分动作的 loading。

反馈规则：

- 创建、更新、删除成功使用 `message.success`。
- 可恢复提醒使用 `message.info`。
- 表单校验、业务阻断使用 `message.warning`。
- API 或未知异常由 `apiClient` 统一提示；页面只在需要更具体语义时补充提示。

危险操作：

- 删除、停用、重置、清空、覆盖类操作必须二次确认。
- 确认文案要说清对象和结果，例如“确定删除该资源？”。
- 危险按钮使用 `danger`。
- 高风险操作如后续需要填写原因，应封装统一原因确认弹窗后再复用。

## 14. 图表规范

图表组件：

- 常规 ECharts 使用 `TrendChart`，默认高度 `280px`，支持 `height` 覆盖。
- G2 自定义图使用 `G2Chart`，默认高度 `400px`。
- 图表容器宽度固定为 `100%`，依靠组件自动适配。

ECharts 默认配置：

- `grid: { left: 36, right: 24, top: 48, bottom: 28 }`
- `tooltip: { trigger: 'axis' }`
- 常用色遵循主题语义：主趋势蓝色，健康绿色，异常红色，告警橙色。

图表页面要求：

- 图表必须有稳定高度，不能依赖内容撑开。
- 无数据时展示空状态或隐藏图表并给出说明。
- 可点击图表需要声明 `@click` 事件处理，不在 option 内写散乱副作用。
- 画像、趋势等复杂 render 函数可放在页面内，但应保持函数短小，公共计算抽出。

## 15. 样式与可访问性细节

按钮：

- 主操作使用 `type="primary"`。
- 查询、新增等常见操作优先配图标。
- 图标使用 `@ant-design/icons-vue`，不要手写 SVG。
- 表格操作按钮文案保持短词，避免挤压列宽。

文本：

- 长文本使用 `Typography.Text ellipsis`、表格 `ellipsis`、Tooltip 或详情页展开。
- 表格和卡片内不要使用过大的标题字体。
- 页面标题保持短句，解释性内容放到 description。

布局：

- 不做卡片套卡片的装饰结构。
- 页面区块间距优先使用 `.srop-section` 或 Card 间 `margin-bottom`。
- 固定格式区域要设置明确尺寸或 grid 轨道，避免 hover、loading、标签变更导致跳动。

## 16. 测试与验收

新增或修改代码后，根据影响范围执行：

- 只改文档：无需构建。
- 改 TypeScript、Vue、service：执行 `npm run build`。
- 改 service 契约、纯函数、权限逻辑：补充或更新 Vitest，并执行 `npm run test:run`。
- 改视觉布局：本地启动 `npm run dev`，检查典型列表页、详情页、Drawer 和窄桌面宽度。

测试建议：

- service 测试覆盖 URL、method、payload、异常返回。
- composable 测试覆盖初始状态、成功、失败和边界参数。
- 权限逻辑测试覆盖超管、普通用户、别名路由和详情页回落。
- 高风险操作至少测试规则函数或服务契约，不只依赖手工点击。

## 17. 禁止项

- 禁止页面组件直接调用 Axios。
- 禁止在页面里重复维护状态颜色和状态中文映射。
- 禁止新增手写 SVG 图标，除非是正式品牌资产。
- 禁止把详情页、编辑页、流程内页面加入一级菜单。
- 禁止生产功能依赖 mock 数据表达真实后端状态。
- 禁止营销式 hero、装饰性渐变背景、无业务意义的大图和大标题。
- 禁止让按钮、标签和表格内容在容器内溢出。
- 禁止无确认地执行删除、停用、覆盖、清空等危险操作。

## 18. 新页面检查清单

提交新增或重构页面前逐项确认：

- 是否放在正确的 `src/views/{module}/{controller}` 目录？
- 是否已在 `src/router/routes.ts` 配置路由和 `meta.title`？
- 是否需要同步 `defaultMenuList`、`route_edit`、`route_delete` 或 `routeAliases`？
- 是否使用 `SropPage`、`srop-search-card`、`srop-table-card` 等现有布局？
- 表格是否设置 `row-key`、loading、分页和合理列宽？
- 搜索是否支持重置，模糊查询参数是否符合现有后端约定？
- 状态是否使用 `StatusTag` 或扩展 `statusColors`、`statusLabels`？
- 新增、编辑、删除是否通过 service 调用，页面没有直接 Axios？
- 异步操作是否有 loading、成功提示和失败兜底？
- 删除或高风险操作是否有确认？
- 表单是否有必填 rules 和提交前 validate？
- 详情页是否处理缺少 id、加载中、加载失败和空值？
- 是否需要补充 `domain.ts`、`api.ts` 类型？
- 是否按影响范围执行了 `npm run build` 或 `npm run test:run`？
