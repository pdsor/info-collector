# 图片 OCR 表格逐行采集设计

## 目标

让图片承载的表格数据可以按业务行输出结构化记录。以湖北省政府“第三批湖北省高质量数据集名单”为当前验收样例，最终输出应是图片表格中的每一条数据集记录，而不是“一篇正文 + 每张图片一条 OCR 原文”。

## 范围

- 支持一篇文章中的多张表格图片合并采集。
- 支持单张图片 OCR 后拆成多条业务记录。
- 支持图片表格采集模式下只输出 OCR 表格行，不保留正文文章记录。
- 保留 OCR 原文、图片地址、图片本地路径、OCR 状态和人工复核标记，便于审计。
- 第一版只处理确定性规则和本地 OCR 结果，不接入外部 AI、视觉模型或云 OCR。

## 核心边界

文章正文抽取和图片 OCR 抽取按规则目标互斥：

- 如果目标数据在正文中，规则不启用 OCR，直接按正文选择器输出结构化数据。
- 如果目标数据在正文图片中，规则启用图片 OCR，并在行输出模式下丢弃正文文章记录。
- 不把正文记录与图片记录叠加为同一批业务输出，避免正文说明文字污染数据集清单。

## 规则设计

在 `image_extraction` 中增加显式输出模式：

```yaml
image_extraction:
  enabled: true
  output_mode: "ocr_rows_only"
```

`output_mode` 首版支持：

- `append`：兼容现有行为，在正文记录后追加 OCR 记录。
- `ocr_rows_only`：只输出图片 OCR 拆出的结构化行，正文记录不进入最终结果。

湖北规则应使用 `ocr_rows_only`，因为验收目标是“第三批湖北省高质量数据集名单”的逐行数据。

## 数据流

采集流程保持在现有引擎内完成：

1. `InfoCollectorEngine` 抓取文章页面 HTML。
2. 常规 `extract` 仍可提取标题、发布时间、来源等页面上下文。
3. `ImageExtractionRunner` 发现正文中的图片并下载。
4. OCR 插件识别每张图片。
5. `image_parser.py` 将 OCR 文本解析为多条业务记录。
6. `image_extraction.py` 给每条业务记录补充 `source_url`、`source_img_url`、`source_img_path`、`ocr_status`、`ocr_text` 等审计字段。
7. `ocr_rows_only` 模式下，引擎只返回 OCR 业务行。
8. 治理管道和输出文件继续使用现有 `meta + data` 结构。

## 解析策略

现有解析器只支持带明确分隔符的文本，例如 `序号 | 数据名称 | 申报单位`。真实 Tesseract 输出常见问题是列错位、空格不稳定、中文列名识别错误。因此第一版增加一个面向名单表格的确定性解析策略：

- 优先使用现有分隔符表格解析，保持兼容。
- 当分隔符解析失败时，进入宽松行解析。
- 宽松行解析以行首序号作为新记录边界，例如 `1`、`13`、`25`。
- 每条记录至少要识别出 `id` 和 `name`，否则标记为 `manual_review_required`。
- 对于跨行 OCR 文本，将同一序号后的连续行合并为当前记录的 `ocr_text`。
- 能稳定识别的字段先输出：`id`、`name`、`category`、`department`。
- 不能稳定拆出的内容保留在 `ocr_text`，不强行猜测字段。

这不是通用表格识别引擎，而是先满足当前政府名单类图片表格的确定性输出。

## 输出结构

每条数据集记录至少包含：

```json
{
  "id": "1",
  "name": "数据集名称",
  "category": "所属领域",
  "department": "申报单位",
  "source_url": "https://www.hubei.gov.cn/...",
  "source_img_url": "https://www.hubei.gov.cn/...png",
  "source_img_path": "/tmp/scraper_imgs/...png",
  "ocr_plugin": "tesseract",
  "ocr_engine": "tesseract",
  "ocr_status": "success",
  "ocr_text": "该行 OCR 原文",
  "manual_review_required": false,
  "semi_structured": false,
  "parse_errors": []
}
```

当字段不完整但能定位为一条表格行时，仍输出记录，并设置：

```json
{
  "manual_review_required": true,
  "semi_structured": true,
  "parse_errors": ["字段不完整"]
}
```

## 错误处理

- OCR 不可用：不输出伪业务行，返回人工复核记录，状态为 `unavailable`。
- OCR 为空：不输出伪业务行，返回人工复核记录，状态为 `empty`。
- 图片下载失败：记录到 OCR 摘要错误列表，不中断整篇文章其他图片。
- 部分图片解析成功、部分失败：成功记录正常输出，失败图片输出人工复核记录。
- 所有图片都无法解析为业务行：输出人工复核记录，避免静默返回 0 条。

## 验收标准

- 湖北规则运行后，输出文件 `data` 中不再包含正文文章记录。
- 湖北规则运行后，输出条数应接近名单实际行数，目标为 25 条业务记录；如果 OCR 质量导致个别行字段不完整，应通过 `manual_review_required` 标记出来。
- 每条记录必须能追溯到来源文章和来源图片。
- 控制台或返回结果应能看到输出文件路径，便于定位明细。
- 现有分隔符表格解析、空 OCR 降级、插件注册测试继续通过。

## 测试策略

- 给 `image_parser.py` 增加真实 Tesseract 风格文本样例，验证能按序号拆成多条记录。
- 给 `image_extraction.py` 增加多图片样例，验证两张图片的行记录可以合并输出。
- 给 `InfoCollectorEngine` 增加 `ocr_rows_only` 测试，验证正文记录被过滤。
- 给 CLI 增加摘要测试，验证 `--format=json` 返回 `output_path`。
- 保留现有 OCR 降级测试，防止 Tesseract 不可用时整条任务失败。

## 非目标

- 不实现通用版面分析。
- 不引入 AI 或外部 OCR 服务。
- 不把图片表格行写入数据库新表。
- 不改 Dashboard 的整体信息架构。
- 不保证所有政府图片表格一次性全自动完美结构化；低置信或字段不完整的数据必须进入人工复核。
