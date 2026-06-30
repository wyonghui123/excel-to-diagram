# -*- coding: utf-8 -*-
"""
test_audit_tx_trace_v2_1.py
覆盖提交: 26455f3 (audit_interceptor 自动生成 tx_id/trace_id)
依据: .trae/specs/test-suite/post-6-22-roadmap.md 主题 6 (Audit Log)

测试:
- audit_interceptor 写入 audit_logs 时, 自动生成 tx_id (tx_<16hex>)
- 自动生成 trace_id (tr_<16hex>)
- 同一请求的多条 audit log 共享 trace_id (按事务追踪)
- 不同请求 tx_id 不同
- 命名规则 + 长度 + 唯一性 + 不为空
- 26455f3 新增的 _ensure_audit_tx_context() helper 行为正确
"""
import os
import re
import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = [
    pytest.mark.post_v2_1,
    pytest.mark.audit_help,
]


# 直接用 sqlite3 打开 architecture.db, 绕开 SqliteDataSource 池
ARCH_DB_PATH = str(PROJECT_ROOT / 'meta' / 'architecture.db')


def _open_db():
    """直接打开 DB (避免 pool/write_queue 复杂度)"""
    con = sqlite3.connect(ARCH_DB_PATH)
    con.row_factory = sqlite3.Row
    return con


# ============================================================
# 1. TestAuditTxIdTraceId (8 用例)
# ============================================================

class TestAuditTxIdTraceId:
    """audit_interceptor 自动生成 tx_id / trace_id (26455f3)"""

    def test_tx_id_auto_generated(self):
        """[26455f3] 每次 create 操作, audit_logs 自动生成 tx_id

        验证: 模拟 audit_interceptor 写入 audit_logs 后, transaction_id 字段非空
        注: helper 返回 (trace_id, transaction_id) 元组
        """
        from meta.services.audit_interceptor import _ensure_audit_tx_context

        trace_id, tx_id = _ensure_audit_tx_context()
        assert tx_id is not None, "tx_id should be auto-generated"
        assert isinstance(tx_id, str)
        assert len(tx_id) > 0, "tx_id should have non-empty value"

    def test_trace_id_auto_generated(self):
        """[26455f3] trace_id 也自动生成

        验证: 第一次调用时, trace_id 非空
        """
        from meta.services.audit_interceptor import _ensure_audit_tx_context

        trace_id, _ = _ensure_audit_tx_context()
        assert trace_id is not None, "trace_id should be auto-generated"
        assert isinstance(trace_id, str)
        assert len(trace_id) > 0, "trace_id should have non-empty value"

    def test_tx_id_format_prefix(self):
        """[26455f3] tx_id 命名规则: 'tx_<16hex>' 格式

        验证: 生成的 tx_id 以 'tx_' 开头, 后面跟 16 位 hex 字符
        (与 action_executor._write_audit_log_v2 保持一致)
        """
        from meta.services.audit_interceptor import _ensure_audit_tx_context

        _, tx_id = _ensure_audit_tx_context()
        assert tx_id is not None

        # 26455f3 命名规则: tx_<16hex> (16 个十六进制字符)
        m = re.match(r'^tx_[0-9a-f]{16}$', tx_id)
        assert m is not None, \
            f"tx_id '{tx_id}' does not match expected format (tx_<16hex>), " \
            f"expected: tx_ followed by 16 hex chars"

    def test_trace_id_format_prefix(self):
        """[26455f3] trace_id 命名规则: 'tr_<16hex>' 格式"""
        from meta.services.audit_interceptor import _ensure_audit_tx_context

        trace_id, _ = _ensure_audit_tx_context()
        assert trace_id is not None

        m = re.match(r'^tr_[0-9a-f]{16}$', trace_id)
        assert m is not None, \
            f"trace_id '{trace_id}' does not match expected format (tr_<16hex>)"

    def test_tx_id_unique_per_request(self):
        """[26455f3] 不同请求的 tx_id 不同

        验证: 不传参数时, 每次生成的 tx_id 都不同 (UUID-based)
        """
        from meta.services.audit_interceptor import _ensure_audit_tx_context

        _, tx1 = _ensure_audit_tx_context()
        _, tx2 = _ensure_audit_tx_context()
        _, tx3 = _ensure_audit_tx_context()

        # 三次都不同
        assert tx1 != tx2, f"Different requests should have different tx_id: {tx1} vs {tx2}"
        assert tx2 != tx3, f"Different requests should have different tx_id: {tx2} vs {tx3}"
        assert tx1 != tx3, f"Different requests should have different tx_id: {tx1} vs {tx3}"

    def test_trace_id_links_related_actions(self):
        """[26455f3] 同一 trace 的多个 action 共享 trace_id

        业务代码可以传同一个 trace_id 来关联多步操作
        """
        from meta.services.audit_interceptor import _ensure_audit_tx_context

        shared_trace = 'tr_abcdef1234567890'

        # 第一次: 使用共享 trace_id
        tr_a, _ = _ensure_audit_tx_context(trace_id=shared_trace)
        # 第二次: 仍传同一个 trace_id
        tr_b, _ = _ensure_audit_tx_context(trace_id=shared_trace)
        # 第三次
        tr_c, _ = _ensure_audit_tx_context(trace_id=shared_trace)

        # 共享的 trace_id 应保持一致
        assert tr_a == shared_trace, f"trace_id should be preserved: {tr_a}"
        assert tr_b == shared_trace, f"trace_id should be preserved: {tr_b}"
        assert tr_c == shared_trace, f"trace_id should be preserved: {tr_c}"

    def test_explicit_tx_id_preserved(self):
        """[26455f3] 显式传入的 tx_id 应被保留, 不被覆盖

        验证: _ensure_audit_tx_context(transaction_id='tx_xxx') 返回 'tx_xxx'
        """
        from meta.services.audit_interceptor import _ensure_audit_tx_context

        explicit_tx = 'tx_explicit_preserve_001'
        explicit_trace = 'tr_explicit_preserve_001'

        # helper 返回 (trace_id, transaction_id)
        tr, tx = _ensure_audit_tx_context(
            trace_id=explicit_trace,
            transaction_id=explicit_tx,
        )

        assert tx == explicit_tx, f"explicit tx_id should be preserved: got {tx}"
        assert tr == explicit_trace, f"explicit trace_id should be preserved: got {tr}"

    def test_audit_logs_schema_supports_tx_columns(self):
        """[26455f3] audit_logs 表必须包含 trace_id / transaction_id 列

        验证: 26455f3 之前的 schema 已含这 2 列 (v2.1 schema 迁移完成)
        """
        con = _open_db()
        try:
            cur = con.execute("PRAGMA table_info(audit_logs)")
            cols = [row[1] for row in cur.fetchall()]

            assert 'transaction_id' in cols, \
                "audit_logs.transaction_id column missing (v2.1 schema migration)"
            assert 'trace_id' in cols, \
                "audit_logs.trace_id column missing (v2.1 schema migration)"
        finally:
            con.close()
