# -*- coding: utf-8 -*-
"""
audit_retry_worker.py (v3.18 FR-010)
后台 daemon thread: 扫 audit_logs 表里 action='AUDIT_WRITE_FAILED' 的记录,
尝试重建原始 audit 记录 (从 extra_data 提取 obj info).

设计:
- 独立后台 thread, 每 60s 扫一次
- 只扫 status='failed' 的记录 (避免重复 retry)
- 成功后 UPDATE status='retried', 不删除 (保留历史)
- 失败记录保留 status='failed', 下次继续重试

限制:
- 只能恢复 obj 级别 (object_type/id/action/user), field 级别 (field_name/old_value/new_value) 丢失
- 历史 867 条 AUDIT_WRITE_FAILED (22:50 前, 没 extra_data) 无法重建
"""
import threading
import time
import json
import logging
from datetime import datetime
from typing import Optional, Any

logger = logging.getLogger(__name__)


class AuditRetryWorker:
    """后台 daemon thread: 重试失败的 audit 写入"""

    def __init__(self, data_source, interval_sec: int = 60, batch_size: int = 100):
        self._ds = data_source
        self._interval = interval_sec
        self._batch_size = batch_size
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stats = {
            'scanned': 0,
            'retried': 0,
            'success': 0,
            'failed': 0,
        }
        self._stats_lock = threading.Lock()

    def start(self):
        """启动后台 thread"""
        if self._running:
            logger.warning("AuditRetryWorker already running")
            return
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True, name='audit-retry-worker')
        self._thread.start()
        logger.info("AuditRetryWorker started: interval=%ds batch_size=%d", self._interval, self._batch_size)

    def stop(self):
        """停止后台 thread"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("AuditRetryWorker stopped")

    def get_stats(self) -> dict:
        """获取统计信息"""
        with self._stats_lock:
            return dict(self._stats)

    def _worker(self):
        """后台循环: 扫 AUDIT_WRITE_FAILED, 重试"""
        while self._running:
            try:
                self._scan_and_retry()
            except Exception as e:
                logger.error("AuditRetryWorker scan error: %s", str(e))
            time.sleep(self._interval)

    def _scan_and_retry(self):
        """扫一批 AUDIT_WRITE_FAILED, 重试"""
        if not self._ds or not getattr(self._ds, 'is_connected', False):
            return

        # 扫 status='failed' 的 AUDIT_WRITE_FAILED 记录
        try:
            rows = self._ds.execute(
                """SELECT id, object_type, object_id, user_id, user_name,
                          ip_address, user_agent, extra_data, created_at
                   FROM audit_logs
                   WHERE action='AUDIT_WRITE_FAILED' AND status='failed'
                   ORDER BY id ASC
                   LIMIT ?""",
                (self._batch_size,)
            ).fetchall()
        except Exception as e:
            logger.error("Failed to scan AUDIT_WRITE_FAILED: %s", str(e))
            return

        if not rows:
            return

        with self._stats_lock:
            self._stats['scanned'] += len(rows)

        logger.info("AuditRetryWorker: found %d AUDIT_WRITE_FAILED records", len(rows))

        for row in rows:
            audit_id, obj_type, obj_id, user_id, user_name, ip_addr, user_agent, extra_data_str, created_at = row
            try:
                extra_data = json.loads(extra_data_str) if extra_data_str else {}
                self._retry_one(audit_id, obj_type, obj_id, user_id, user_name, ip_addr, user_agent, extra_data, created_at)
            except Exception as e:
                logger.error("AuditRetryWorker retry failed for id=%d: %s", audit_id, str(e))
                with self._stats_lock:
                    self._stats['failed'] += 1

    def _retry_one(self, audit_id: int, obj_type: str, obj_id: str,
                   user_id: Any, user_name: str, ip_addr: str, user_agent: str,
                   extra_data: dict, created_at: str):
        """重试一条 AUDIT_WRITE_FAILED"""
        # 从 extra_data 提取原始 audit 信息
        original_action = extra_data.get('original_action', 'UNKNOWN')
        original_trace_id = extra_data.get('original_trace_id')

        # 重建 audit 记录 (obj 级别, field 级别丢失)
        retry_record = {
            'object_type': obj_type,
            'object_id': obj_id,
            'action': original_action,
            'field_name': '',  # field 级别丢失
            'old_value': '',
            'new_value': json.dumps({
                'retry_from': 'AUDIT_WRITE_FAILED',
                'original_audit_id': audit_id,
                'original_created_at': created_at,
                'note': 'field-level data lost, only obj-level recovered',
            }, ensure_ascii=False),
            'user_id': user_id,
            'user_name': user_name or 'system',
            'ip_address': ip_addr or '',
            'user_agent': user_agent or '',
            'created_at': datetime.now().isoformat(),
            'extra_data': json.dumps({
                'retry_source': 'audit_retry_worker',
                'original_audit_id': audit_id,
                'original_trace_id': original_trace_id,
                'original_created_at': created_at,
            }, ensure_ascii=False),
            'trace_id': original_trace_id,
            'transaction_id': None,
            'status': 'retried',
            'retry_count': 1,
            'error_message': '',
            'agent_id': None,
            'agent_session_id': None,
            'tool_call_id': None,
            'agent_reasoning': None,
            'outcome': 'retry',
            'log_category': 'business',
            'log_level': 'INFO',
        }

        # 写入重建的 audit 记录
        try:
            self._ds.insert('audit_logs', retry_record)
            if not getattr(self._ds, 'in_transaction', False):
                self._ds.commit()
        except Exception as e:
            logger.error("Failed to insert retry audit record: %s", str(e))
            with self._stats_lock:
                self._stats['failed'] += 1
            return

        # 标记原 AUDIT_WRITE_FAILED 为 status='retried'
        try:
            self._ds.execute(
                "UPDATE audit_logs SET status='retried' WHERE id=?",
                (audit_id,)
            )
            if not getattr(self._ds, 'in_transaction', False):
                self._ds.commit()
        except Exception as e:
            logger.error("Failed to update AUDIT_WRITE_FAILED status: %s", str(e))

        with self._stats_lock:
            self._stats['retried'] += 1
            self._stats['success'] += 1

        logger.info("AuditRetryWorker: retried audit_id=%d obj=%s#%s action=%s",
                    audit_id, obj_type, obj_id, original_action)


# 全局单例
_audit_retry_worker: Optional[AuditRetryWorker] = None


def get_audit_retry_worker() -> Optional[AuditRetryWorker]:
    """获取全局 AuditRetryWorker 实例"""
    return _audit_retry_worker


def init_audit_retry_worker(data_source, interval_sec: int = 60) -> AuditRetryWorker:
    """初始化并启动全局 AuditRetryWorker"""
    global _audit_retry_worker
    if _audit_retry_worker is None:
        _audit_retry_worker = AuditRetryWorker(data_source, interval_sec=interval_sec)
        _audit_retry_worker.start()
    return _audit_retry_worker


def stop_audit_retry_worker():
    """停止全局 AuditRetryWorker"""
    global _audit_retry_worker
    if _audit_retry_worker:
        _audit_retry_worker.stop()
        _audit_retry_worker = None
