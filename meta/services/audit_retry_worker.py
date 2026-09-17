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
import os
import logging
from datetime import datetime
from typing import Optional, Any

logger = logging.getLogger(__name__)

# [FIX R018 P2 OBS-G g3 2026-09-15] retry worker 最大重试次数
# 超过此次数后 source AUDIT_WRITE_FAILED 状态置 'gave_up', 跳出无限循环
# 防止 audit_retry_worker 自身失败时反复重试同一条 source 重建行
# 默认 3 次, 可通过环境变量 AUDIT_RETRY_MAX_ATTEMPTS 覆盖
AUDIT_RETRY_MAX_ATTEMPTS = int(os.environ.get('AUDIT_RETRY_MAX_ATTEMPTS', '3'))


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
            'gave_up': 0,  # [FIX R018 P2 OBS-G g3 2026-09-15] retry 达 max 后放弃计数
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
        # [FIX R018 P2 OBS-G g3 2026-09-15] 加 retry_count 列, 跳过已达 max_retry 的
        try:
            rows = self._ds.execute(
                """SELECT id, object_type, object_id, user_id, user_name,
                          ip_address, user_agent, extra_data, created_at,
                          error_message, retry_count
                   FROM audit_logs
                   WHERE action='AUDIT_WRITE_FAILED' AND status='failed'
                     AND retry_count < ?
                   ORDER BY id ASC
                   LIMIT ?""",
                (AUDIT_RETRY_MAX_ATTEMPTS, self._batch_size)
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
            (audit_id, obj_type, obj_id, user_id, user_name, ip_addr, user_agent,
             extra_data_str, created_at, source_error_message, source_retry_count) = row
            try:
                extra_data = json.loads(extra_data_str) if extra_data_str else {}
                # [FIX R018 P2 OBS-G g2 2026-09-15] 把 source error_message 传给 _retry_one
                # 背景: 当前 retry 重建行 error_message='' 丢原始 error, 645 条孤儿记录
                # 改为继承到 retry 行的 extra_data.original_error
                self._retry_one(
                    audit_id, obj_type, obj_id, user_id, user_name,
                    ip_addr, user_agent, extra_data, created_at,
                    source_error_message=source_error_message or '',
                    source_retry_count=source_retry_count or 0,
                )
            except Exception as e:
                logger.error("AuditRetryWorker retry failed for id=%d: %s", audit_id, str(e))
                with self._stats_lock:
                    self._stats['failed'] += 1
                # [FIX R018 P2 OBS-G g3 2026-09-15] retry 自身失败时, 累加 source.retry_count
                # 达到 max 后 status='gave_up', 避免无限重试
                self._mark_retry_attempt(audit_id, source_retry_count or 0)

    def _mark_retry_attempt(self, audit_id: int, current_retry_count: int):
        """[FIX R018 P2 OBS-G g3 2026-09-15] 累加 retry_count, 达 max 后标 'gave_up'

        避免 retry worker 自身失败时, 下一轮又扫到同一条 source, 无限循环重建。
        'gave_up' 状态需 ops 人工介入 (离线 grep failed-audit-*.log 或直接 SQL 查)。
        """
        new_retry_count = (current_retry_count or 0) + 1
        try:
            if new_retry_count >= AUDIT_RETRY_MAX_ATTEMPTS:
                # 放弃: 标 gave_up, 不再被 _scan_and_retry 扫到 (retry_count >= max)
                self._ds.execute(
                    "UPDATE audit_logs SET retry_count=?, status='gave_up' WHERE id=?",
                    (new_retry_count, audit_id)
                )
                logger.warning(
                    "AuditRetryWorker gave up on audit_id=%d after %d attempts, status=gave_up",
                    audit_id, new_retry_count
                )
                with self._stats_lock:
                    self._stats['gave_up'] = self._stats.get('gave_up', 0) + 1
            else:
                # 累加 retry_count, 留作下一轮
                self._ds.execute(
                    "UPDATE audit_logs SET retry_count=? WHERE id=?",
                    (new_retry_count, audit_id)
                )
            if not getattr(self._ds, 'in_transaction', False):
                self._ds.commit()
        except Exception as e:
            logger.error("Failed to mark retry attempt for audit_id=%d: %s", audit_id, str(e))

    def _retry_one(self, audit_id: int, obj_type: str, obj_id: str,
                   user_id: Any, user_name: str, ip_addr: str, user_agent: str,
                   extra_data: dict, created_at: str,
                   source_error_message: str = '',
                   source_retry_count: int = 0):
        """重试一条 AUDIT_WRITE_FAILED"""
        # 从 extra_data 提取原始 audit 信息
        original_action = extra_data.get('original_action', 'UNKNOWN')
        original_trace_id = extra_data.get('original_trace_id')

        # 重建 audit 记录 (obj 级别, field 级别丢失)
        # [FIX R018 P2 OBS-G g2 2026-09-15] 保留原 error_message:
        #   1) error_message 字段直接写 source 的 error (截断 500 字避免过长)
        #   2) extra_data.original_error 写完整 (供后续分析)
        # 背景: 旧版写 error_message='', 645 条 retry 行无 error 可查, 变成孤儿
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
                # [FIX R018 P2 OBS-G g2 2026-09-15] 完整原 error 留存
                'original_error': (source_error_message or '')[:1000],
            }, ensure_ascii=False),
            'trace_id': original_trace_id,
            'transaction_id': None,
            'status': 'retried',
            'retry_count': 1,
            # [FIX R018 P2 OBS-G g2 2026-09-15] 改用源 error 截断 500 字
            # 旧版硬编码 '' 导致 645 条 retry 行无 error 信息
            'error_message': (source_error_message or '')[:500],
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
