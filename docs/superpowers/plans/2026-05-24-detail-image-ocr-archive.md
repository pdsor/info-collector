# 详情页图片抓取 + OCR 块入库切片

> **面向代理工作者：** 推荐 `superpowers:subagent-driven-development`。步骤使用复选框（`- [ ]`）跟踪。

**目标：** 在「discovery → 详情 → 归档」最小闭环之上，让详情页归档同时包含图片资产与 OCR 块。当 `archive.image_ocr.enabled=true` 时，从详情 HTML 中按选择器发现图片、下载、跑 OCR 插件、把 `image` + `ocr` block 追加到归档的 `blocks` 列表，并把图片落到 `assets`（`storage_uri` 为本地缓存路径）。Markdown 文本暂仍交给 `build_archive_page`（首版可为空字符串）。

**架构：** 复用 `ImageExtractionRunner.discover_images/download_image` 和 `ocr_plugins.get_ocr_plugin`，但**不**经过 `_append_image_extraction_items`（那条路径会把 OCR 结果转成采集 items，与归档无关）。在 `engine.py` 新增 `_extract_detail_assets_and_ocr()`，由 `_archive_after_pipeline()` 在拿到 `detail_html` 之后调用，把 `image` block / `ocr` block / `assets` 三者一并产出后透传给 `_maybe_archive_page()`。

**技术栈：** 现有 `ImageExtractionRunner`、`get_ocr_plugin("tesseract")`、`parsel.Selector`、`build_archive_page`、pytest with monkeypatch。

---

## 范围

**必须做：**
- 详情 HTML 中按 `archive.image_ocr.images.selector`（或默认 `img`）发现图片。
- 下载图片到本地缓存（复用 `ImageExtractionRunner.download_image`）。
- 调用 `archive.image_ocr.ocr.plugin` 指定的本地 OCR 插件，得到 `OcrResult`。
- 产出 `image` block + `ocr` block（`parent_block_id` 指向 image block），追加在 detail blocks 之后。
- 产出 `assets` 列表，每个图片一项，`asset_type="image"`、`storage_uri=本地路径`、`source_url=图片URL`、`block_id=image block id`。
- 单个图片失败不影响归档：跳过该图片，记入 errors 摘要，继续处理后续图片。

**明确不做：**
- 不做 Markdown 文档渲染（`markdown=""` 保留）。
- 不做附件 / PDF 抓取。
- 不做 OCR 行级精抽（`structured_records`）。
- 不连真实 PostgreSQL。
- 不改 `archive.py`、`archive_store.py`、`output.py` 签名。

---

## 文件结构

- 修改：`APP/engine/engine/engine.py`
  - 新增 `_extract_detail_assets_and_ocr(rule, detail_html, detail_url, next_block_index) -> (blocks, assets)`。
  - 在 `_archive_after_pipeline` 的 discovery 分支里，detail 抓取完后调用上面这个方法，把返回的 blocks/assets 与 `_extract_detail_blocks` 输出合并后透传给 `_maybe_archive_page`。
- 新增：`APP/engine/tests/test_archive_detail_images.py`
  - 四个用例：
    1. `image_ocr` 未启用或未配置 → 归档不含 image/ocr block，与上一切片完全一致。
    2. `image_ocr.enabled=true` 且能匹配图片 → 归档 `blocks` 末尾包含 1 个 `image` block + 1 个 `ocr` block，`assets` 含 1 项，`ocr` block 的 `parent_block_id` == image block id。
    3. 图片下载失败 → 任务不崩，归档跳过该图片，仍然成功；`ocr_results` 不包含失败条目。
    4. OCR 插件返回 `status=success` 但 `text=""` → 归档仍包含 image block，但 `ocr` block 的 `ocr_text==""` 且 `manual_review_required=True` 落到 meta 上下文（首版仅断言 block 存在，状态字段附在 block metadata）。
- 不修改：`engine/archive.py`、`engine/archive_store.py`、`engine/output.py`、`engine/image_extraction.py`。

---

## 任务 1：失败测试

**文件：**
- 新增：`APP/engine/tests/test_archive_detail_images.py`

测试公共桩：
- monkeypatch `engine.engine.ArchiveStore.from_rule` → `_RecordingStore`。
- monkeypatch `engine.output_mgr.save_archive_package` → tmp_path 返回。
- monkeypatch `engine.html_crawler.fetch` 按 URL 后缀返回 list HTML / detail HTML。
- monkeypatch `engine.engine.ImageExtractionRunner` 或更靠下层：直接 monkeypatch `_extract_detail_assets_and_ocr` 调用到的 `download_image` 与 `get_ocr_plugin` —— 优选后者，因为新方法本来就是为了不依赖网络下载。具体在实现步骤里：把 `_extract_detail_assets_and_ocr` 写成调用 module 级 `_download_image_for_archive` 与 `get_ocr_plugin`，测试 monkeypatch 这两个符号。

预期：实现到位前 3 个 success 用例失败。

## 任务 2：实现

- [ ] **步骤 1：在 `engine.py` 中加 helper**

```python
def _extract_detail_assets_and_ocr(
    self, rule: dict, detail_html: str, detail_url: str, next_index: int
) -> tuple[list[dict], list[dict]]:
    cfg = (rule.get("archive") or {}).get("image_ocr") or {}
    if not cfg.get("enabled"):
        return [], []
    images_cfg = cfg.get("images") or {}
    selector_text = images_cfg.get("selector") or "img"
    src_attr = images_cfg.get("src_attribute") or "src"
    max_images = int(images_cfg.get("max_images") or 10)

    selector = parsel.Selector(text=detail_html or "")
    blocks: list[dict] = []
    assets: list[dict] = []
    plugin_name = (cfg.get("ocr") or {}).get("plugin") or "tesseract"

    for idx, node in enumerate(selector.css(selector_text)[:max_images]):
        src = node.attrib.get(src_attr, "").strip()
        if not src:
            continue
        absolute = urljoin(detail_url, src)
        image_block_id = f"b{next_index}"
        next_index += 1
        try:
            local_path = _download_image_for_archive(absolute, cfg)
        except Exception as exc:  # 单图失败跳过
            continue
        ocr_block_id = f"b{next_index}"
        next_index += 1
        try:
            ocr_result = get_ocr_plugin(plugin_name).recognize(local_path, cfg.get("ocr") or {})
            ocr_text = ocr_result.text or ""
            manual = ocr_result.manual_review_required
        except Exception:
            ocr_text = ""
            manual = True

        blocks.append({
            "block_id": image_block_id,
            "type": "image",
            "order": next_index - 2,
            "source_url": absolute,
            "storage_uri": local_path,
        })
        blocks.append({
            "block_id": ocr_block_id,
            "type": "ocr",
            "order": next_index - 1,
            "parent_block_id": image_block_id,
            "ocr_text": ocr_text,
            "manual_review_required": manual,
        })
        assets.append({
            "id": image_block_id,
            "block_id": image_block_id,
            "asset_type": "image",
            "source_url": absolute,
            "storage_uri": local_path,
        })
    return blocks, assets
```

`_download_image_for_archive(url, cfg)` 是 module 级函数，内部走 `ImageExtractionRunner({"image_extraction": {"download": cfg.get("download") or {}}}).download_image(url)` —— 复用既有重试 / 大小限制 / 缓存目录逻辑。

- [ ] **步骤 2：接入 `_archive_after_pipeline`**

discovery 分支内拿到 `detail_html` 后：

```python
title, blocks = self._extract_detail_blocks(rule, detail_html)
extra_blocks, assets = self._extract_detail_assets_and_ocr(
    rule, detail_html, candidate["detail_url"], next_index=len(blocks) + 1
)
blocks.extend(extra_blocks)
return self._maybe_archive_page(
    rule, items, html=None,
    detail_url=candidate["detail_url"],
    detail_html=detail_html,
    detail_title=title or candidate["title"],
    detail_blocks=blocks,
    detail_assets=assets,
)
```

- [ ] **步骤 3：回归与提交**

```bash
.venv/bin/python -m pytest tests/test_archive.py tests/test_archive_store.py tests/test_archive_engine.py tests/test_archive_discovery.py tests/test_archive_detail_images.py tests/test_rule_v2.py tests/test_integration.py -q
```

预期：全部通过。提交信息：`详情页图片与OCR块入库`。

---

## 验收标准

- `archive.image_ocr` 未启用 → 行为与上一切片完全一致。
- 启用且匹配到图片 → 归档对象 `blocks` 末尾追加 image + ocr 成对块；`assets` 包含图片，`asset_type=image`、`storage_uri` 非空；`build_archive_page` 自动把 `contains_ocr` 置为 True。
- 单图失败不影响整体归档；OCR 插件抛错时该图片仍写 image block，对应 ocr block `ocr_text=""`、`manual_review_required=True`。
- 不依赖真实下载与真实 Tesseract（测试 monkeypatch `_download_image_for_archive` 与 `get_ocr_plugin`）。
