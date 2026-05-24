# Info Collector NG 概要设计手册

| 文档名称 | Info Collector NG 系统概要设计手册 |
|----------|-----------------------------------|
| 文档编号 | IC-NG-SDD-001 |
| 版本号 | v2.2 |
| 发布日期 | 2026-05-13 |
| 文档密级 | 内部公开 |
| 作者 | 架构组 |
| 审核人 | 待定 |
| 批准人 | 待定 |

---

## 修订历史

| 版本 | 日期 | 修订内容 | 作者 |
|------|------|----------|-------|
| v2.0 | 2026-04-20 | 初始总体规划，定位 AI 驱动，存在架构缺陷 | 原始团队 |
| v2.1 | 2026-05-13 | 修正 AI 层职责、任务模型、浏览器池等关键问题 | 架构组 |
| v2.2 | 2026-05-13 | 完全移除系统中 AI 组件依赖，回归纯规则驱动架构 | 架构组 |

---

## 目录

1. 引言  
   1.1 项目背景与定位  
   1.2 设计范围与边界  
   1.3 定义与缩略语  
2. 现有问题分析与设计应对  
3. 系统总体架构  
   3.1 核心定位与设计原则  
   3.2 系统逻辑架构图  
   3.3 关键架构决策  
4. 核心领域模型  
   4.1 Source（数据源）  
   4.2 Rule（采集规则）  
   4.3 Task（采集任务）  
   4.4 实体关系  
5. 模块设计  
   5.1 Source Service  
   5.2 Rule Service  
   5.3 Task Service 与调度中心  
   5.4 采集执行引擎  
   5.5 数据治理管道  
   5.6 健康度监控  
   5.7 存储与索引子系统  
   5.8 Dashboard 设计  
6. 数据治理与质量  
   6.1 数据分层  
   6.2 去重策略  
   6.3 内容清洗与注入防护  
   6.4 可信度与质量评分  
7. 技术选型与组件清单  
8. 部署架构与运维  
   8.1 容器化部署视图  
   8.2 资源规划  
   8.3 监控与日志  
9. 分阶段实施路线  
10. 风险与缓解措施  
附录 A：规则 DSL Schema 草案  
附录 B：任务状态机与超时处理  

---

## 1. 引言

### 1.1 项目背景与定位
Info Collector NG 定位为**规则驱动的互联网知识采集与治理平台**。系统将分散的互联网公开信息转化为结构化、可检索、可向量的知识资产，成为“互联网数据资产生产系统”。其核心使命是为下游检索、向量化、知识图谱等应用提供高质量数据基础，系统自身不承载对话式产品、大模型推理或 BI 分析。

系统能力主线：
- 规则化全域采集
- 严格结构化输出
- 多层级数据治理
- 知识底座构建

### 1.2 设计范围与边界
**系统负责：**
- 数据源发现、注册与生命周期管理
- 基于 YAML DSL 的采集规则管理（人工编写维护）
- 多引擎网页采集（静态 HTTP、动态浏览器渲染、API）
- 采集结果结构化提取，禁止原始 HTML 直接入库
- 数据清洗、去重、结构化校验、注入防护
- 知识实体提取（基于规则）、分类、向量化（可选嵌入服务）
- 数据存储、索引与对外查询接口

**系统明确不负责：**
- 任何形式的 AI/大模型调用（不在系统内调用 LLM，不集成 AI Agent）
- BI 报表、可视化大屏
- 大模型训练、推理服务
- 复杂多租户权限（MVP 阶段单用户本地部署）
- 最终面向用户的 RAG 对话系统

### 1.3 定义与缩略语
| 术语 | 说明 |
|------|------|
| Source | 互联网数据源 |
| Rule | 采集规则，采用 YAML DSL |
| Governance Pipe | 数据治理管道 |
| Embedding Layer | 向量化存储层（由可选的本地嵌入服务生成） |
| Crawl Scheduler | 采集调度器 |

---

## 2. 现有问题分析与设计应对
本版本（v2.2）针对早期方案中**过度依赖 AI** 的问题进行彻底纠正，确保系统可在无 AI 环境稳定运行，决策均由确定性规则和人工维护完成。

| 原方案问题 | 风险等级 | 本设计修正方式 |
|------------|----------|----------------|
| 原设计包含 Source Agent、Rule Agent、Health Agent 等 AI 模块，系统耦合外部大模型 | 高 | 全部移除。来源发现由人工或外部工具提供，规则由人工编写上传，健康检测基于传统选择器校验和统计 |
| AI 直接参与规则生成和修复，稳定性不可控 | 高 | 规则仅接受人工或离线编写的 YAML 文件上传，系统提供沙箱验证和效果预览，不自动修改规则 |
| 架构图中 AI Control Layer 直接调度采集 | 高 | 移除 AI Control Layer，任务调度完全由 Task Service 负责 |
| 使用 Crawl4AI 等 AI 提取组件 | 中 | 删除该组件，统一使用 parsel/lxml + 规则选择器进行提取 |
| 健康度检测依赖 LLM 分析 | 中 | 健康度改为基于 DOM 漂移检测（选择器失效）、字段缺失率、响应状态码等硬件指标，完全确定性 |

---

## 3. 系统总体架构

### 3.1 核心定位与设计原则
- **规则中心化**：一切采集行为由版本化 DSL 规则定义，不依赖 AI 判断。
- **结构化强制**：采集结果必须为键值对字段集合，原始 HTML 仅在规则明确指定时保留。
- **人工闭环**：规则编写、验证、发布全流程由人主导，系统只做校验和辅助预览。
- **数据分层治理**：Raw → Parsed → Knowledge → Embedding，各层可追溯，不允许跳过。
- **弹性可扩展**：采集、治理全流程组件化，支持横向扩展。

### 3.2 系统逻辑架构图（v2.2）

```text
┌─────────────────────────────────────────┐
│             Dashboard / API             │
└───────────────┬─────────────────────────┘
                │
   ┌────────────┼──────────────┐
   ▼            ▼              ▼
Source Svc   Rule Svc      Task Svc       ← 核心业务服务
   │            │              │
   └────────────┼──────────────┘
                │
                ▼
        ┌───────────────┐
        │ Crawl Scheduler│                ← 调度控制
        └───────┬───────┘
                │
   ┌────────────┼──────────────────┐
   ▼            ▼                  ▼
HTTP Fetcher  Browser Renderer  API Fetcher  ← 执行组件
   └────────────┼──────────────────┘
                │
        ┌───────▼────────┐
        │ Governance Pipe │                ← 治理管道（异步 Worker）
        └───────┬────────┘
                │
   ┌────────────┼────────────────────┐
   ▼            ▼                    ▼
Raw Store   Structured DB      Vector Store    ← 数据分层存储
(MinIO)     (PostgreSQL)        (Milvus)
                │
        ┌───────▼────────┐
        │  Knowledge API │                ← 对外检索接口
        └────────────────┘
```

> 与早期版本相比，彻底去除 AI Control Layer 及所有 Agent，形成清晰的“规则驱动、人工管理”链路。

### 3.3 关键架构决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 任务调度 | Task Service + Celery | 单一入口，确定性调度 |
| 规则生成 | 人工编写 + 离线辅助（可选） | 保证规则质量和可控 |
| 规则验证 | 沙箱试采，预览提取结果 | 避免无效规则进入生产 |
| 浏览器渲染 | Playwright Cluster 池化管理 | 解决大规模动态采集时的资源瓶颈 |
| 数据提取 | 基于规则选择器 + parsel/lxml | 稳定、高性能、可预测 |
| 知识实体提取 | 基于规则的正则/选择器模板 | 无需 AI，确定性产出 |
| 向量化 | 可选：本地嵌入服务 bge-m3 | 生成向量供下游使用，系统本身不对接外部 AI 服务 |
| 健康度监控 | 选择器有效性 + 字段缺失率 + 响应状态 | 纯逻辑检测，无黑盒依赖 |

---

## 4. 核心领域模型

### 4.1 Source（数据源）
Source 是系统最核心的实体，所有采集、治理、质量评估均绑定到 Source。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 唯一标识 |
| name | String | 来源名称 |
| domain | String | 根域名 |
| type | Enum | website/forum/social/api/rss/repo/file/media |
| category | String | 人工分类 |
| trust_score | Float | 0-1 可信度（基于历史质量计算） |
| update_frequency | Integer | 建议采集间隔（秒） |
| anti_crawl_level | Enum | low/medium/high/very_high |
| parser_strategy | String | 默认解析策略标识 |
| auth_required | Boolean | 是否需要认证 |
| language | String | 主要语言 |
| tags | Array | 标签 |
| enabled | Boolean | 是否激活 |

**生命周期**：`DISCOVERED → VERIFIED → ACTIVE → PAUSED → DEPRECATED → ARCHIVED`。来源发现可由外部工具或人工完成，通过 API 注册进入系统。

### 4.2 Rule（规则）
规则采用 **YAML DSL 分层设计**，完全由人编写或离线工具生成后上传。系统提供 Schema 校验、兼容性检查与沙箱验证。

| 层 | 职责 |
|----|------|
| discovery | 来源发现规则（如 RSS 地址） |
| list | 列表页采集 |
| detail | 详情页采集 |
| extraction | 字段提取定义 |
| transform | 数据转换（类型、过滤） |
| governance | 治理规则（去重方式、清洗标记） |
| output | 输出控制（是否保存 Raw） |

**规则版本**：每条 Rule 有递增版本号，状态包括 `DRAFT`、`TESTING`、`PRODUCTION`、`DEPRECATED`。发布和回滚需人工操作。一个 Source 可关联多条规则（如不同版本），但只有一个版本处于 `PRODUCTION` 状态。

规则示例：
```yaml
rule_id: 3fa85f64-5717-4562-b3fc-2c963f66afa6
source_id: 1a2b3c...
version: 2
status: PRODUCTION
list:
  url: "https://example.com/news?page={page}"
  pagination:
    type: param
    param: page
    start: 1
    step: 1
extract:
  title: { selector: "h1" }
  content: { selector: "div.article-body", type: html }
  publish_time: { selector: "time", format: "ISO8601" }
governance:
  dedup: simhash
  save_raw: false   # 不保存原始HTML
output:
  fields: [title, content, publish_time]
```

### 4.3 Task（任务）
每次采集执行实例为一个 Task，记录完整生命周期。

**状态机**：`PENDING → QUEUED → RUNNING → (RETRYING →)* → SUCCESS / FAILED / CANCELLED / PARTIAL_SUCCESS`

新增**超时处理**：每个任务携带 `max_runtime`，超时后自动标记 `FAILED` 并记录原因 `TIMEOUT`。死信队列用于多次重试失败任务。

**关键属性**：priority、retry_count、max_retries、source_id、rule_id、沙箱标记（用于验证任务）。

### 4.4 实体关系
```
Source 1 ──── * Rule (versioned)
Source 1 ──── * Task
Rule  1 ──── * Task
```

---

## 5. 模块设计

### 5.1 Source Service
- Source 注册、编辑、状态变更 API
- 支持批量导入（JSON/CSV）
- 来源信任分自动计算（根据采集成功率、字段完整率）
- 提供来源健康度摘要

### 5.2 Rule Service
- 管理 DSL 规则版本的完整生命周期
- 严格 Schema 校验，拒绝不符合规范的规则上传
- 兼容性检查（字段变更兼容性）
- 沙箱验证触发：接收规则，创建隔离采集任务，返回提取结果预览
- 发布、回滚均需确认，记录操作日志

**规则上传验证流程**：
1. 上传 YAML，系统进行 Schema 校验。
2. 校验通过后，用户可请求“沙箱测试”，系统创建临时 Task（限制采集页面数 1~2），使用该规则试采。
3. 返回每个字段的提取成功率和样本值预览，用户确认后手动发布为 PRODUCTION。

### 5.3 Task Service 与调度中心
- 负责任务创建、暂停、重试、查询
- 对接 Celery 调度器，按 Source 优先级和限速策略分发
- 沙箱任务使用独立低并发队列，避免影响生产采集
- 提供细粒度事件流（状态变更、日志）推送至 Dashboard
- 超时与死信：利用 Celery 的 `soft_time_limit`，超时任务自动标记失败；超过最大重试次数的任务移入死信队列，由人工处理

### 5.4 采集执行引擎
引擎拆分为可组合的 Pipeline，核心原则：**只产出规则定义的结构化字段，默认不得保留原始 HTML**。

| 组件 | 功能 | 约束 |
|------|------|------|
| Fetcher | 基于 httpx 的 HTTP 请求，支持重试、代理、会话维持 | 返回字节流，不进行解析 |
| Renderer | Playwright 浏览器渲染 | 仅当规则 `render: true` 时启用；浏览器池按 anti_crawl_level 分配独立 Profile |
| Extractor | 基于规则 DSL 的选择器提取 | 使用 parsel + lxml，提取结果必须是键值对；若规则未指定 `save_raw: true`，则丢弃原始响应内容 |
| Deduplicator | SimHash/MinHash 去重 | 基于提取后字段组合 |
| Output Adapter | 将结构化数据写入治理管道 | 标记字段缺失率，缺失过高则任务标记 `PARTIAL_SUCCESS` 或 `FAILED` |

**非 API 网页采集强化设计**：
- 支持 JS 动态渲染、无限滚动、Shadow DOM 穿透。
- 反爬对抗：自动 Cookie 持久化、TLS 指纹伪装、CAPTCHA 人工处理接口（仅记录，系统不自动打码）。
- 渲染超时后可降级为静态 HTTP 提取（若规则允许）。
- 浏览器池：采用预启动 Playwright Cluster，按域名限流，动态扩缩。

### 5.5 数据治理管道
治理管道为独立的 Celery Worker 集合，异步处理采集产出：

1. **字段校验**：检查规则定义的必填字段是否存在，缺失率超过阈值则任务标记失败。
2. **数据清洗**：移除残留 HTML 标签、控制字符、潜在注入内容。
3. **去重**：按规则指定的去重策略执行。
4. **内容分类**：基于规则模板（如 URL 模式、字段关键词）添加分类标签。
5. **向量化**（可选）：若开启，调用本地嵌入服务生成向量，存入 Milvus。
6. **存储**：结构化数据写入 PostgreSQL，原始内容仅在 `save_raw: true` 时存入 MinIO。

### 5.6 健康度监控
完全基于确定性指标，不依赖 AI。系统以定时任务形式检测已上线规则的健康状况：

- **选择器有效性**：定期对 Source 样本页使用当前规则选择器测试，若主选择器全部失效，规则标记为 `NEEDS_FIX`。
- **字段缺失率**：统计近期任务各字段产出比例，缺失率突增触发告警。
- **响应状态**：统计 HTTP 4xx/5xx 比例、渲染超时次数。
- **DOM 漂移量化**：通过采集样本页的 DOM 结构指纹（标签序列哈希），与规则创建时的指纹对比，差异超过阈值则发出“页面结构变更”告警。

告警通过 Dashboard 展示，并可配置通知。所有修正仍由人工修改规则后上传。

### 5.7 存储与索引子系统
| 层级 | 存储 | 说明 |
|------|------|------|
| Raw | MinIO | 原始响应（仅在规则 `save_raw: true` 时），带 Task 元数据，不可变 |
| Parsed | PostgreSQL (JSONB) | 结构化提取结果，关联 Source、Rule、Task |
| Knowledge | PostgreSQL（实体/关系表） | 基于规则模板提取的实体、时间线等 |
| Embedding | Milvus | 向量库，由可选嵌入服务生成 |
| Full-text Search | Elasticsearch | Parsed 数据副本，供关键词检索 |
| 元数据/配置 | PostgreSQL | Source, Rule, Task, 健康度等 |

### 5.8 Dashboard 设计
重构为四大中心：
- **Source Center**：来源列表、状态、信任分、更新频率管理
- **Rule Center**：规则编辑器（YAML）、版本对比、沙箱测试结果查看、发布/回滚
- **Task Center**：实时任务监控、日志查看、重试、沙箱任务隔离显示
- **Governance Center**：去重统计、字段完整率趋势、健康度告警处理

---

## 6. 数据治理与质量

### 6.1 数据分层处理
严格分层，不允许从采集直接写入最终存储。治理管道保障每一层数据清洗和标记，Raw 层为可避责的审计基础。

### 6.2 去重策略
- 单 Source 内使用精确内容哈希 + SimHash 近重复检测。
- 跨 Source 去重在 Parsed 入库时通过 Elasticsearch 的 `more_like_this` 或 SimHash 海明距离实现。
- 保留策略：保留最新或字段完整度高的版本。

### 6.3 内容清洗与注入防护
- 移除常见指令注入模式（如 `Ignore previous instructions` 等字符串），并标记 `injection_risk` 标签。
- 对清洗后内容进行风险评分，高风险内容入人工审核队列。

### 6.4 可信度与质量评分
- Source 信任分：基于权威性基础分 + 历史字段完整率 + 采集成功率 + 人工标记。
- 任务质量评分：字段提取率、反爬拦截状态、清洗后内容合规度。

---

## 7. 技术选型与组件清单
选型原则：所有组件不依赖外部 AI 服务，仅在可选的嵌入服务中使用本地模型。

| 分层 | 组件 | 用途 |
|------|------|------|
| API 框架 | FastAPI | 异步 API 服务 |
| 任务队列/调度 | Celery + Redis | 采集与治理任务分发 |
| ORM | SQLAlchemy 2.0 | 异步数据库操作 |
| 关系数据库 | PostgreSQL 15+ | 元数据、结构化数据 |
| 对象存储 | MinIO | Raw 数据归档 |
| 搜索引擎 | Elasticsearch 8.x | 全文检索 |
| 向量数据库 | Milvus 2.3+ | 向量存储（可选） |
| 缓存 | Redis | 限速、状态缓存 |
| HTTP 采集 | httpx | 高性能异步 HTTP |
| 浏览器渲染 | Playwright + 池化管理 | 动态页面采集 |
| HTML 解析 | parsel + lxml | 基于规则选择器提取 |
| 嵌入服务（可选） | bge-m3 (本地 CPU/GPU) | 向量化生成，系统不调用外部 API |
| 规则 Schema 校验 | jsonschema / pydantic | 规则上传校验 |
| 容器化 | Docker + Kubernetes | 生产部署 |

> 明确移除：任何形式的 AI Agent 框架、LangChain、Crawl4AI、LLM 网关。向量化嵌入服务为本地独立模块，不依赖外部大模型。

---

## 8. 部署架构与运维

### 8.1 容器化部署视图
- API Server（FastAPI）
- Celery Worker（采集、治理）
- 数据库与中间件集群（PostgreSQL、Redis、Elasticsearch、Milvus、MinIO）
- 浏览器渲染 Worker 节点（资源隔离，可独立伸缩）
- 可选：嵌入服务单独部署

开发环境可使用 Docker Compose 一键启动，生产环境通过 Kubernetes 管理。

### 8.2 资源规划
- 浏览器渲染节点：每 Pod 最大并发 5 个 Browser Context，内存 ≥2GB。
- 治理 Worker 可共享节点，按负载扩缩。
- 嵌入服务如需 GPU，需独立节点。

### 8.3 监控与日志
- Prometheus + Grafana 监控任务队列长度、浏览器池利用率、字段缺失率等。
- 结构化日志输出到 ELK，关联 Trace ID。
- 健康度告警通过 Dashboard 和 Webhook 通知。

---

## 9. 分阶段实施路线

| 阶段 | 目标 | 关键交付物 |
|------|------|------------|
| Phase 1 稳定化 | 建立无 AI 的规则驱动骨架 | Source Registry、Rule v2 DSL、Task 状态机、结构化存储、Pipeline 化采集 |
| Phase 2 治理化 | 数据可直接用于下游知识检索 | 去重、清洗、注入防护、质量评分、健康度监控 |
| Phase 3 扩展化 | 丰富采集能力与规则生态 | 更多 Source 类型支持、规则模板库、社区规则市场（可选） |
| Phase 4 知识化 | 形成知识底座 | 规则化实体提取、事件时间线、Embedding 全量生成、对外知识 API |

---

## 10. 风险与缓解措施

| 风险 | 缓解 |
|------|------|
| 规则编写门槛高 | 提供丰富模板、沙箱预览、详细文档，降低出错概率 |
| 浏览器渲染成本 | 池化复用、按需渲染、静态降级 |
| 健康度误报 | 组合多项指标，设置阈值可调，人工最终确认 |
| 字段缺失导致治理停滞 | 设置缺失率容忍度，依然保存部分有效记录，便于排查 |
| 向量化嵌入服务资源消耗 | 默认关闭，按需开启；提供轻量替代（如无向量检索仅依赖 ES） |

---

## 附录 A：规则 DSL Schema 草案

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Rule",
  "type": "object",
  "required": ["rule_id", "source_id", "version", "extract"],
  "properties": {
    "rule_id": { "type": "string", "format": "uuid" },
    "source_id": { "type": "string", "format": "uuid" },
    "version": { "type": "integer" },
    "status": { "enum": ["DRAFT", "TESTING", "PRODUCTION", "DEPRECATED"] },
    "render": { "type": "boolean", "default": false },
    "list": { "type": "object" },
    "extract": {
      "type": "object",
      "additionalProperties": { "$ref": "#/definitions/field" }
    },
    "governance": { "$ref": "#/definitions/governance" },
    "output": {
      "type": "object",
      "properties": {
        "fields": { "type": "array", "items": { "type": "string" } },
        "save_raw": { "type": "boolean", "default": false }
      }
    }
  },
  "definitions": {
    "field": {
      "type": "object",
      "properties": {
        "selector": { "type": "string" },
        "type": { "enum": ["text", "html", "attribute", "list"] },
        "attribute": { "type": "string" },
        "transform": { "type": "string" }
      },
      "required": ["selector"]
    },
    "governance": {
      "type": "object",
      "properties": {
        "dedup": { "enum": ["none", "simhash", "minhash"] },
        "sanitize": { "type": "boolean", "default": true }
      }
    }
  }
}
```

---

## 附录 B：任务状态机与超时处理

```text
PENDING ──(入队)──► QUEUED ──(worker 拾取)──► RUNNING
  ▲                                              │
  │                                              ├── 成功 ──► SUCCESS
  │                                              ├── 失败 & retry_left ──► RETRYING
  │                                              ├── 超时 ──► FAILED [TIMEOUT]
  │                                              ├── 用户取消 ──► CANCELLED
  │                                              └── 部分成功 ──► PARTIAL_SUCCESS
  │
  └── 手动重试 ── 从 FAILED/CANCELLED 回到 PENDING
```

- `max_runtime` 通过 Celery `soft_time_limit` 控制，超时后 Worker 捕获信号，将任务标记为 `FAILED` 并记录超时日志。
- 超过 `max_retries` 的任务进入死信队列，需人工干预。
