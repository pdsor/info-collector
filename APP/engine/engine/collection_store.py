"""普通采集结果 PostgreSQL 写入层。"""

from copy import deepcopy

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    create_engine,
    insert,
    text as sql_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from .config import get_pg_dsn


COLLECTION_METADATA = MetaData()

COLLECTION_RUNS = Table(
    "collection_runs",
    COLLECTION_METADATA,
    Column("id", UUID(as_uuid=False), primary_key=True, server_default=sql_text("gen_random_uuid()")),
    Column("rule_name", Text),
    Column("rule_path", Text),
    Column("subject", Text),
    Column("platform", Text),
    Column("status", Text),
    Column("total_collected", Integer),
    Column("saved_count", Integer),
    Column("dedup_filtered", Integer),
    Column("output_path", Text),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("duration_seconds", Numeric),
    Column("metadata", JSONB),
)

COLLECTION_ITEMS = Table(
    "collection_items",
    COLLECTION_METADATA,
    Column("id", UUID(as_uuid=False), primary_key=True, server_default=sql_text("gen_random_uuid()")),
    Column("run_id", UUID(as_uuid=False)),
    Column("rule_name", Text),
    Column("rule_path", Text),
    Column("subject", Text),
    Column("platform", Text),
    Column("raw_id", Text),
    Column("url", Text),
    Column("title", Text),
    Column("content_hash", Text),
    Column("field_completeness", Numeric),
    Column("injection_risk", Boolean),
    Column("data", JSONB),
    Column("governance", JSONB),
    Column("collected_at", DateTime(timezone=True)),
)

COLLECTION_RUN_ITEMS = Table(
    "collection_run_items",
    COLLECTION_METADATA,
    Column("id", UUID(as_uuid=False), primary_key=True, server_default=sql_text("gen_random_uuid()")),
    Column("run_id", UUID(as_uuid=False)),
    Column("rule_name", Text),
    Column("rule_path", Text),
    Column("subject", Text),
    Column("platform", Text),
    Column("item_stage", Text),
    Column("raw_id", Text),
    Column("url", Text),
    Column("title", Text),
    Column("content_hash", Text),
    Column("filter_reason", Text),
    Column("matched_existing_id", Text),
    Column("data", JSONB),
    Column("governance", JSONB),
    Column("collected_at", DateTime(timezone=True)),
)

COLLECTION_GOVERNANCE_RECORDS = Table(
    "collection_governance_records",
    COLLECTION_METADATA,
    Column("id", UUID(as_uuid=False), primary_key=True, server_default=sql_text("gen_random_uuid()")),
    Column("run_id", UUID(as_uuid=False)),
    Column("subject", Text),
    Column("platform", Text),
    Column("item_count", Integer),
    Column("duplicate_count", Integer),
    Column("injection_risk_count", Integer),
    Column("field_completeness", Numeric),
    Column("quality_score", Numeric),
    Column("status", Text),
    Column("summary", JSONB),
)


class CollectionStore:
    """普通采集结果 PostgreSQL 存储。"""

    def __init__(self, dsn: str, connection_factory=None):
        if not dsn:
            raise ValueError("collection store dsn is required")
        self.dsn = dsn
        self.connection_factory = connection_factory
        self._engine = None

    @classmethod
    def from_project_config(cls):
        """从项目级配置读取 PostgreSQL 连接串。"""
        return cls(dsn=get_pg_dsn())

    def _connect(self):
        """获取 PostgreSQL 连接；测试可注入伪连接。"""
        if self.connection_factory:
            return self.connection_factory()
        if self._engine is None:
            self._engine = create_engine(self.dsn)
        return self._engine.connect()

    def _insert_returning_id(self, connection, table, payload):
        """插入记录并返回数据库生成的 ID。"""
        statement = insert(table).values(**payload).returning(table.c.id)
        return connection.execute(statement).scalar_one()

    def _resolve_subject(self, rule: dict) -> str:
        return rule.get("subject") or (rule.get("source") or {}).get("subject") or ""

    def _resolve_platform(self, rule: dict) -> str:
        return (rule.get("source") or {}).get("platform") or "unknown"

    def _build_run_payload(
        self,
        *,
        rule: dict,
        rule_path: str,
        item_count: int,
        governance_summary: dict,
        total_collected: int,
        dedup_filtered: int,
        output_path: str,
        status: str,
        started_at,
        finished_at,
        duration_seconds: float,
    ) -> dict:
        return {
            "rule_name": rule.get("name") or rule_path,
            "rule_path": rule_path,
            "subject": self._resolve_subject(rule),
            "platform": self._resolve_platform(rule),
            "status": status,
            "total_collected": int(total_collected),
            "saved_count": int(item_count),
            "dedup_filtered": int(dedup_filtered),
            "output_path": output_path or "",
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": duration_seconds,
            "metadata": {"governance": deepcopy(governance_summary or {})},
        }

    def _build_item_payload(
        self,
        *,
        run_id,
        rule: dict,
        rule_path: str,
        item: dict,
        collected_at,
    ) -> dict:
        governance = deepcopy(item.get("_governance") or {})
        data = {key: deepcopy(value) for key, value in item.items() if key != "_governance"}
        return {
            "run_id": run_id,
            "rule_name": rule.get("name") or rule_path,
            "rule_path": rule_path,
            "subject": self._resolve_subject(rule),
            "platform": self._resolve_platform(rule),
            "raw_id": item.get("raw_id"),
            "url": item.get("url"),
            "title": item.get("title"),
            "content_hash": governance.get("content_hash"),
            "field_completeness": governance.get("field_completeness"),
            "injection_risk": bool(governance.get("injection_risk", False)),
            "data": data,
            "governance": governance,
            "collected_at": collected_at,
        }

    def _build_run_item_payload(
        self,
        *,
        run_id,
        rule: dict,
        rule_path: str,
        item: dict,
        item_stage: str,
        collected_at,
    ) -> dict:
        governance = deepcopy(item.get("_governance") or {})
        data = {key: deepcopy(value) for key, value in item.items() if key != "_governance"}
        return {
            "run_id": run_id,
            "rule_name": rule.get("name") or rule_path,
            "rule_path": rule_path,
            "subject": self._resolve_subject(rule),
            "platform": self._resolve_platform(rule),
            "item_stage": item_stage,
            "raw_id": item.get("raw_id"),
            "url": item.get("url"),
            "title": item.get("title"),
            "content_hash": governance.get("content_hash"),
            "filter_reason": item.get("_filter_reason"),
            "matched_existing_id": item.get("_matched_existing_id"),
            "data": data,
            "governance": governance,
            "collected_at": collected_at,
        }

    def _build_governance_payload(self, *, run_id, rule: dict, summary: dict) -> dict:
        summary = deepcopy(summary or {})
        return {
            "run_id": run_id,
            "subject": self._resolve_subject(rule),
            "platform": self._resolve_platform(rule),
            "item_count": int(summary.get("item_count", 0)),
            "duplicate_count": int(summary.get("duplicate_count", 0)),
            "injection_risk_count": int(summary.get("injection_risk_count", 0)),
            "field_completeness": summary.get("field_completeness", 1.0),
            "quality_score": summary.get("quality_score", 1.0),
            "status": summary.get("status") or "SUCCESS",
            "summary": summary,
        }

    def save_run_items(
        self,
        *,
        rule: dict,
        rule_path: str,
        items: list[dict],
        governance_summary: dict,
        total_collected: int,
        dedup_filtered: int,
        output_path: str,
        status: str,
        started_at,
        finished_at,
        duration_seconds: float,
        raw_items: list[dict] | None = None,
        filtered_items: list[dict] | None = None,
        deduped_items: list[dict] | None = None,
    ) -> dict:
        """在一个事务内保存运行记录、采集结果和治理摘要。"""
        connection = self._connect()
        transaction = None
        item_ids = []
        run_item_ids = []
        try:
            transaction = connection.begin()
            run_payload = self._build_run_payload(
                rule=rule,
                rule_path=rule_path,
                item_count=len(items),
                governance_summary=governance_summary,
                total_collected=total_collected,
                dedup_filtered=dedup_filtered,
                output_path=output_path,
                status=status,
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=duration_seconds,
            )
            run_id = self._insert_returning_id(connection, COLLECTION_RUNS, run_payload)

            for item in items:
                item_payload = self._build_item_payload(
                    run_id=run_id,
                    rule=rule,
                    rule_path=rule_path,
                    item=item,
                    collected_at=finished_at,
                )
                item_ids.append(self._insert_returning_id(connection, COLLECTION_ITEMS, item_payload))

            run_item_groups = [
                ("raw", raw_items if raw_items is not None else []),
                ("deduped", deduped_items if deduped_items is not None else items),
                ("filtered", filtered_items if filtered_items is not None else []),
            ]
            for item_stage, stage_items in run_item_groups:
                for item in stage_items:
                    run_item_payload = self._build_run_item_payload(
                        run_id=run_id,
                        rule=rule,
                        rule_path=rule_path,
                        item=item,
                        item_stage=item_stage,
                        collected_at=finished_at,
                    )
                    run_item_ids.append(
                        self._insert_returning_id(connection, COLLECTION_RUN_ITEMS, run_item_payload)
                    )

            governance_payload = self._build_governance_payload(
                run_id=run_id,
                rule=rule,
                summary=governance_summary,
            )
            governance_record_id = self._insert_returning_id(
                connection,
                COLLECTION_GOVERNANCE_RECORDS,
                governance_payload,
            )

            transaction.commit()
            return {
                "run_id": run_id,
                "item_ids": item_ids,
                "run_item_ids": run_item_ids,
                "governance_record_id": governance_record_id,
            }
        except Exception:
            if transaction:
                transaction.rollback()
            raise
        finally:
            close = getattr(connection, "close", None)
            if close:
                close()
