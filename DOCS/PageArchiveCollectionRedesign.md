# 页面归档式采集改版方案

| 文档名称 | 页面归档式采集改版方案 |
|----------|------------------------|
| 文档编号 | IC-NG-REDESIGN-ARCHIVE-001 |
| 版本号 | v0.1 |
| 发布日期 | 2026-05-21 |
| 文档状态 | 改版规划草案 |
| 适用范围 | Info Collector NG 采集引擎、规则 DSL、输出与后续数据治理 |

---

## 1. 背景

当前图片 OCR 试采已经证明：如果直接把某一篇文章的表格结构写死到 YAML 中，可以产出结构化结果，但这条路线在规模化时会遇到明显问题：

- 真实采集入口通常是栏目页、搜索页或公告列表，不可能人工收集每篇详情页 URL。
- 列表中的文章并非都包含目标数据，需要先筛选候选文章。
- 有些文章是总览页，真正数据分散在多个详情页、附件页或图片中。
- 不同文章的表格列数、字段名称、展示方式可能不同，强行用一个 schema 会越来越脆弱。
- 过早追求结构化会导致大量规则分支，维护成本高，且容易丢失原始证据。

因此，采集策略需要从“直接结构化抽取”调整为“先完整归档，再逐步精抽”。

## 2. 改版目标

本次改版目标是引入页面归档式采集能力：

1. 从列表页或搜索页自动发现详情页。
2. 进入详情页后尽量完整保留页面正文、图片、OCR 文本和来源证据。
3. 将页面内容转换为类似 Markdown 的可读文档。
4. 同时保留块级结构，避免只保存一整段纯文本导致后续难以精抽。
5. 对标题、来源、发布时间、域名、URL、正文摘要、图片 OCR 等可确定字段先提取。
6. 后续再按不同数据类型进行结构化解析，而不是在采集阶段强行解决所有表格差异。

核心原则：

- 采集层可以粗。
- 存储层不能粗。
- 使用层再细化。

## 3. 总体架构

```text
列表页 / 搜索页
  -> 候选详情页发现
  -> 粗过滤
  -> 详情页抓取
  -> 页面归档
      -> 原始页快照
      -> Markdown 文档
      -> 内容块列表
      -> 图片与 OCR 块
      -> 元数据
  -> 后续精抽任务
      -> 表格抽取
      -> 名单抽取
      -> 附件抽取
      -> 实体识别
```

采集引擎第一阶段不再假设所有目标数据都能立即变成统一表格。它先把页面可靠地保存下来，并给后续处理留下足够证据。

## 4. 三层数据存储设计

### 4.1 第一层：原始页快照

原始页快照用于审计、回放和重新解析。

建议字段：

| 字段 | 说明 |
|------|------|
| `source_url` | 当前详情页 URL |
| `entry_url` | 发现该详情页的列表页或搜索页 URL |
| `domain` | 域名，例如 `hubei.gov.cn` |
| `platform` | 来源平台，例如 `hubei_gov` |
| `subject` | 主题，例如 `数据要素` |
| `fetched_at` | 抓取时间 |
| `http_status` | HTTP 状态码，浏览器渲染时可为空 |
| `final_url` | 跳转后的最终 URL |
| `html_path` | 原始 HTML 本地路径 |
| `screenshot_path` | 可选，页面截图路径 |
| `assets_dir` | 图片、附件等资产目录 |
| `fetch_engine` | `html`、`browser` 或 `api` |
| `rendered` | 是否经过浏览器渲染 |

要求：

- 原始 HTML 必须可回放。
- 图片、附件下载后保留本地路径和原始 URL。
- 不因为结构化失败而丢弃页面。

### 4.2 第二层：Markdown 文档

Markdown 文档用于人工阅读、全文检索和后续轻量处理，目标类似 `r.jina.ai` 的页面正文转换能力。

建议字段：

| 字段 | 说明 |
|------|------|
| `markdown_path` | Markdown 文件路径 |
| `markdown` | 可选，直接内嵌 Markdown 内容 |
| `title` | 页面标题 |
| `source_name` | 来源名称 |
| `publish_time` | 发布时间 |
| `author` | 作者，若可提取 |
| `summary` | 简短摘要，可由规则截取，不使用 AI |
| `text_length` | 正文长度 |
| `image_count` | 图片数量 |
| `ocr_block_count` | OCR 块数量 |

Markdown 生成规则：

- 保留标题层级。
- 保留段落顺序。
- 保留表格原始文本或简化表格。
- 图片以 Markdown 图片语法占位。
- 图片下方插入 OCR 文本块。
- 附件以链接列表形式保留。

图片 OCR 插入示例：

```markdown
![图片 1](assets/W020260105365173215206.png)

> OCR 文本：
> 第三批湖北省高质量数据集名单
> 序号 数据集名称 数据集模态 行业领域 申报单位
> ...
```

### 4.3 第三层：内容块

内容块是后续精细化处理的基础。不能只保存一整段 Markdown，否则后续很难知道某段文字、某张图片、某个 OCR 文本来自哪里。

建议结构：

```json
{
  "blocks": [
    {
      "block_id": "b001",
      "type": "heading",
      "order": 1,
      "text": "湖北省数据局发布第三批湖北省高质量数据集",
      "level": 1,
      "source_selector": ".hbgov-article-title h1"
    },
    {
      "block_id": "b002",
      "type": "paragraph",
      "order": 2,
      "text": "近日，湖北省数据局发布...",
      "source_selector": ".hbgov-article-content"
    },
    {
      "block_id": "b003",
      "type": "image",
      "order": 3,
      "source_img_url": "https://www.hubei.gov.cn/...",
      "source_img_path": "/tmp/scraper_imgs/...",
      "alt": ""
    },
    {
      "block_id": "b004",
      "type": "ocr",
      "order": 4,
      "parent_block_id": "b003",
      "ocr_text": "第三批湖北省高质量数据集名单...",
      "ocr_status": "success",
      "manual_review_required": false
    }
  ]
}
```

块类型建议：

| 类型 | 说明 |
|------|------|
| `heading` | 标题或小标题 |
| `paragraph` | 普通正文段落 |
| `table` | HTML 表格或已识别表格 |
| `image` | 页面图片 |
| `ocr` | 图片 OCR 结果 |
| `attachment` | 附件链接 |
| `link` | 正文中的普通链接 |
| `metadata` | 页面显式元数据 |

## 5. 可先提取的确定性字段

在不做深度结构化的前提下，以下字段可以优先提取：

### 5.1 URL 与域名

| 字段 | 说明 |
|------|------|
| `source_url` | 详情页原始 URL |
| `final_url` | 渲染或跳转后的 URL |
| `domain` | 域名 |
| `site_name` | 站点名称，可由规则配置 |
| `url_path` | URL path |
| `url_hash` | URL 哈希，用于去重 |

### 5.2 页面元数据

| 字段 | 说明 |
|------|------|
| `title` | 页面标题 |
| `source_name` | 页面显示的来源 |
| `publish_time` | 发布时间 |
| `author` | 作者 |
| `channel` | 栏目名称 |
| `breadcrumb` | 面包屑路径 |
| `language` | 页面语言，默认中文 |

### 5.3 内容统计

| 字段 | 说明 |
|------|------|
| `text_length` | 纯文本长度 |
| `paragraph_count` | 段落数量 |
| `image_count` | 图片数量 |
| `attachment_count` | 附件数量 |
| `table_count` | HTML 表格数量 |
| `ocr_success_count` | OCR 成功数量 |
| `ocr_failed_count` | OCR 失败数量 |

### 5.4 质量与处理标记

| 字段 | 说明 |
|------|------|
| `archive_status` | `success`、`partial_success`、`failed` |
| `content_type` | `article`、`index`、`attachment_page`、`unknown` |
| `contains_ocr` | 是否包含 OCR |
| `contains_table` | 是否包含表格 |
| `requires_structuring` | 是否需要后续精抽 |
| `manual_review_required` | 是否需要人工复核 |
| `parse_errors` | 解析或 OCR 错误 |

## 6. 规则 DSL 改版建议

### 6.1 列表发现配置

```yaml
discovery:
  enabled: true
  mode: "list"
  entry:
    url: "https://www.hubei.gov.cn/..."
    client: "browser"
  list:
    items_path: "css:.news-list li"
    title:
      selector: "a"
      type: "text"
    detail_url:
      selector: "a"
      type: "attribute"
      attribute: "href"
    publish_time:
      selector: ".date"
      type: "text"
  filters:
    title_keywords:
      - "高质量数据集"
      - "数据集名单"
      - "数据要素"
    include_domains:
      - "hubei.gov.cn"
    max_details: 20
```

### 6.2 详情归档配置

```yaml
archive:
  enabled: true
  mode: "page_markdown"
  detail:
    client: "browser"
    wait_for_selector: ".hbgov-article-content"
  metadata:
    title:
      selector: ".hbgov-article-title h1"
      type: "text"
    source_name:
      selector: ".hbgov-article-meta-source"
      type: "text"
    publish_time:
      selector: ".hbgov-article-meta-time"
      type: "text"
    content:
      selector: ".hbgov-article-content .view"
      type: "html"
  markdown:
    enabled: true
    include_images: true
    include_links: true
    include_ocr_after_image: true
  image_ocr:
    enabled: true
    selector: ".hbgov-article-content img"
    plugin: "tesseract"
    languages:
      - "chi_sim"
      - "eng"
```

### 6.3 后续精抽配置

精抽不要求首版完全实现，但规则上预留入口：

```yaml
structuring:
  enabled: false
  strategies:
    - name: "dataset_table_from_ocr"
      applies_to:
        block_types:
          - "ocr"
        keywords:
          - "数据集名称"
          - "申报单位"
      output_collection: "dataset_rows"
```

## 7. 输出文件建议

页面归档输出不再只是一份 `data` 数组，而应保存为可审计包。改版后的主存储选择 PostgreSQL，文件目录作为资产缓存和人工复核辅助，不再作为唯一事实源。

## 7. PostgreSQL 主库存储决策

### 7.1 选型结论

页面归档改版采用 PostgreSQL 作为主库。

选型结论：

- PostgreSQL 是页面归档、块级内容、OCR 结果和结构化结果的主事实源。
- Elasticsearch 只作为后续可选全文检索索引，不作为唯一存储。
- MySQL 不作为首选主库，原因是本项目需要长期保存大量半结构化内容、块级 JSON、OCR 结构化结果和后续精抽结果，PostgreSQL 的 `jsonb`、全文检索和事务能力更适合该模型。
- 大图片、PDF、Word、Excel、ZIP、完整截图等二进制资产不强制直接写入 PostgreSQL。首版可保存本地路径，后续可切换对象存储；PostgreSQL 中保存资产元数据、哈希和 `storage_uri`。

### 7.2 入库范围

必须入库：

| 数据 | 存储方式 |
|------|----------|
| 页面元数据 | PostgreSQL 普通字段 |
| 原始 HTML | PostgreSQL `text` |
| Markdown 正文 | PostgreSQL `text` |
| 内容块 | PostgreSQL 行表 + `jsonb` 元数据 |
| 图片与附件元数据 | PostgreSQL 行表 |
| OCR 文本 | PostgreSQL `text` |
| OCR 结构化结果 | PostgreSQL `jsonb` |
| 后续精抽结果 | PostgreSQL `jsonb` |
| 任务运行状态 | PostgreSQL 行表 |

可选入库：

| 数据 | 默认策略 |
|------|----------|
| 图片二进制 | 默认不入库，保存本地文件或对象存储 URI |
| PDF、Word、Excel、ZIP | 默认不入库，保存本地文件或对象存储 URI |
| 完整页面截图 | 默认不入库，保存本地文件或对象存储 URI |

### 7.3 建议表模型

#### `archive_pages`

保存详情页归档主记录。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `uuid` | 页面归档 ID |
| `source_url` | `text` | 详情页 URL |
| `entry_url` | `text` | 列表页或搜索页 URL |
| `final_url` | `text` | 跳转后的最终 URL |
| `domain` | `text` | 域名 |
| `platform` | `text` | 来源平台 |
| `subject` | `text` | 主题 |
| `title` | `text` | 中文标题 |
| `source_name` | `text` | 页面来源 |
| `publish_time` | `timestamp with time zone` | 发布时间 |
| `author` | `text` | 作者 |
| `channel` | `text` | 栏目 |
| `breadcrumb` | `jsonb` | 面包屑 |
| `html` | `text` | 渲染后 HTML |
| `markdown` | `text` | Markdown 正文 |
| `metadata` | `jsonb` | 扩展元数据 |
| `content_hash` | `text` | 内容哈希 |
| `archive_status` | `text` | `success`、`partial_success`、`failed` |
| `contains_ocr` | `boolean` | 是否包含 OCR |
| `contains_table` | `boolean` | 是否包含表格 |
| `requires_structuring` | `boolean` | 是否需要后续精抽 |
| `manual_review_required` | `boolean` | 是否需要人工复核 |
| `fetched_at` | `timestamp with time zone` | 抓取时间 |
| `created_at` | `timestamp with time zone` | 入库时间 |
| `updated_at` | `timestamp with time zone` | 更新时间 |

#### `archive_blocks`

保存页面内容块。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `uuid` | 内容块 ID |
| `page_id` | `uuid` | 关联 `archive_pages.id` |
| `block_order` | `integer` | 页面内顺序 |
| `block_type` | `text` | `heading`、`paragraph`、`table`、`image`、`ocr`、`attachment`、`link` |
| `parent_block_id` | `uuid` | 父块，例如 OCR 块关联图片块 |
| `text` | `text` | 块文本 |
| `html` | `text` | 块级 HTML，可选 |
| `metadata` | `jsonb` | 选择器、层级、图片 URL、附件扩展名等 |
| `created_at` | `timestamp with time zone` | 入库时间 |

#### `archive_assets`

保存图片、附件、截图等资产元数据。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `uuid` | 资产 ID |
| `page_id` | `uuid` | 关联页面 |
| `block_id` | `uuid` | 关联内容块 |
| `asset_type` | `text` | `image`、`attachment`、`screenshot` |
| `source_url` | `text` | 原始 URL |
| `storage_uri` | `text` | 本地路径或对象存储 URI |
| `file_name` | `text` | 文件名 |
| `extension` | `text` | 扩展名 |
| `mime_type` | `text` | MIME 类型 |
| `size_bytes` | `bigint` | 文件大小 |
| `content_hash` | `text` | 文件哈希 |
| `downloaded` | `boolean` | 是否已下载 |
| `metadata` | `jsonb` | 图片 alt、附件文本、错误信息等 |
| `created_at` | `timestamp with time zone` | 入库时间 |

#### `ocr_results`

保存 OCR 结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `uuid` | OCR 结果 ID |
| `page_id` | `uuid` | 关联页面 |
| `asset_id` | `uuid` | 关联图片资产 |
| `block_id` | `uuid` | 关联 OCR 内容块 |
| `engine` | `text` | OCR 引擎 |
| `status` | `text` | `success`、`empty`、`unavailable` |
| `ocr_text` | `text` | OCR 原文 |
| `structured_data` | `jsonb` | 词块、网格、单元格等结构化 OCR 数据 |
| `elapsed_seconds` | `numeric` | 耗时 |
| `error` | `text` | 错误信息 |
| `manual_review_required` | `boolean` | 是否需要人工复核 |
| `created_at` | `timestamp with time zone` | 入库时间 |

#### `structured_records`

保存后续精抽结果。

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `uuid` | 结构化记录 ID |
| `page_id` | `uuid` | 关联页面 |
| `source_block_id` | `uuid` | 来源块 |
| `record_type` | `text` | 例如 `dataset_row`、`policy_item`、`attachment_item` |
| `data` | `jsonb` | 结构化业务字段 |
| `raw_columns` | `jsonb` | 原始列和值，避免丢字段 |
| `confidence` | `numeric` | 规则置信度 |
| `status` | `text` | `success`、`partial_success`、`manual_review` |
| `created_at` | `timestamp with time zone` | 入库时间 |

### 7.4 推荐索引

首版建议索引：

```sql
create unique index archive_pages_source_url_hash_idx on archive_pages (content_hash);
create index archive_pages_domain_idx on archive_pages (domain);
create index archive_pages_platform_subject_idx on archive_pages (platform, subject);
create index archive_pages_publish_time_idx on archive_pages (publish_time);
create index archive_blocks_page_order_idx on archive_blocks (page_id, block_order);
create index archive_blocks_type_idx on archive_blocks (block_type);
create index archive_assets_page_idx on archive_assets (page_id);
create index ocr_results_page_idx on ocr_results (page_id);
create index structured_records_page_type_idx on structured_records (page_id, record_type);
create index structured_records_data_gin_idx on structured_records using gin (data);
```

全文检索首版可先使用 PostgreSQL 自带全文能力，后续如搜索需求变复杂，再同步到 Elasticsearch。

## 8. 输出文件建议

数据库是主事实源，文件输出用于调试、人工复核、迁移过渡和资产缓存。页面归档输出仍可保存为可审计包，但不能替代 PostgreSQL 入库。

建议目录：

```text
output/{subject}/{platform}/{date}/{page_hash}/
  page.json
  page.html
  page.md
  blocks.json
  assets/
    image_001.png
    attachment_001.pdf
```

### 7.1 `page.json`

```json
{
  "meta": {
    "source_url": "https://www.hubei.gov.cn/...",
    "entry_url": "https://www.hubei.gov.cn/...",
    "domain": "www.hubei.gov.cn",
    "platform": "hubei_gov",
    "subject": "数据要素",
    "title": "湖北省数据局发布第三批湖北省高质量数据集",
    "source_name": "湖北省数据局",
    "publish_time": "2026-01-05",
    "fetched_at": "2026-05-21T15:30:00",
    "archive_status": "success",
    "contains_ocr": true,
    "requires_structuring": true
  },
  "paths": {
    "html": "page.html",
    "markdown": "page.md",
    "blocks": "blocks.json",
    "assets": "assets/"
  }
}
```

### 7.2 `blocks.json`

`blocks.json` 保存所有内容块，供后续结构化任务使用。

### 7.3 `page.md`

`page.md` 用于人工阅读和全文检索。

## 9. 与现有图片 OCR 能力的关系

现有图片 OCR 逐行结构化能力不废弃，但降级为后续精抽策略之一。

新关系如下：

```text
页面归档层
  -> 保存图片
  -> 保存 OCR 原文
  -> 保存 OCR 块
  -> 可选：立即尝试表格结构化

结构化层
  -> 针对 OCR 块、HTML 表格、正文段落做专门解析
  -> 产出 dataset_rows、policy_items、attachment_items 等结果集
```

对于湖北省高质量数据集名单：

- 第一阶段：归档整篇文章、两张名单图片和 OCR Markdown。
- 第二阶段：从 OCR 表格块中精抽 25 条数据集行。

这样即使第二阶段抽取失败，也不会丢失页面正文、图片和 OCR 原文。

## 10. 实施阶段

### 第一阶段：页面归档 MVP

目标：

- 从详情页生成 `page.html`、`page.md`、`blocks.json`、`page.json`。
- 支持图片下载和 OCR 块插入。
- 支持标题、来源、发布时间、域名等元数据提取。

不做：

- 不做复杂翻页。
- 不做多模板结构化。
- 不做 AI 摘要或 AI 分类。

### 第二阶段：列表发现到详情归档

目标：

- 从列表页发现详情页。
- 支持标题关键词过滤。
- 支持 URL 去重。
- 批量归档多个详情页。

### 第三阶段：后续精抽任务

目标：

- 从 `blocks.json` 中读取 OCR、HTML 表格和正文块。
- 按策略生成结构化结果集。
- 对不同表格形态保留 `raw_columns`，避免字段丢失。

### 第四阶段：控制台查看与复核

目标：

- Dashboard 中查看页面归档。
- 查看 Markdown、原始 HTML、图片、OCR 块。
- 标记是否需要人工复核。

## 11. 风险与取舍

| 风险 | 说明 | 缓解 |
|------|------|------|
| 存储量增加 | HTML、Markdown、块结构和 OCR 结果入库后会增加 PostgreSQL 存储压力 | 大二进制资产不强制入库，正文和结构化数据入库，按来源配置保留周期 |
| 后续精抽延后 | 第一阶段不保证直接得到最终业务表 | 通过 `requires_structuring` 明确后续任务 |
| Markdown 转换质量不稳定 | 政府网站 DOM 差异大 | 保留 HTML 和块结构，Markdown 只作为阅读层 |
| OCR 质量不足 | 本地 Tesseract 对中文图片仍可能误识别 | 保存图片和 OCR 原文，支持后续替换 OCR 插件重跑 |
| 规则复杂度上升 | 新增 discovery/archive/structuring 三层 | 第一版只实现 archive MVP，逐步扩展 |
| PostgreSQL 连接配置未确定 | 不同部署环境的连接参数不同 | 代码先支持环境变量和配置文件，具体连接信息后续由用户提供 |

## 12. 推荐结论

推荐将系统采集主线调整为：

```text
先归档页面，再结构化数据。
```

具体落地原则：

1. 详情页先保存为可回放资产包。
2. PostgreSQL 作为页面、块、OCR、结构化结果的主事实源。
3. Markdown 便于阅读和全文检索，但不能替代块级结构。
4. 图片 OCR 文本按原始位置插入 Markdown，同时保存独立 OCR 块。
5. 结构化结果作为后续产物，不作为采集成功的唯一标准。
6. 对异构页面保留 `raw_columns` 和原始块，避免过早丢失信息。

这条路线可以更好应对政府网站中“列表多、文章杂、详情层级不一致、表格形态不固定”的现实情况，同时为后续精抽和人工复核保留完整证据链。
