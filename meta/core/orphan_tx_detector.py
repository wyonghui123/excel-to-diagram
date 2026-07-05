# -*- coding: utf-8 -*-
"""
[V007.15 L5] 后台定期检查 + 自动清理 orphan transaction

检测策略:
1. 读 _write_conn 真实状态 (savepoint probe)
2. 比对应用层 _in_transaction
3. 不一致 → 视为 orphan → 强制 ROLLBACK + 重置标志

运行方式:
- 启动时由 server.py 启动 daemon thread
- 每 N 秒 (state-aware: 30/60) 检查一次
- 状态污染时自动恢复
- 不影响正常业务

观测:
- Prometheus counter: orphan_detector_runs, orphan_recovered
- /healthz endpoint: orphan_detector.get_stats()
"""
import threading
import time
import logging
import sqlite3
import datetime
from typing import Optional

from meta.core.db_config_detector import get_runtime_config
from meta.core.sqlite_tx_state import get_tx_state, TxState
from meta.core.observability import metrics_inc, OBS_COUNTERS, log_tx_event

logger = logging.getLogger(__name__)


class OrphanTxDetector:
    """[V007.15 L5] 后台孤儿事务检测器"""

    def __init__(self, data_source):
        self._ds = data_source
        self._config = get_runtime_config()
        self._stop = False
        self._thread: Optional[threading.Thread] = None
        self._check_count = 0
        self._recovery_count = 0
        self._last_check_result = "init"
        self._last_check_ts = None

    def start(self):
        if not self._config.use_orphan_detector:
            logger.info("[V007.15 L5] Orphan detector disabled by config")
            return
        if self._thread is not None:
            logger.warning("[V007.15 L5] Orphan detector already started")
            return
        self._thread = threading.Thread(
            target=self._run, name='orphan-tx-detector', daemon=True
        )
        self._thread.start()
        logger.info(
            f"[V007.15 L5] Orphan TX detector started, "
            f"interval={self._config.orphan_check_interval_sec}s"
        )

    def stop(self):
        self._stop = True
        if self._thread:
            self._thread.join(timeout=5)

    def _run(self):
        while not self._stop:
            time.sleep(self._config.orphan_check_interval_sec)
            try:
                self._check_once()
            except Exception as e:
                logger.error(f"[V007.15 L5] Orphan detector iteration failed: {e}")

    def _check_once(self):
        """单次检查 + 恢复"""
        self._check_count += 1
        self._last_check_ts = datetime.datetime.utcnow().isoformat()
        metrics_inc('orphan_detector_runs')

        # 1. 拿 _write_conn
        write_conn = self._get_write_conn()
        if write_conn is None:
            self._last_check_result = "no_write_conn"
            return

        # 2. savepoint probe
        try:
            actual = get_tx_state(write_conn)
        except Exception as e:
            self._last_check_result = f"probe_error: {e}"
            return

        # 3. 读应用层 _in_transaction
        app_state = self._get_app_in_transaction()

        # 4. 比对 + 恢复
        if actual != TxState.NONE and not app_state:
            # ORPHAN! SQLite 在 tx 中, Python 说不在
            self._recover_orphan(write_conn, actual)
            self._last_check_result = "recovered"
        elif actual == TxState.NONE and app_state:
            # 应用层状态污染, 重置
            self._reset_app_state()
            metrics_inc('orphan_app_state_pollution')
            self._last_check_result = "app_state_pollution_reset"
        else:
            metrics_inc('orphan_detector_clean')
            self._last_check_result = "clean"

    def _recover_orphan(self, conn, actual_state: str):
        """Orphan 恢复: 强制 ROLLBACK + 重置 + 告警"""
        self._recovery_count += 1
        metrics_inc('orphan_recovered')
        log_tx_event(
            'orphan', None, 'recovered',
            f"actual_sqlite_state={actual_state}, forced_rollback"
        )

        try:
            conn.execute("ROLLBACK")
        except Exception as e:
            log_tx_event('orphan', None, 'rollback_error', str(e))
            # 兜底: 关闭连接
            try:
                conn.close()
                log_tx_event('orphan', None, 'connection_closed', 'last_resort')
            except Exception:
                pass

        self._reset_app_state()

    def _reset_app_state(self):
        """重置应用层 _in_transaction 标志"""
        try:
            if hasattr(self._ds, '_in_transaction'):
                self._ds._in_transaction = False
            if hasattr(self._ds, '_write_queue') and self._ds._write_queue:
                if hasattr(self._ds._write_queue, '_in_transaction'):
                    self._ds._write_queue._in_transaction = False
        except Exception as e:
            log_tx_event('orphan', None, 'state_reset_error', str(e))

    def _get_write_conn(self):
        """从 data_source 拿 write connection"""
        try:
            if hasattr(self._ds, '_write_queue') and self._ds._write_queue:
                if hasattr(self._ds._write_queue, '_write_conn'):
                    return self._ds._write_queue._write_conn
            if hasattr(self._ds, '_connection'):
                return self._ds._connection
        except Exception:
            return None
        return None

    def _get_app_in_transaction(self) -> bool:
        """读应用层 _in_transaction 状态"""
        try:
            if hasattr(self._ds, 'in_transaction'):
                return bool(self._ds.in_transaction)
        except Exception:
            return False
        return False

    def get_stats(self) -> dict:
        return {
            'check_count': self._check_count,
            'recovery_count': self._recovery_count,
            'interval_sec': self._config.orphan_check_interval_sec,
            'deployment_state': self._config.deployment_state,
            'last_check_ts': self._last_check_ts,
            'last_check_result': self._last_check_result,
        }

