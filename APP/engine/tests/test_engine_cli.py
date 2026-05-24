"""引擎命令行测试。"""

import json

from click.testing import CliRunner

from engine_cli import cli


def test_run_rule_json_includes_output_path(monkeypatch):
    """run-rule JSON 摘要应返回输出文件路径，便于定位明细。"""
    class FakeEngine:
        def run(self, rule_path, event_handler=None, include_data=False):
            assert include_data is False
            return {
                "status": "success",
                "total_collected": 2,
                "dedup_filtered": 0,
                "collected": 2,
                "duration": 1.23,
                "output_path": "/tmp/output/data.json",
            }

        def close(self):
            return None

    monkeypatch.setattr("engine_cli._engine", lambda: FakeEngine())
    monkeypatch.setattr("engine_cli._resolve_rule_path", lambda rule_path: rule_path)

    result = CliRunner().invoke(cli, ["run-rule", "rules/demo.yaml", "--format=json"])

    assert result.exit_code == 0
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["success"] is True
    assert payload["output_path"] == "/tmp/output/data.json"
    assert "raw_data" not in payload
    assert "deduped_data" not in payload


def test_run_rule_json_can_print_raw_and_deduped_data(monkeypatch):
    """run-rule JSON 可按参数返回去重前和去重后明细。"""
    class FakeEngine:
        def run(self, rule_path, event_handler=None, include_data=False):
            assert include_data is True
            return {
                "status": "success",
                "total_collected": 2,
                "dedup_filtered": 1,
                "collected": 1,
                "duration": 1.23,
                "output_path": "/tmp/output/data.json",
                "raw_data": [{"id": "1"}, {"id": "1"}],
                "deduped_data": [{"id": "1"}],
            }

        def close(self):
            return None

    monkeypatch.setattr("engine_cli._engine", lambda: FakeEngine())
    monkeypatch.setattr("engine_cli._resolve_rule_path", lambda rule_path: rule_path)

    result = CliRunner().invoke(
        cli,
        ["run-rule", "rules/demo.yaml", "--format=json", "--print-data=both"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output.strip().splitlines()[-1])
    assert payload["raw_data"] == [{"id": "1"}, {"id": "1"}]
    assert payload["deduped_data"] == [{"id": "1"}]


def test_run_rule_jsonl_can_print_data_event(monkeypatch):
    """run-rule JSONL 可额外输出明细事件。"""
    class FakeEngine:
        def run(self, rule_path, event_handler=None, include_data=False):
            assert include_data is True
            event_handler(json.dumps({"type": "start", "rule": rule_path}))
            return {
                "status": "success",
                "total_collected": 2,
                "dedup_filtered": 1,
                "collected": 1,
                "raw_data": [{"id": "1"}, {"id": "1"}],
                "deduped_data": [{"id": "1"}],
            }

        def close(self):
            return None

    monkeypatch.setattr("engine_cli._engine", lambda: FakeEngine())
    monkeypatch.setattr("engine_cli._resolve_rule_path", lambda rule_path: rule_path)

    result = CliRunner().invoke(
        cli,
        ["run-rule", "rules/demo.yaml", "--format=jsonl", "--print-data=both"],
    )

    assert result.exit_code == 0
    lines = [json.loads(line) for line in result.output.strip().splitlines()]
    assert lines[-1] == {
        "type": "data",
        "raw_data": [{"id": "1"}, {"id": "1"}],
        "deduped_data": [{"id": "1"}],
    }
