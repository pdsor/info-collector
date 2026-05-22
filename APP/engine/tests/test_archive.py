"""页面归档对象测试。"""


def test_build_archive_page_generates_meta_content_blocks_and_assets():
    """归档对象应同时包含元数据、正文、块和资产。"""
    from engine.archive import build_archive_page

    archive_page = build_archive_page(
        source_url="https://www.hubei.gov.cn/a.shtml",
        entry_url="https://www.hubei.gov.cn/list.shtml",
        final_url="https://www.hubei.gov.cn/a.shtml",
        domain="www.hubei.gov.cn",
        platform="hubei_gov",
        subject="数据要素",
        title="第三批湖北省高质量数据集名单",
        source_name="湖北省数据局",
        publish_time="2026-01-05 09:00:00",
        fetched_at="2026-05-21T15:30:00+08:00",
        html="<html><body><h1>第三批湖北省高质量数据集名单</h1></body></html>",
        markdown="# 第三批湖北省高质量数据集名单",
        blocks=[
            {
                "block_id": "b001",
                "type": "heading",
                "order": 1,
                "text": "第三批湖北省高质量数据集名单",
            },
            {
                "block_id": "b002",
                "type": "image",
                "order": 2,
                "source_url": "https://www.hubei.gov.cn/img.png",
                "storage_uri": "/tmp/scraper_imgs/x.png",
                "metadata": {"alt": "名单图片"},
            },
        ],
        assets=[
            {
                "asset_type": "image",
                "source_url": "https://www.hubei.gov.cn/img.png",
                "storage_uri": "/tmp/scraper_imgs/x.png",
                "file_name": "x.png",
                "extension": ".png",
                "mime_type": "image/png",
                "size_bytes": 12345,
                "content_hash": "abc",
                "downloaded": True,
                "metadata": {"block_id": "b002"},
            }
        ],
    )

    meta = archive_page["meta"]
    assert meta["source_url"] == "https://www.hubei.gov.cn/a.shtml"
    assert meta["domain"] == "www.hubei.gov.cn"
    assert meta["title"] == "第三批湖北省高质量数据集名单"
    assert meta["fetched_at"] == "2026-05-21T15:30:00+08:00"
    assert len(meta["content_hash"]) == 64
    assert archive_page["content"]["html"].startswith("<html>")
    assert archive_page["content"]["markdown"].startswith("# 第三批")
    assert archive_page["blocks"][0]["block_type"] == "heading"
    assert archive_page["assets"][0]["asset_type"] == "image"
    assert archive_page["paths"]["html"] == "page.html"
    assert archive_page["paths"]["markdown"] == "page.md"
    assert archive_page["paths"]["blocks"] == "blocks.json"


def test_output_manager_saves_archive_package_structure(tmp_path):
    """归档输出包应落盘页面、正文、块和资产清单。"""
    import json
    import os

    from engine.archive import build_archive_page
    from engine.output import OutputManager

    output_mgr = OutputManager(base_path=str(tmp_path))
    rule = {
        "name": "归档规则",
        "subject": "数据要素",
        "source": {"platform": "hubei_gov"},
    }
    archive_page = build_archive_page(
        source_url="https://www.hubei.gov.cn/a.shtml",
        entry_url="https://www.hubei.gov.cn/list.shtml",
        final_url="https://www.hubei.gov.cn/a.shtml",
        domain="www.hubei.gov.cn",
        platform="hubei_gov",
        subject="数据要素",
        title="第三批湖北省高质量数据集名单",
        source_name="湖北省数据局",
        publish_time="2026-01-05 09:00:00",
        fetched_at="2026-05-21T15:30:00+08:00",
        html="<html><body><h1>第三批湖北省高质量数据集名单</h1></body></html>",
        markdown="# 第三批湖北省高质量数据集名单",
        blocks=[
            {
                "block_id": "b001",
                "type": "heading",
                "order": 1,
                "text": "第三批湖北省高质量数据集名单",
            }
        ],
        assets=[
            {
                "asset_type": "image",
                "source_url": "https://www.hubei.gov.cn/img.png",
                "storage_uri": "/tmp/scraper_imgs/x.png",
                "file_name": "x.png",
                "extension": ".png",
                "mime_type": "image/png",
                "size_bytes": 12345,
                "content_hash": "abc",
                "downloaded": True,
                "metadata": {},
            }
        ],
    )

    package_dir = output_mgr.save_archive_package(archive_page, rule)

    assert os.path.isdir(package_dir)
    assert os.path.isfile(os.path.join(package_dir, "page.json"))
    assert os.path.isfile(os.path.join(package_dir, "page.html"))
    assert os.path.isfile(os.path.join(package_dir, "page.md"))
    assert os.path.isfile(os.path.join(package_dir, "blocks.json"))
    assert os.path.isfile(os.path.join(package_dir, "assets", "manifest.json"))

    with open(os.path.join(package_dir, "page.json"), encoding="utf-8") as f:
        page_json = json.load(f)
    with open(
        os.path.join(package_dir, "assets", "manifest.json"), encoding="utf-8"
    ) as f:
        asset_manifest = json.load(f)

    assert page_json["meta"]["title"] == "第三批湖北省高质量数据集名单"
    assert page_json["blocks"][0]["block_type"] == "heading"
    assert asset_manifest[0]["asset_type"] == "image"
