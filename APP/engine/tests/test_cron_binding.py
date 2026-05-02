"""Tests for cron job rule binding"""
import pytest
import sqlite3
import tempfile
import os
import sys
from unittest.mock import patch, MagicMock


# Add dashboard path for imports
_DASHBOARD_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'dashboard')
sys.path.insert(0, os.path.dirname(_DASHBOARD_PATH))


class TestCronBinding:
    """Test cron job binding to specific rules"""

    def test_cron_respects_rule_path(self):
        """Cron 任务应根据 rule_path 绑定特定规则，而非总是 run-all"""
        from dashboard.apis.cron_api import _add_scheduler_job

        tmp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp_db.close()
        conn = sqlite3.connect(tmp_db.name)
        conn.execute("""
            CREATE TABLE cron_jobs (
                id INTEGER PRIMARY KEY, name TEXT, second TEXT, minute TEXT,
                hour TEXT, day TEXT, month TEXT, day_of_week TEXT,
                rule_path TEXT, enabled INTEGER)
        """)
        conn.execute(
            "INSERT INTO cron_jobs (name,second,minute,hour,day,month,day_of_week,rule_path,enabled) "
            "VALUES ('测试', '0', '*', '*', '*', '*', '*', 'rules/test/sample_rule.yaml', 1)"
        )
        conn.commit()
        conn.close()

        # 验证 rule_path 被正确记录
        conn2 = sqlite3.connect(tmp_db.name)
        row = conn2.execute("SELECT rule_path FROM cron_jobs WHERE id=1").fetchone()
        conn2.close()
        assert row[0] == "rules/test/sample_rule.yaml"
        
        os.unlink(tmp_db.name)

    def test_cron_with_empty_rule_path_runs_all(self):
        """当 rule_path 为空时，cron 应执行 run-all"""
        from dashboard.apis.cron_api import _add_scheduler_job

        tmp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        tmp_db.close()
        conn = sqlite3.connect(tmp_db.name)
        conn.execute("""
            CREATE TABLE cron_jobs (
                id INTEGER PRIMARY KEY, name TEXT, second TEXT, minute TEXT,
                hour TEXT, day TEXT, month TEXT, day_of_week TEXT,
                rule_path TEXT, enabled INTEGER)
        """)
        conn.execute(
            "INSERT INTO cron_jobs (name,second,minute,hour,day,month,day_of_week,rule_path,enabled) "
            "VALUES ('全部规则', '0', '*', '*', '*', '*', '*', '', 1)"
        )
        conn.commit()
        conn.close()

        # 验证 rule_path 为空字符串
        conn2 = sqlite3.connect(tmp_db.name)
        row = conn2.execute("SELECT rule_path FROM cron_jobs WHERE id=1").fetchone()
        conn2.close()
        assert row[0] == ""
        
        os.unlink(tmp_db.name)

    def test_add_scheduler_job_uses_rule_path(self):
        """测试 _add_scheduler_job 将 rule_path 传递给调度器"""
        import dashboard.apis.cron_api as cron_api

        mock_scheduler = MagicMock()
        original_scheduler = cron_api._scheduler
        cron_api._scheduler = mock_scheduler
        
        try:
            job_row = {
                'id': 1,
                'name': '测试任务',
                'second': '0',
                'minute': '*',
                'hour': '*',
                'day': '*',
                'month': '*',
                'day_of_week': '*',
                'rule_path': 'rules/test/test_rule.yaml',
                'enabled': 1
            }
            
            cron_api._add_scheduler_job(job_row)
            
            # 验证 scheduler.add_job 被调用
            assert mock_scheduler.add_job.called
            
            # 验证 job_id 正确
            assert mock_scheduler.add_job.call_count == 1
            
        finally:
            cron_api._scheduler = original_scheduler

    def test_add_scheduler_job_with_empty_rule_path(self):
        """测试 rule_path 为空时调度器仍能正确添加 job"""
        import dashboard.apis.cron_api as cron_api

        mock_scheduler = MagicMock()
        original_scheduler = cron_api._scheduler
        cron_api._scheduler = mock_scheduler
        
        try:
            job_row = {
                'id': 2,
                'name': '全部规则',
                'second': '0',
                'minute': '*',
                'hour': '*',
                'day': '*',
                'month': '*',
                'day_of_week': '*',
                'rule_path': '',
                'enabled': 1
            }
            
            cron_api._add_scheduler_job(job_row)
            
            # 验证调度器被正确调用
            assert mock_scheduler.add_job.called
            call_kwargs = mock_scheduler.add_job.call_args[1]
            assert call_kwargs['id'] == 'cron_2'
            
        finally:
            cron_api._scheduler = original_scheduler
