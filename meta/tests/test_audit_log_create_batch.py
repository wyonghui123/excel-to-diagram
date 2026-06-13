# -*- coding: utf-8 -*-
"""
测试 AuditLogger.log_create 批量插入 (FR-006)
验证：CREATE 1 个对象 → 1 次 batch_insert（不是 1+N 次 insert）
"""
import pytest
from unittest.mock import MagicMock
from meta.core.action_executor import AuditLogger


class TestAuditLogCreateBatch:
    """AuditLogger 批量插入测试"""

    def test_log_create_uses_batch_insert(self):
        """[FR-006] log_create 走 ds.batch_insert，不走循环 ds.insert"""
        ds = MagicMock()
        ds.batch_insert = MagicMock(return_value=3)
        logger = AuditLogger(ds, enabled=True)
        data = {"name": "test", "code": "T001", "description": "desc"}

        result = logger.log_create(
            "domain", 100, data,
            trace_id="abc-123", user_id=1
        )

        # 验证：调用 batch_insert 1 次
        assert ds.batch_insert.call_count == 1
        # 验证：传入的 rows 包含 1 extra_data + 3 字段 = 4 行
        rows = ds.batch_insert.call_args[0][1]
        assert len(rows) == 4
        # 第 1 行是 extra_data
        assert rows[0]["action"] == "CREATE"
        assert rows[0]["field_name"] == ""
        assert rows[0]["extra_data"] is not None
        # 后续行是字段级
        assert rows[1]["field_name"] == "name"
        assert rows[2]["field_name"] == "code"
        assert rows[3]["field_name"] == "description"

    def test_log_create_does_not_call_insert(self):
        """[FR-006] log_create 不应再调用 ds.insert"""
        ds = MagicMock()
        logger = AuditLogger(ds, enabled=True)
        logger.log_create("user", 1, {"name": "x"})
        assert ds.insert.call_count == 0

    def test_log_create_filters_system_fields(self):
        """system 字段（id/created_at 等）不写入审计"""
        ds = MagicMock()
        logger = AuditLogger(ds, enabled=True)
        data = {
            "id": 1, "created_at": "2024-01-01", "created_by": "system",
            "name": "x", "is_system": True,
        }
        logger.log_create("user", 1, data)
        rows = ds.batch_insert.call_args[0][1]
        field_names = [r["field_name"] for r in rows if r["field_name"]]
        # 只有 name 应被审计
        assert field_names == ["name"]

    def test_log_create_preserves_trace_id(self):
        """trace_id 必须传递到每行（关联可观测性）"""
        ds = MagicMock()
        logger = AuditLogger(ds, enabled=True)
        logger.log_create("user", 1, {"name": "x"}, trace_id="tid-001")
        rows = ds.batch_insert.call_args[0][1]
        for row in rows:
            assert row["trace_id"] == "tid-001"

    def test_log_create_disabled(self):
        """enabled=False 时直接返回 True，不调用 ds"""
        ds = MagicMock()
        logger = AuditLogger(ds, enabled=False)
        result = logger.log_create("user", 1, {"name": "x"})
        assert result is True
        assert ds.batch_insert.call_count == 0

    def test_log_create_rollback_on_failure(self):
        """batch_insert 失败时返回 False，不抛异常"""
        ds = MagicMock()
        ds.batch_insert.side_effect = Exception("DB locked")
        logger = AuditLogger(ds, enabled=True)
        result = logger.log_create("user", 1, {"name": "x"})
        assert result is False

    def test_log_create_empty_data(self):
        """空 data 也应成功（仅 1 行 extra_data）"""
        ds = MagicMock()
        logger = AuditLogger(ds, enabled=True)
        result = logger.log_create("user", 1, {})
        assert result is True
        rows = ds.batch_insert.call_args[0][1]
        # 仅 extra_data 行
        assert len(rows) == 1
        assert rows[0]["field_name"] == ""

    def test_log_create_performance(self):
        """[NFR-001.5] CREATE 20 字段对象应只 1 次 batch_insert"""
        ds = MagicMock()
        logger = AuditLogger(ds, enabled=True)
        data = {f"field_{i}": f"value_{i}" for i in range(20)}
        result = logger.log_create("user", 1, data)
        # 1 次 batch_insert（包含 1 extra_data + 20 字段 = 21 行）
        assert ds.batch_insert.call_count == 1
        rows = ds.batch_insert.call_args[0][1]
        assert len(rows) == 21
