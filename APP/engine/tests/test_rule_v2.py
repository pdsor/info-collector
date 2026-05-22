"""Rule v2 DSL 兼容测试。"""


def test_rule_parser_accepts_minimal_rule_v2():
    """Rule v2 最小结构可以通过校验。"""
    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "source_id": "1a2b3c",
        "version": 2,
        "status": "PRODUCTION",
        "source": {"type": "html", "platform": "example", "url": "https://example.com"},
        "list": {"items_path": "css:article"},
        "extract": {
            "title": {"selector": "h1", "type": "text"},
            "url": {"selector": "a", "type": "attribute", "attribute": "href"},
        },
        "governance": {"dedup": "none", "sanitize": True},
        "output": {"fields": ["title", "url"], "save_raw": False},
    }

    assert RuleParser().validate(rule) is True


def test_rule_parser_rejects_rule_v2_without_structured_extract():
    """Rule v2 必须声明结构化提取字段。"""
    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "source_id": "1a2b3c",
        "version": 2,
        "source": {"type": "html", "platform": "example", "url": "https://example.com"},
        "list": {"items_path": "css:article"},
        "extract": {},
    }

    try:
        RuleParser().validate(rule)
    except ValueError as exc:
        assert "extract" in str(exc)
    else:
        raise AssertionError("缺少 extract 时必须校验失败")


def test_engine_extracts_rule_v2_fields_from_html(monkeypatch):
    """Rule v2 extract 字段应能从列表元素中提取结构化数据。"""
    from engine.engine import InfoCollectorEngine

    html = """
    <html><body>
      <article><h1>标题一</h1><a href="/a">详情</a><time>2026-05-14</time></article>
      <article><h1>标题二</h1><a href="/b">详情</a><time>2026-05-15</time></article>
    </body></html>
    """
    rule = {
        "rule_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        "source_id": "1a2b3c",
        "version": 2,
        "source": {"type": "html", "platform": "example", "url": "https://example.com"},
        "list": {"items_path": "css:article"},
        "extract": {
            "title": {"selector": "h1", "type": "text"},
            "url": {"selector": "a", "type": "attribute", "attribute": "href"},
            "publish_time": {"selector": "time", "type": "text"},
        },
        "output": {"fields": ["title", "url", "publish_time"]},
    }
    engine = InfoCollectorEngine(dedup_db_path=":memory:")
    monkeypatch.setattr(engine.html_crawler, "fetch", lambda *args, **kwargs: html)

    items = engine.crawl(rule)

    assert items == [
        {"title": "标题一", "url": "/a", "publish_time": "2026-05-14"},
        {"title": "标题二", "url": "/b", "publish_time": "2026-05-15"},
    ]


def test_rule_parser_accepts_local_registered_ocr_plugin():
    """Rule v2 允许本地已注册 OCR 插件配置。"""
    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "ocr-rule",
        "source_id": "ocr-source",
        "version": 1,
        "source": {"type": "html", "platform": "hubei_gov", "url": "https://www.hubei.gov.cn/a.shtml"},
        "list": {"items_path": "css:article"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "image_extraction": {
            "enabled": True,
            "images": {"selector": "img"},
            "ocr": {"plugin": "tesseract", "languages": ["chi_sim", "eng"]},
            "parse": {"mode": "table", "column_mapping": {"序号": "id"}},
        },
    }

    assert RuleParser().validate(rule) is True


def test_rule_parser_keeps_engine_field_compatibility_for_tesseract():
    """Rule v2 兼容旧 engine 字段指定 Tesseract。"""
    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "ocr-rule",
        "source_id": "ocr-source",
        "version": 1,
        "source": {"type": "html", "platform": "hubei_gov", "url": "https://www.hubei.gov.cn/a.shtml"},
        "list": {"items_path": "css:article"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "image_extraction": {"enabled": True, "ocr": {"engine": "tesseract"}},
    }

    assert RuleParser().validate(rule) is True


def test_rule_parser_rejects_cloud_or_ai_ocr_config():
    """Rule v2 禁止云 OCR 或 AI/视觉模型 OCR 配置。"""
    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "ocr-rule",
        "source_id": "ocr-source",
        "version": 1,
        "source": {"type": "html", "platform": "hubei_gov", "url": "https://www.hubei.gov.cn/a.shtml"},
        "list": {"items_path": "css:article"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "image_extraction": {"enabled": True, "ocr": {"plugin": "vision_model", "api_key": "secret"}},
    }

    try:
        RuleParser().validate(rule)
    except ValueError as exc:
        assert "image_extraction" in str(exc)
    else:
        raise AssertionError("AI 或云 OCR 配置必须校验失败")


def test_rule_parser_accepts_archive_discovery_and_structuring_blocks():
    """Rule v2 允许页面归档相关配置块。"""
    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "archive-rule",
        "source_id": "archive-source",
        "version": 2,
        "source": {"type": "html", "platform": "example", "url": "https://example.com"},
        "list": {"items_path": "css:article"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "discovery": {
            "enabled": True,
            "list_selector": "article",
            "list": {
                "items_path": "css:article",
                "detail_url": {"selector": "a", "attribute": "href"},
            },
        },
        "archive": {
            "enabled": True,
            "markdown": {"enabled": True},
            "image_ocr": {
                "enabled": True,
                "images": {"selector": "img"},
                "ocr": {"plugin": "tesseract", "languages": ["chi_sim"]},
            },
        },
        "structuring": {"enabled": True, "strategy": "schema"},
    }

    assert RuleParser().validate(rule) is True


def test_rule_parser_accepts_disabled_structuring_block():
    """Rule v2 允许先声明关闭精抽。"""
    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "archive-rule",
        "source_id": "archive-source",
        "version": 2,
        "source": {"type": "html", "platform": "example", "url": "https://example.com"},
        "list": {"items_path": "css:article"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "structuring": {"enabled": False},
    }

    assert RuleParser().validate(rule) is True


def test_rule_parser_rejects_forbidden_archive_and_structuring_config():
    """Rule v2 页面归档配置仍禁止 AI、Agent、云 OCR 和 crawl4ai。"""
    from engine.rule_parser import RuleParser

    base_rule = {
        "rule_id": "archive-rule",
        "source_id": "archive-source",
        "version": 2,
        "source": {"type": "html", "platform": "example", "url": "https://example.com"},
        "list": {"items_path": "css:article"},
        "extract": {"title": {"selector": "h1", "type": "text"}},
    }
    forbidden_configs = [
        {"archive": {"enabled": True, "image_ocr": {"enabled": True, "ocr": {"cloud_ocr": "baidu"}}}},
        {"archive": {"enabled": True, "image_ocr": {"enabled": True, "ocr": {"api_key": "secret"}}}},
        {"structuring": {"enabled": True, "llm": {"model": "gpt-4o-mini"}}},
        {"discovery": {"enabled": True, "agent": {"name": "browser-agent"}}},
        {"discovery": {"enabled": True, "client": "crawl4ai"}},
    ]

    for config in forbidden_configs:
        rule = {**base_rule, **config}
        try:
            RuleParser().validate(rule)
        except ValueError as exc:
            message = str(exc)
            assert (
                "AI" in message
                or "Agent" in message
                or "OCR" in message
                or "crawl4ai" in message
                or "Crawl4AI" in message
            )
        else:
            raise AssertionError(f"非法配置必须校验失败: {config}")


def test_rule_parser_requires_discovery_list_when_enabled():
    """discovery.enabled=true 必须提供 list.items_path 与 list.detail_url。"""
    import pytest

    from engine.rule_parser import RuleParser

    rule = {
        "rule_id": "discovery-bad",
        "source_id": "discovery-bad-source",
        "version": 1,
        "extract": {"title": {"selector": "h1", "type": "text"}},
        "source": {"type": "html", "platform": "x", "url": "https://x/list"},
        "discovery": {"enabled": True, "list": {}},
        "archive": {"enabled": True},
    }
    with pytest.raises(ValueError, match="discovery.list"):
        RuleParser().validate(rule)
