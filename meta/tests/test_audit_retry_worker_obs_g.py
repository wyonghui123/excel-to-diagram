# -*- coding: utf-8 -*-
"""
[R018 P2 OBS-G] AuditRetryWorker g2/g3 单测

测试目标:
1. g2 — retry 重建行继承 source error_message
   - error_message 字段非空
   - extra_data.original_error 包含完整原 error
2. g3 — retry 自身失败时累加 retry_count, 达 max 后标 gave_up
   - 第 1 次失败: retry_count=1
   - 第 2 次失败: retry_count=2
   - 第 3 次失败: status='gave_up', retry_count=3
   - gave_up 之后不再被 _scan_and_retry 扫到

不使用 pytest, 直接 python -m unittest 运行 (符合 .trae/rules/sandbox-aware)
"""
import sys
import os
import json
import sqlite3
import tempfile
import unittest

# [FIX sandbox] 把项目根加到 sys.path
_PROJ_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJ_ROOT)

# 测试环境标记 (避免真正启动 worker thread)
os.environ.setdefault('TESTING', 'true')
os.environ.setdefault('PYTEST_CURRENT_TEST', 'test_audit_retry_worker_obs_g')

from meta.services.audit_retry_worker import (
    AuditRetryWorker,
    AUDIT_RETRY_MAX_ATTEMPTS,
)


class _MockDataSource:
    """Mock data_source — 只实现 retry worker 用到的接口
    (execute, fetchall, insert, commit, is_connected, in_transaction)
    """
    def __init__(self, db_path):
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._in_txn = False
        self._create_schema()
        self._in_transaction = False

    def _create_schema(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT NOT NULL,
                object_id INTEGER,
                action TEXT NOT NULL,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                user_id TEXT,
                user_name TEXT,
                ip_address TEXT,
                user_agent TEXT,
                created_at TEXT,
                extra_data TEXT,
                trace_id TEXT,
                transaction_id TEXT,
                status TEXT DEFAULT 'written',
                retry_count INTEGER DEFAULT 0,
                error_message TEXT,
                agent_id TEXT,
                agent_session_id TEXT,
                tool_call_id TEXT,
                agent_reasoning TEXT,
                parent_object_type TEXT,
                parent_object_id TEXT,
                action_kind TEXT,
                outcome TEXT,
                log_category TEXT,
                log_level TEXT
            )
        """)
        self._conn.commit()

    @property
    def is_connected(self):
        return True

    @property
    def in_transaction(self):
        return self._in_txn

    def execute(self, sql, params=None):
        if params is None:
            return self._conn.execute(sql)
        return self._conn.execute(sql, params)

    def fetchall(self):
        # sqlite3.Cursor.fetchall 直接调用即可, 不需要单独 mock
        # 但 retry worker 用法: cursor = self._ds.execute(sql); cursor.fetchall()
        # 上面的 self._ds.execute 已经返回 Cursor, fetchall 调的是 cursor 的方法
        # 这里是误标, 不需要
        raise NotImplementedError("Use cursor returned from execute()")

    def insert(self, table, record):
        cols = list(record.keys())
        placeholders = ','.join('?' * len(cols))
        col_list = ','.join(f'"{c}"' for c in cols)
        values = [record[c] for c in cols]
        sql = f'INSERT INTO "{table}" ({col_list}) VALUES ({placeholders})'
        cur = self._conn.execute(sql, values)
        self._conn.commit()
        return cur.lastrowid

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()


class TestAuditRetryWorkerOBSG(unittest.TestCase):
    """[R018 P2 OBS-G] retry worker g2/g3 修复测试"""

    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self._db_path = self._tmp.name
        self._tmp.close()
        self._ds = _MockDataSource(self._db_path)
        # 用 interval=999 避免 worker 真的起 thread 干扰测试
        self._worker = AuditRetryWorker(self._ds, interval_sec=999, batch_size=10)

    def tearDown(self):
        try:
            self._ds.close()
        except Exception:
            pass
        try:
            os.unlink(self._db_path)
        except Exception:
            pass

    # ─────────── g2 测试: retry 重建行保留原 error_message ───────────

    def test_g2_retry_row_inherits_error_message(self):
        """g2 主测试: source error_message 出现在 retry 行的 error_message 字段"""
        # 插入一条 source AUDIT_WRITE_FAILED 记录
        source_error = "AuditInterceptor.log_create.<locals>.write_audit_log() got an unexpected keyword argument 'user_id'"
        self._ds.insert("audit_logs", {
            "object_type": "__audit_failure__",
            "object_id": 0,
            "action": "AUDIT_WRITE_FAILED",
            "field_name": "",
            "old_value": "",
            "new_value": json.dumps({
                "original_action": "CREATE",
                "error": source_error,
            }, ensure_ascii=False),
            "user_id": None,
            "user_name": "system",
            "ip_address": "",
            "user_agent": "",
            "created_at": "2026-09-15T10:00:00",
            "extra_data": json.dumps({
                "original_trace_id": "tr_obs_g_test_001",
                "original_transaction_id": "tx_obs_g_test_001",
                "original_object_type": "user",
                "original_object_id": "42",
                "original_action": "CREATE",
                "failure_kind": "AUDIT_WRITE_FAILED",
            }, ensure_ascii=False),
            "trace_id": "tr_obs_g_test_001",
            "transaction_id": "tx_obs_g_test_001",
            "status": "failed",
            "retry_count": 0,
            "error_message": source_error,
            "agent_id": None,
            "agent_session_id": None,
            "tool_call_id": None,
            "agent_reasoning": None,
            "outcome": "failure",
            "log_category": "system",
            "log_level": "ERROR",
        })

        # 触发 _scan_and_retry (不启 worker thread, 直接调)
        self._worker._scan_and_retry()

        # 检查 source 标 status='retried'
        source_row = self._ds.execute(
            "SELECT status, retry_count FROM audit_logs WHERE action='AUDIT_WRITE_FAILED'"
        ).fetchone()
        self.assertEqual(source_row['status'], 'retried', "source 应被标 retried")

        # 检查 retry 重建行
        retry_row = self._ds.execute(
            "SELECT * FROM audit_logs WHERE action='CREATE' AND status='retried' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(retry_row, "应有一条 CREATE retry 重建行")
        # g2 修复: error_message 字段不再是空字符串
        self.assertEqual(
            retry_row['error_message'], source_error,
            f"retry 行的 error_message 应继承 source error, 实际: {retry_row['error_message']!r}"
        )
        # g2 修复: extra_data.original_error 应包含完整原 error
        retry_extra = json.loads(retry_row['extra_data'])
        self.assertIn('original_error', retry_extra, "extra_data 应包含 original_error")
        self.assertEqual(
            retry_extra['original_error'], source_error,
            f"extra_data.original_error 应等于 source error, 实际: {retry_extra['original_error']!r}"
        )
        # 验证其他关键字段没漏
        self.assertEqual(retry_row['trace_id'], 'tr_obs_g_test_001')
        # 注: object_type 不严格断言, 因为 _extract_obj_info 在 mock 环境
        # 不能从 audit_fn 闭包提取 (真实闭包分析依赖 action_executor 真实 lambda)
        # 此测试只验证 g2 修复 (error_message 继承)

    def test_g2_empty_source_error_message_keeps_empty(self):
        """g2 边界: source error_message 为空时, retry 行也保持空 (不抛异常)"""
        self._ds.insert("audit_logs", {
            "object_type": "__audit_failure__",
            "object_id": 0,
            "action": "AUDIT_WRITE_FAILED",
            "field_name": "",
            "old_value": "",
            "new_value": "",
            "user_id": None,
            "user_name": "system",
            "ip_address": "",
            "user_agent": "",
            "created_at": "2026-09-15T10:00:00",
            "extra_data": json.dumps({"original_action": "UNKNOWN"}, ensure_ascii=False),
            "trace_id": "tr_empty",
            "transaction_id": None,
            "status": "failed",
            "retry_count": 0,
            "error_message": "",  # 空
            "agent_id": None,
            "agent_session_id": None,
            "tool_call_id": None,
            "agent_reasoning": None,
            "outcome": "failure",
            "log_category": "system",
            "log_level": "ERROR",
        })
        self._worker._scan_and_retry()
        retry_row = self._ds.execute(
            "SELECT * FROM audit_logs WHERE action='UNKNOWN' AND status='retried' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertIsNotNone(retry_row)
        self.assertEqual(retry_row['error_message'], '', "source error 为空时 retry 行也为空")

    # ─────────── g3 测试: retry 自身失败时累加 retry_count + gave_up ───────────

    def test_g3_retry_count_increments_on_failure(self):
        """g3 主测试: _mark_retry_attempt 累加 retry_count"""
        # 插入一条 source (不直接 _scan, 只测 _mark_retry_attempt)
        source_id = self._ds.insert("audit_logs", {
            "object_type": "__audit_failure__",
            "object_id": 0,
            "action": "AUDIT_WRITE_FAILED",
            "field_name": "",
            "old_value": "",
            "new_value": "",
            "user_id": None,
            "user_name": "system",
            "ip_address": "",
            "user_agent": "",
            "created_at": "2026-09-15T10:00:00",
            "extra_data": "{}",
            "trace_id": "tr_g3_test",
            "transaction_id": None,
            "status": "failed",
            "retry_count": 0,
            "error_message": "boom",
            "agent_id": None,
            "agent_session_id": None,
            "tool_call_id": None,
            "agent_reasoning": None,
            "outcome": "failure",
            "log_category": "system",
            "log_level": "ERROR",
        })

        # 模拟第 1 次失败
        self._worker._mark_retry_attempt(source_id, current_retry_count=0)
        row = self._ds.execute(
            "SELECT retry_count, status FROM audit_logs WHERE id=?", (source_id,)
        ).fetchone()
        self.assertEqual(row['retry_count'], 1, f"第 1 次失败后 retry_count=1, 实际: {row['retry_count']}")
        self.assertEqual(row['status'], 'failed', "未达 max 应仍为 failed")

        # 模拟第 2 次失败
        self._worker._mark_retry_attempt(source_id, current_retry_count=1)
        row = self._ds.execute(
            "SELECT retry_count, status FROM audit_logs WHERE id=?", (source_id,)
        ).fetchone()
        self.assertEqual(row['retry_count'], 2, f"第 2 次失败后 retry_count=2, 实际: {row['retry_count']}")
        self.assertEqual(row['status'], 'failed', "未达 max 应仍为 failed")

        # 模拟第 3 次失败 — 应触发 gave_up
        self._worker._mark_retry_attempt(source_id, current_retry_count=2)
        row = self._ds.execute(
            "SELECT retry_count, status FROM audit_logs WHERE id=?", (source_id,)
        ).fetchone()
        self.assertEqual(row['retry_count'], 3, f"第 3 次失败后 retry_count=3, 实际: {row['retry_count']}")
        self.assertEqual(row['status'], 'gave_up', f"达 max 后应标 gave_up, 实际: {row['status']}")

    def test_g3_gave_up_not_rescanned(self):
        """g3 集成测试: gave_up 记录不应被 _scan_and_retry 扫到"""
        # 插 1 条 retry_count 达 max 的 gave_up
        self._ds.insert("audit_logs", {
            "object_type": "__audit_failure__",
            "object_id": 0,
            "action": "AUDIT_WRITE_FAILED",
            "field_name": "",
            "old_value": "",
            "new_value": "",
            "user_id": None,
            "user_name": "system",
            "ip_address": "",
            "user_agent": "",
            "created_at": "2026-09-15T10:00:00",
            "extra_data": json.dumps({"original_action": "CREATE"}, ensure_ascii=False),
            "trace_id": "tr_gave_up",
            "transaction_id": None,
            "status": "gave_up",  # 已是 gave_up 状态
            "retry_count": AUDIT_RETRY_MAX_ATTEMPTS,  # 达 max
            "error_message": "permanent failure",
            "agent_id": None,
            "agent_session_id": None,
            "tool_call_id": None,
            "agent_reasoning": None,
            "outcome": "failure",
            "log_category": "system",
            "log_level": "ERROR",
        })

        # 触发 _scan_and_retry
        self._worker._scan_and_retry()

        # 不应有 CREATE retry 重建行
        retry_row = self._ds.execute(
            "SELECT COUNT(*) AS cnt FROM audit_logs WHERE action='CREATE'"
        ).fetchone()
        self.assertEqual(retry_row['cnt'], 0, "gave_up 记录不应被 retry")

    def test_g3_stats_gave_up_counter(self):
        """g3 stats 测试: gave_up 计数器 +1"""
        source_id = self._ds.insert("audit_logs", {
            "object_type": "__audit_failure__",
            "object_id": 0,
            "action": "AUDIT_WRITE_FAILED",
            "field_name": "",
            "old_value": "",
            "new_value": "",
            "user_id": None,
            "user_name": "system",
            "ip_address": "",
            "user_agent": "",
            "created_at": "2026-09-15T10:00:00",
            "extra_data": "{}",
            "trace_id": "tr_stats",
            "transaction_id": None,
            "status": "failed",
            "retry_count": 0,
            "error_message": "",
            "agent_id": None,
            "agent_session_id": None,
            "tool_call_id": None,
            "agent_reasoning": None,
            "outcome": "failure",
            "log_category": "system",
            "log_level": "ERROR",
        })
        # 触发 gave_up
        self._worker._mark_retry_attempt(source_id, current_retry_count=AUDIT_RETRY_MAX_ATTEMPTS - 1)
        stats = self._worker.get_stats()
        self.assertEqual(stats['gave_up'], 1, f"gave_up stats 应为 1, 实际: {stats['gave_up']}")


if __name__ == '__main__':
    # 静默 logging, 让 unittest 输出干净
    import logging
    logging.disable(logging.CRITICAL)
    unittest.main(verbosity=2)
