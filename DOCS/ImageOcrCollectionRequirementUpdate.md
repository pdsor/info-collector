# 图片内嵌数据采集能力需求更新

| 文档名称 | 图片内嵌数据采集能力需求更新 |
|----------|------------------------------|
| 文档编号 | IC-NG-REQ-OCR-001 |
| 版本号 | v0.1 |
| 发布日期 | 2026-05-15 |
| 文档状态 | 需求更新草案 |
| 适用范围 | Info Collector NG v2.2 后续功能扩展 |

## 1. 背景

当前项目以规则驱动方式采集公开网页、接口和浏览器渲染页面。现有 Rule v2 规则擅长处理 HTML 文本、JSON 接口和 DOM 结构化字段，但政务、金融、公告类网站经常将结构化表格以 PNG、JPG 图片形式嵌入页面。

典型场景包括：

- 政府招标公告附件截图。
- 政务数据集清单截图。
- 财务报表截图。
- 扫描件中的表格图片。

以湖北省政府数据集页面为例，页面中的结构化数据可能不是 DOM 文本，而是两张 PNG 图片内的 25 条表格记录。传统 CSS、XPath、JSONPath 解析无法直接提取这些记录。

## 2. 设计边界

本能力必须符合 Info Collector NG v2.2 的现有架构边界：

- 仍然以 YAML Rule v2 为规则入口。
- 仍然由 `InfoCollectorEngine` 统一调度采集、治理和输出。
- 仍然输出当前项目统一的 `meta + data` JSON 文件。
- 不接入 Agent、视觉大模型、云端 OCR 或外部 AI 服务。
- 不使用 Crawl4AI。
- OCR 必须本地运行，支持无显卡环境。
- 验证码和人机验证挑战只做识别和状态标记，不实现自动绕过。

本能力不是独立采集系统，而是现有 `html` 和 `browser` 采集链路的扩展。

## 3. 本地 OCR 选型

### 3.1 首选方案：Tesseract OCR

首版推荐使用 `Tesseract OCR + Pillow/OpenCV 轻量预处理`。

选择理由：

- 可本地离线运行。
- CPU 可用，无显卡要求。
- 依赖相对轻，适合 MVP。
- 支持中文语言包。
- 以命令行或 Python 包方式接入都比较简单。

需要的系统依赖：

```text
tesseract-ocr
tesseract-ocr-chi-sim
tesseract-ocr-eng
```

可选 Python 依赖：

```text
pytesseract
Pillow
opencv-python-headless
```

### 3.2 可选增强：PaddleOCR CPU

PaddleOCR 可作为后续增强方案，不作为首版默认方案。

适用条件：

- Tesseract 对复杂中文表格识别质量不足。
- 可以接受更大的依赖和模型文件。
- 部署环境允许安装较重的 Python 包。

不作为首版默认的原因：

- 依赖更重。
- CPU 推理速度和资源占用不稳定。
- 模型下载、版本兼容和部署复杂度高于 Tesseract。

### 3.3 不纳入本项目的方案

以下方案不纳入本能力：

- 云 OCR 服务，例如百度 OCR、阿里 OCR。
- Agent 内置视觉分析。
- 视觉大模型。
- Camofox 或其他浏览器视觉识别能力。
- 用 OCR 自动破解验证码或人机验证。

## 4. Rule v2 扩展方式

建议在 Rule v2 中新增 `image_extraction` 配置块。该配置只在 HTML 或 Browser 页面采集后触发。

示例：

```yaml
image_extraction:
  enabled: true
  trigger:
    when_empty: true
    domains:
      - "hubei.gov.cn"
    img_keywords:
      - "table"
      - "数据"
      - "附件"
  images:
    selector: "img"
    src_attribute: "src"
    include_alt: true
    max_images: 10
  download:
    dir_template: "/tmp/scraper_imgs/{task_id}"
    retries: 3
    retry_interval_seconds: 2
    timeout_seconds: 15
    max_size_mb: 5
  ocr:
    engine: "tesseract"
    languages:
      - "chi_sim"
      - "eng"
    psm: 6
    preprocess:
      grayscale: true
      threshold: true
      resize_ratio: 2
  parse:
    mode: "table"
    delimiters:
      - "|"
      - "\t"
      - ","
    column_mapping:
      序号: "id"
      数据名称: "name"
      发布时间: "publish_time"
  fallback:
    ocr_unavailable: "manual_review"
    ocr_empty: "manual_review"
    parse_failed: "semi_structured"
```

## 5. 图片模式触发条件

图片采集不是替代标准采集，而是补充链路。满足以下任一条件时触发：

| 条件 | 说明 |
|------|------|
| `image_extraction.enabled: true` 且 `trigger.when_empty: true`，标准 `extract` 结果为空 | 页面没有提取到目标字段时尝试图片采集。 |
| 页面域名命中 `trigger.domains` | 对已知图片表格站点直接启用图片候选提取。 |
| 页面 `<img>` 的 `src`、文件名或 `alt` 命中 `trigger.img_keywords` | 例如 `table`、`数据`、`附件`、`清单`。 |

默认策略：

- 标准 DOM 采集成功时，不自动进入 OCR。
- 明确命中站点或图片关键词时，即使 DOM 采集有少量结果，也可以补充 OCR 结果。
- OCR 结果需要保留来源字段，避免与 DOM 结果混淆。

## 6. 图片发现与下载

图片候选来自页面中的 `<img>` 标签。

输入：

- 当前页面 URL。
- 页面标题。
- 渲染后的 HTML。
- `image_extraction.images` 配置。

输出：

- 图片 URL。
- 绝对 URL。
- 图片本地路径。
- `alt` 文本。
- 下载状态。
- 错误信息。

下载要求：

| 项 | 要求 |
|----|------|
| URL 补全 | 支持相对路径自动补全为绝对 URL。 |
| 重试 | 默认 3 次。 |
| 间隔 | 默认 2 秒。 |
| 超时 | 默认 15 秒。 |
| 单图大小 | 默认不超过 5MB。 |
| 缓存目录 | `/tmp/scraper_imgs/{task_id}/{hash(url)}.{ext}`。 |
| 文件保留 | 采集任务结束后不删除，支持人工复核。 |

下载失败时跳过当前图片，继续处理下一张图片。

## 7. 本地 OCR 流程

OCR 模块只负责把图片转换为文本，不负责业务结构化。

输入：

- 本地图片路径。
- OCR 语言配置。
- 预处理配置。

输出：

- OCR 原始文本。
- OCR 引擎名称。
- OCR 耗时。
- OCR 状态。
- 错误信息。

推荐处理流程：

1. 检查图片文件存在且大小未超过限制。
2. 使用 Pillow 打开图片。
3. 可选放大图片。
4. 可选转灰度。
5. 可选二值化。
6. 调用 Tesseract。
7. 返回原始文本。

OCR 输出为空时，不抛弃图片记录，应标记：

```json
{
  "ocr_empty": true,
  "manual_review_required": true
}
```

## 8. OCR 文本结构化解析

结构化解析模块负责把 OCR 原始文本转为项目内的结构化记录。

输入：

- OCR 原始文本。
- `parse.delimiters`。
- `parse.column_mapping`。
- 来源页面和图片元数据。

输出：

- 多条扁平化结构化 item。
- 解析错误列表。
- 半结构化标记。

解析策略：

- 自动剔除空行。
- 优先识别表头行。
- 支持 `|`、制表符、英文逗号作为分隔符。
- 根据 `column_mapping` 把 OCR 表头映射为项目字段。
- 单行解析失败不影响其他行。
- 全部解析失败时输出半结构化记录，保留 OCR 原文。

示例映射：

```yaml
parse:
  column_mapping:
    序号: "id"
    数据名称: "name"
    发布时间: "publish_time"
```

OCR 文本：

```text
序号 | 数据名称 | 发布时间
1 | 企业登记数据集 | 2023-03-01
2 | 公共信用数据集 | 2023-03-02
```

结构化 item：

```json
[
  {
    "id": "1",
    "name": "企业登记数据集",
    "publish_time": "2023-03-01"
  },
  {
    "id": "2",
    "name": "公共信用数据集",
    "publish_time": "2023-03-02"
  }
]
```

## 9. 当前项目统一输出格式

OCR 最终结果必须匹配当前 `OutputManager` 输出格式，不能使用独立的 OCR JSON 外壳。

统一输出文件结构：

```json
{
  "meta": {
    "subject": "湖北数据集",
    "platform": "hubei_gov",
    "rule_name": "湖北省政府 - 数据集图片公告",
    "collected_at": "2026-05-15T10:00:00",
    "count": 2,
    "dedup_filtered": 0,
    "governance": {
      "item_count": 2,
      "duplicate_count": 0,
      "injection_risk_count": 0,
      "field_completeness": 1.0,
      "quality_score": 1.0,
      "status": "SUCCESS"
    }
  },
  "data": [
    {
      "id": "1",
      "name": "企业登记数据集",
      "publish_time": "2023-03-01",
      "url": "https://example.com/page",
      "source_url": "https://example.com/page",
      "source_img_url": "https://example.com/a.png",
      "source_img_path": "/tmp/scraper_imgs/task/hash.png",
      "source_img_alt": "数据集清单",
      "ocr_engine": "tesseract",
      "ocr_text": "序号 | 数据名称 | 发布时间\n1 | 企业登记数据集 | 2023-03-01",
      "ocr_empty": false,
      "semi_structured": false,
      "manual_review_required": false,
      "parse_errors": [],
      "_governance": {
        "content_hash": "hash",
        "field_completeness": 1.0,
        "injection_risk": false
      }
    },
    {
      "id": "2",
      "name": "公共信用数据集",
      "publish_time": "2023-03-02",
      "url": "https://example.com/page",
      "source_url": "https://example.com/page",
      "source_img_url": "https://example.com/a.png",
      "source_img_path": "/tmp/scraper_imgs/task/hash.png",
      "source_img_alt": "数据集清单",
      "ocr_engine": "tesseract",
      "ocr_text": "序号 | 数据名称 | 发布时间\n2 | 公共信用数据集 | 2023-03-02",
      "ocr_empty": false,
      "semi_structured": false,
      "manual_review_required": false,
      "parse_errors": [],
      "_governance": {
        "content_hash": "hash",
        "field_completeness": 1.0,
        "injection_risk": false
      }
    }
  ]
}
```

关键约束：

- `data` 中每个对象是一条结构化记录。
- 一张图片识别出多行表格时，必须展开为多条 `data` 记录。
- `structured`、`raw_text` 这类 OCR 专用外壳不能作为最终输出根结构。
- OCR 中间信息应作为单条记录字段保存，例如 `ocr_text`、`source_img_path`。
- 记录必须继续进入 `GovernancePipeline`，追加 `_governance`。
- `output.fields` 继续声明目标字段和治理默认必填字段，但当前保存逻辑不会按字段列表裁剪 item。

## 10. 字段落点与程序读取约定

OCR 解析出的业务字段必须落在 `data` 数组中每条记录的顶层。后续程序读取 OCR 结果时，不读取 `ocr_text` 再二次解析，也不读取嵌套的 `structured` 字段，而是直接读取规则定义好的业务字段。

例如文章图片里包含三个字段：

```text
项目名称：智慧园区数据治理平台
申报单位：某某科技有限公司
所属行业：软件和信息技术服务业
```

规则应通过 `image_extraction.parse.column_mapping` 定义 OCR 字段到项目字段的映射：

```yaml
image_extraction:
  parse:
    mode: "key_value"
    column_mapping:
      项目名称: "project_name"
      申报单位: "applicant_unit"
      所属行业: "industry"

output:
  fields:
    - "project_name"
    - "applicant_unit"
    - "industry"
    - "url"
    - "source_img_url"
    - "ocr_engine"
```

最终写入 `data` 的记录应为：

```json
{
  "project_name": "智慧园区数据治理平台",
  "applicant_unit": "某某科技有限公司",
  "industry": "软件和信息技术服务业",
  "url": "https://example.com/article/123",
  "source_url": "https://example.com/article/123",
  "source_img_url": "https://example.com/upload/table.png",
  "source_img_path": "/tmp/scraper_imgs/task/hash.png",
  "ocr_engine": "tesseract",
  "ocr_text": "项目名称：智慧园区数据治理平台\n申报单位：某某科技有限公司\n所属行业：软件和信息技术服务业",
  "ocr_empty": false,
  "semi_structured": false,
  "manual_review_required": false,
  "parse_errors": []
}
```

后续程序读取方式：

```python
project_name = item["project_name"]
applicant_unit = item["applicant_unit"]
industry = item["industry"]
```

字段职责：

| 配置或字段 | 职责 |
|------------|------|
| `image_extraction.parse.column_mapping` | 定义 OCR 原始字段名到最终 JSON 字段名的映射。 |
| `output.fields` | 声明规则期望输出的字段，并作为治理默认必填字段来源。 |
| `data[*].project_name` 等业务字段 | 后续程序稳定读取的结构化字段。 |
| `ocr_text` | OCR 原始文本或当前记录关联文本，仅用于审计和人工复核。 |
| `source_img_url`、`source_img_path` | 图片来源审计字段，不作为业务字段读取入口。 |

## 11. 推荐字段规范

OCR 表格记录应优先输出业务字段，再补充审计字段。

推荐业务字段：

| 字段 | 说明 |
|------|------|
| `id` | 表格序号或稳定编号。 |
| `name` | 数据名称、公告名称或条目名称。 |
| `title` | 当页面语义更适合标题时使用。 |
| `publish_time` | 发布时间。 |
| `department` | 发布部门。 |
| `category` | 分类。 |
| `url` | 页面 URL 或详情 URL，用于当前项目去重和 `combined_latest.json` 汇总。 |

推荐审计字段：

| 字段 | 说明 |
|------|------|
| `source_url` | 来源页面 URL。 |
| `source_img_url` | 图片原始 URL。 |
| `source_img_path` | 图片本地缓存路径。 |
| `source_img_alt` | 图片 `alt` 文本。 |
| `ocr_engine` | OCR 引擎名称，例如 `tesseract`。 |
| `ocr_text` | 当前记录关联的 OCR 原文或行文本。 |
| `ocr_empty` | OCR 结果是否为空。 |
| `semi_structured` | 是否为半结构化兜底结果。 |
| `manual_review_required` | 是否需要人工复核。 |
| `parse_errors` | 当前图片或当前行的解析错误。 |

## 12. 治理和去重要求

OCR 结果必须进入现有治理流程：

- 清洗 HTML 标签和控制字符。
- 检测提示注入风险文本。
- 计算内容哈希。
- 计算字段完整率。
- 生成质量分。

OCR 规则应配置必填字段：

```yaml
governance:
  sanitize: true
  dedup: hash
  required_fields:
    - "name"
    - "url"
  min_completeness: 0.8
```

去重建议：

- `url` 默认使用来源页面 URL。
- 如果每条 OCR 记录没有独立详情 URL，应生成稳定 `raw_id`，例如 `{source_img_hash}_{row_index}`。
- 对同一图片重复识别出的相同行，使用治理阶段 `dedup: hash` 去重。

## 13. 异常与降级

| 场景 | 处理策略 |
|------|----------|
| 图片下载失败 | 记录失败日志，跳过当前图片，继续处理下一张。 |
| OCR 命令不可用 | 记录 `manual_review_required: true`，输出图片元数据。 |
| OCR 结果为空 | 记录 `ocr_empty: true`，进入人工复核。 |
| 部分行解析失败 | 成功行正常输出，失败行写入 `parse_errors`。 |
| 全部行解析失败 | 输出一条半结构化记录，保留 `ocr_text`，标记 `semi_structured: true`。 |
| 图片疑似验证码或人机验证 | 标记 `blocked_by_verification: true`，不自动破解。 |

半结构化兜底记录示例：

```json
{
  "title": "OCR 半结构化结果",
  "url": "https://example.com/page",
  "source_url": "https://example.com/page",
  "source_img_url": "https://example.com/a.png",
  "source_img_path": "/tmp/scraper_imgs/task/hash.png",
  "ocr_engine": "tesseract",
  "ocr_text": "无法稳定拆分的 OCR 原文",
  "ocr_empty": false,
  "semi_structured": true,
  "manual_review_required": true,
  "parse_errors": ["未识别到表头或列数不一致"]
}
```

## 14. Dashboard 和试采要求

Rule Center 的试采能力需要支持图片采集预览：

- 显示图片候选数量。
- 显示下载成功、失败、跳过数量。
- 显示 OCR 引擎和耗时。
- 显示解析出的 `data` 记录。
- 显示 `ocr_empty`、`semi_structured`、`manual_review_required`。
- 试采不写正式输出、不写去重库，但可以写入 `/tmp/scraper_imgs` 供复核。

治理中心应能继续读取 `meta.governance`，不需要为 OCR 单独定义另一套治理摘要。

## 15. 示例 Rule v2

```yaml
rule_id: "hubei-data-image-datasets"
source_id: "hubei-gov-dataset-page"
version: 1
status: TESTING
name: "湖北省政府 - 数据集图片公告"
subject: "湖北数据集"
description: "从湖北省政府页面采集图片内嵌的数据集清单"
enabled: true

source:
  platform: "hubei_gov"
  subject: "湖北数据集"
  type: "browser"
  client: "browser"
  url: "https://example.hubei.gov.cn/dataset-page"

render:
  headless: true
  stealth: true
  wait_for_selector: "img"
  wait_for_timeout: 5000

list:
  items_path: "css:.dataset-list"

extract:
  title:
    selector: ".dataset-title"
    type: "text"

image_extraction:
  enabled: true
  trigger:
    when_empty: true
    domains:
      - "hubei.gov.cn"
    img_keywords:
      - "table"
      - "数据"
      - "附件"
      - "清单"
  images:
    selector: "img"
    src_attribute: "src"
    include_alt: true
    max_images: 10
  download:
    dir_template: "/tmp/scraper_imgs/{task_id}"
    retries: 3
    retry_interval_seconds: 2
    timeout_seconds: 15
    max_size_mb: 5
  ocr:
    engine: "tesseract"
    languages:
      - "chi_sim"
      - "eng"
    psm: 6
    preprocess:
      grayscale: true
      threshold: true
      resize_ratio: 2
  parse:
    mode: "table"
    delimiters:
      - "|"
      - "\t"
      - ","
    column_mapping:
      序号: "id"
      数据名称: "name"
      发布时间: "publish_time"
      发布部门: "department"
  fallback:
    ocr_unavailable: "manual_review"
    ocr_empty: "manual_review"
    parse_failed: "semi_structured"

dedup:
  incremental: true

governance:
  sanitize: true
  dedup: hash
  required_fields:
    - "name"
    - "url"
  min_completeness: 0.8

output:
  fields:
    - "id"
    - "name"
    - "publish_time"
    - "department"
    - "url"
    - "source_img_url"
    - "source_img_path"
    - "ocr_engine"
    - "ocr_empty"
    - "semi_structured"
    - "manual_review_required"
  save_raw: false
  filename_template: "hubei_data_image_datasets_{date}.json"
```

## 16. 分阶段实施建议

### 16.1 阶段一：本地最小闭环

目标：

- 支持图片候选发现。
- 支持图片下载缓存。
- 支持 Tesseract 本地 OCR。
- 支持简单表格文本解析。
- 输出符合当前项目 `meta + data` 格式。
- 支持 Rule Center 试采预览。

不包含：

- PaddleOCR。
- 复杂表格版面恢复。
- 图片旋转、倾斜校正。
- 验证码自动处理。

### 16.2 阶段二：质量增强

目标：

- 增加更细的图片预处理策略。
- 增加 OCR 置信度字段。
- 增加列数不一致修复策略。
- 增加 Dashboard 人工复核入口。

### 16.3 阶段三：可选 OCR 引擎扩展

目标：

- 增加 PaddleOCR CPU 适配器。
- 允许规则按站点选择 OCR 引擎。
- 增加 OCR 引擎健康检查。

## 17. 验收标准

首版验收标准：

- 给定包含两张表格图片的页面，能够下载图片到 `/tmp/scraper_imgs/{task_id}`。
- 本地 Tesseract 可用时，能够识别图片文本。
- OCR 表格文本能够按 `column_mapping` 输出多条 `data` 记录。
- 最终输出 JSON 符合当前 `OutputManager` 的 `meta + data` 结构。
- 每条 OCR 记录包含来源图片和 OCR 审计字段。
- OCR 不可用时不阻塞任务，输出人工复核记录。
- Rule Center 试采能展示 OCR 解析结果。
- 相关结果进入现有治理流程，生成 `_governance` 和 `meta.governance`。
