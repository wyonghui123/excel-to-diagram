# -*- coding: utf-8 -*-
"""
测试 AuditLogger.log_create 审计写入行为

历史背景：FR-006 曾要求 CREATE 走 ds.batch_insert 一次批量写入。
实现已改为委托 AuditService.log()（支持 change_set_id / reason_code /
outcome / retention 等字段），因此一次 CREATE 会写 1 条整行快照
（field_name='_record'）+ 每个业务字段 1 条，逐行走 ds.insert。
本文件按当前契约验证：写入内容、字段过滤、trace 透传、失败返回、性能上界。
"""
import pytest
from unittest.mock import MagicMock
from meta.core.action_executor import AuditLogger


def _insert_records(ds):
    """提取 ds.insert(table, record) 调用中的 record 列表"""
    return [call[0][1] for call in ds.insert.call_args_list]


class TestAuditLogCreateBatch:
    """AuditLogger CREATE 审计写入测试"""

    def test_log_create_writes_record_and_field_rows(self):
        """1 条整行快照 + 每个业务字段 1 条"""
        ds = MagicMock()
        logger = AuditLogger(ds, enabled=True)
        data = {"name": "test", "code": "T001", "description": "desc"}

        result = logger.log_create(
            "domain", 100, data,
            trace_id="abc-123", user_id=1
        )

        assert result is True
        records = _insert_records(ds)
        assert len(records) == 4
        # 第 1 行是整行快照
        assert records[0]["action"] == "CREATE"
        assert records[0]["field_name"] == "_record"
        assert records[0]["extra_data"] is not None
        # 后续行是字段级
        assert records[1]["field_name"] == "name"
        assert records[2]["field_name"] == "code"
        assert records[3]["field_name"] == "description"

    def test_log_create_uses_row_inserts_not_batch(self):
        """当前实现逐行 ds.insert，不再调用 ds.batch_insert"""
        ds = MagicMock()
        logger = AuditLogger(ds, enabled=True)
        logger.log_create("user", 1, {"name": "x"})
        # 1 条 _record + 1 条字段
        assert ds.insert.call_count == 2
        assert ds.batch_insert.call_count == 0

    def test_log_create_filters_system_fields(self):
        """system 字段（id/created_at 等）不写入审计"""
        ds = MagicMock()
        logger = AuditLogger(ds, enabled=True)
        data = {
            "id": 1, "created_at": "2024-01-01", "created_by": "system",
            "name": "x", "is_system": True,
        }
        logger.log_create("user", 1, data)
        records = _insert_records(ds)
        field_names = [r["field_name"] for r in records if r["field_name"] != "_record"]
        # 只有 name 应被审计
        assert field_names == ["name"]

    def test_log_create_preserves_trace_id(self):
        """trace_id 必须传递到每行（关联可观测性）"""
        ds = MagicMock()
        logger = AuditLogger(ds, enabled=True)
        logger.log_create("user", 1, {"name": "x"}, trace_id="tid-001")
        records = _insert_records(ds)
        assert records
        for record in records:
            assert record["trace_id"] == "tid-001"

    def test_log_create_disabled(self):
        """enabled=False 时直接返回 True，不调用 ds"""
        ds = MagicMock()
        logger = AuditLogger(ds, enabled=False)
        result = logger.log_create("user", 1, {"name": "x"})
        assert result is True
        assert ds.batch_insert.call_count == 0
        assert ds.insert.call_count == 0

    def test_log_create_rollback_on_failure(self):
        """写入失败时返回 False，不抛异常"""
        ds = MagicMock()
        ds.insert.side_effect = Exception("DB locked")
        logger = AuditLogger(ds, enabled=True)
        result = logger.log_create("user", 1, {"name": "x"})
        assert result is False

    def test_log_create_empty_data(self):
        """空 data 也应成功（仅 1 行整行快照）"""
        ds = MagicMock()
        logger = AuditLogger(ds, enabled=True)
        result = logger.log_create("user", 1, {})
        assert result is True
        records = _insert_records(ds)
        assert len(records) == 1
        assert records[0]["field_name"] == "_record"

    def test_log_create_performance(self):
        """CREATE 20 字段对象写入 21 行（1 条快照 + 20 条字段）"""
        ds = MagicMock()
        logger = AuditLogger(ds, enabled=True)
        data = {f"field_{i}": f"value_{i}" for i in range(20)}
        result = logger.log_create("user", 1, data)
        assert result is True
        records = _insert_records(ds)
        assert len(records) == 21
