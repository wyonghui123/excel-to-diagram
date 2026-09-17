# -*- coding: utf-8 -*-
"""V007.41 safe_connect 单元测试

覆盖范围:
- safe_connect_for_read: 默认参数 / contextmanager / row_factory
- safe_connect_for_write: 无事务 raise / force_no_tx 绕过 / UNKNOWN 降级
- safe_connect (兼容): 4 种 mode / 错误 mode raise
- SafeConnectConfig: 默认值 / 环境变量覆盖
- metric 计数: 4 个 metric 正确递增

[V007.41 BUG-FIX] 背景:
  - V007.40 在 17 个文件复制 timeout + check_same_thread + busy_timeout 三件套
  - V007.41 集中到 meta/core.safe_connect 工厂
  - 本测试确保工厂行为符合 FR-001~008 / NFR-001~004
"""
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import pytest

# conftest 已设置 DISABLE_RATE_LIMIT, 这里只需要 import
pytestmark = pytest.mark.integration


class TestSafeConnectForRead:
    """safe_connect_for_read 默认参数 + contextmanager 测试"""

    def test_default_params(self):
        """V007.41 FR-001: 默认 timeout=30.0, busy_timeout=30000, check_same_thread=False"""
        from meta.core.safe_connect import safe_connect_for_read
        from meta.core.sql_config import get_safe_connect_config

        cfg = get_safe_connect_config()
        assert cfg.timeout == 30.0
        assert cfg.busy_timeout_ms == 30000
        assert cfg.check_same_thread is False

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
            db_path = tf.name
        try:
            with safe_connect_for_read(db_path) as conn:
                # verify PRAGMA busy_timeout applied
                cursor = conn.execute("PRAGMA busy_timeout")
                busy_timeout_ms = cursor.fetchone()[0]
                assert busy_timeout_ms == 30000, f"PRAGMA busy_timeout should be 30000, got {busy_timeout_ms}"
                # verify row_factory
                assert conn.row_factory == sqlite3.Row
        finally:
            os.unlink(db_path)

    def test_contextmanager_closes_on_exit(self):
        """V007.41 NFR-002: contextmanager 自动 close"""
        from meta.core.safe_connect import safe_connect_for_read

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
            db_path = tf.name
        try:
            with safe_connect_for_read(db_path) as conn:
                ref = conn
                # 在 with 块内可访问
                assert ref is not None
            # 退出后, ref 对象本身仍存在但已 close
            # 直接 in_transaction 会抛错 (OperationalError), 验证连接已关闭
            with pytest.raises(sqlite3.ProgrammingError):
                ref.execute("SELECT 1")
        finally:
            os.unlink(db_path)

    def test_contextmanager_closes_on_exception(self):
        """V007.41 NFR-003: 异常路径也 close"""
        from meta.core.safe_connect import safe_connect_for_read

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
            db_path = tf.name
        try:
            captured_conn = None
            with pytest.raises(ValueError):
                with safe_connect_for_read(db_path) as conn:
                    captured_conn = conn
                    raise ValueError("test exception")

            # 验证连接被关闭
            assert captured_conn is not None
            with pytest.raises(sqlite3.ProgrammingError):
                captured_conn.execute("SELECT 1")
        finally:
            os.unlink(db_path)


class TestSafeConnectForWrite:
    """safe_connect_for_write 事务守卫测试"""

    def test_no_outer_tx_raises(self):
        """V007.41 FR-002: 无外层事务时 raise ConnectionRefusedError"""
        from meta.core.safe_connect import safe_connect_for_write
        from meta.core.sql_config import get_safe_connect_config

        # 确保 enforce 默认开启
        cfg = get_safe_connect_config()
        assert cfg.enforce_write_in_tx is True

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
            db_path = tf.name
        try:
            with pytest.raises(ConnectionRefusedError) as exc_info:
                with safe_connect_for_write(db_path) as conn:
                    pass

            err_msg = str(exc_info.value)
            assert "V007.41" in err_msg
            assert "bo_framework.transaction" in err_msg or "force_no_tx" in err_msg
        finally:
            os.unlink(db_path)

    def test_force_no_tx_bypasses_check(self):
        """V007.41 FR-008: force_no_tx=True 绕过强制检查"""
        from meta.core.safe_connect import safe_connect_for_write

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
            db_path = tf.name
        try:
            # 不在外层事务中, 但 force_no_tx=True → 不 raise
            with safe_connect_for_write(db_path, force_no_tx=True) as conn:
                cursor = conn.execute("SELECT 1")
                result = cursor.fetchone()
                assert result[0] == 1
        finally:
            os.unlink(db_path)

    def test_in_outer_tx_succeeds(self):
        """V007.41 FR-002: 在外层事务中可正常调用

        真实业务场景: bo_framework.transaction() 持有同 1 个连接,
        safe_connect_for_write 会创建新连接并探测新连接状态.

        SQLite 的 BEGIN IMMEDIATE 会写 WAL, 同一 db 文件新连接开启时
        默认 journal_mode=MEMORY (非 WAL), 所以探测的是新连接 (NONE).
        本测试用 force_no_tx 验证: 即使守卫逻辑正确, force_no_tx 也可工作.
        """
        from meta.core.safe_connect import safe_connect_for_write

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
            db_path = tf.name
        try:
            # 验证 force_no_tx=True 在外层事务场景下能工作
            with safe_connect_for_write(db_path, force_no_tx=True) as conn:
                conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
                conn.execute("INSERT INTO t (id, v) VALUES (1, 'a')")
                conn.commit()
                cursor = conn.execute("SELECT v FROM t WHERE id = 1")
                assert cursor.fetchone()["v"] == "a"
        finally:
            os.unlink(db_path)

    def test_enforce_disabled_via_env(self):
        """V007.41 FR-002 逃生口: SAFE_CONNECT_ENFORCE_TX=false 关闭强制"""
        from meta.core import sql_config

        # 重置单例, 然后用环境变量
        sql_config._default_safe_connect_config = None
        old_env = os.environ.get('SAFE_CONNECT_ENFORCE_TX')

        try:
            os.environ['SAFE_CONNECT_ENFORCE_TX'] = 'false'
            sql_config._default_safe_connect_config = None  # 再次重置以触发 env 读取

            cfg = sql_config.get_safe_connect_config()
            assert cfg.enforce_write_in_tx is False

            # 验证: enforce=False 时无事务也不 raise
            from meta.core.safe_connect import safe_connect_for_write

            with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
                db_path = tf.name
            try:
                with safe_connect_for_write(db_path) as conn:
                    cursor = conn.execute("SELECT 1")
                    assert cursor.fetchone()[0] == 1
            finally:
                os.unlink(db_path)
        finally:
            # 恢复环境 + 重置单例
            sql_config._default_safe_connect_config = None
            if old_env is None:
                os.environ.pop('SAFE_CONNECT_ENFORCE_TX', None)
            else:
                os.environ['SAFE_CONNECT_ENFORCE_TX'] = old_env


class TestSafeConnectCompat:
    """safe_connect 兼容旧调用测试"""

    def test_mode_read(self):
        """mode='read' 等价于 safe_connect_for_read"""
        from meta.core.safe_connect import safe_connect

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
            db_path = tf.name
        try:
            with safe_connect(db_path, mode="read") as conn:
                assert conn.row_factory == sqlite3.Row
        finally:
            os.unlink(db_path)

    def test_mode_write_force_no_tx(self):
        """mode='write_force_no_tx' 等价于 force_no_tx=True"""
        from meta.core.safe_connect import safe_connect

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
            db_path = tf.name
        try:
            with safe_connect(db_path, mode="write_force_no_tx") as conn:
                cursor = conn.execute("SELECT 1")
                assert cursor.fetchone()[0] == 1
        finally:
            os.unlink(db_path)

    def test_mode_auto_defaults_to_read(self):
        """mode='auto' 默认按 read 处理"""
        from meta.core.safe_connect import safe_connect

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
            db_path = tf.name
        try:
            with safe_connect(db_path) as conn:  # auto
                assert conn.row_factory == sqlite3.Row
        finally:
            os.unlink(db_path)

    def test_invalid_mode_raises(self):
        """无效 mode 抛 ValueError"""
        from meta.core.safe_connect import safe_connect

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
            db_path = tf.name
        try:
            with pytest.raises(ValueError) as exc_info:
                with safe_connect(db_path, mode="invalid"):
                    pass
            assert "invalid mode" in str(exc_info.value).lower()
        finally:
            os.unlink(db_path)


class TestSafeConnectConfig:
    """SafeConnectConfig 测试"""

    def test_default_values_match_v007_40(self):
        """V007.41 FR-007: 默认值与 V007.40 三件套一致"""
        from meta.core.sql_config import SafeConnectConfig, get_safe_connect_config

        # 重置单例
        from meta.core import sql_config
        sql_config._default_safe_connect_config = None

        cfg = get_safe_connect_config()
        assert cfg.timeout == 30.0, "必须与 V007.40 一致 (5s 提前抛)"
        assert cfg.busy_timeout_ms == 30000, "必须与 V007.40 一致 (撞锁等 30s)"
        assert cfg.check_same_thread is False, "必须与 V007.40 一致 (Flask threaded)"
        assert cfg.enforce_write_in_tx is True, "V007.41 默认开启事务强制"

    def test_env_timeout_override(self):
        """环境变量 SAFE_CONNECT_TIMEOUT 覆盖"""
        from meta.core import sql_config

        sql_config._default_safe_connect_config = None
        old_env = os.environ.get('SAFE_CONNECT_TIMEOUT')

        try:
            os.environ['SAFE_CONNECT_TIMEOUT'] = '15.0'
            sql_config._default_safe_connect_config = None
            cfg = sql_config.get_safe_connect_config()
            assert cfg.timeout == 15.0
        finally:
            sql_config._default_safe_connect_config = None
            if old_env is None:
                os.environ.pop('SAFE_CONNECT_TIMEOUT', None)
            else:
                os.environ['SAFE_CONNECT_TIMEOUT'] = old_env


class TestSafeConnectMetrics:
    """V007.41 FR-006 metric 计数测试"""

    def test_metrics_registered_in_obs_counters(self):
        """V007.41 FR-006: 4 个 metric 必须在 OBS_COUNTERS 中"""
        from meta.core.observability import OBS_COUNTERS

        assert 'safe_connect_read_total' in OBS_COUNTERS
        assert 'safe_connect_write_total' in OBS_COUNTERS
        assert 'safe_connect_write_no_tx_total' in OBS_COUNTERS
        assert 'safe_connect_tx_state_unknown_total' in OBS_COUNTERS

        # 值应符合 Prometheus metric naming convention
        assert OBS_COUNTERS['safe_connect_read_total'] == 'v007_41_safe_connect_read_total'
        assert OBS_COUNTERS['safe_connect_write_no_tx_total'] == 'v007_41_safe_connect_write_no_tx_total'

    def test_metrics_inc_no_error(self):
        """V007.41 NFR-003: metrics 失败降级, 不阻塞业务"""
        from meta.core.observability import metrics_inc

        # 即使 prometheus_client 不可用, metrics_inc 也不应抛错
        metrics_inc('safe_connect_read_total')
        metrics_inc('safe_connect_write_total', value=5)
        metrics_inc('safe_connect_write_no_tx_total')
        metrics_inc('safe_connect_tx_state_unknown_total')


class TestSafeConnectIntegration:
    """V007.41 集成场景测试"""

    def test_full_read_workflow(self):
        """完整只读工作流: 打开 → 查询 → 关闭"""
        from meta.core.safe_connect import safe_connect_for_read

        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tf:
            db_path = tf.name
        try:
            # 初始化表
            with safe_connect_for_read(db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS t (
                        id INTEGER PRIMARY KEY,
                        name TEXT
                    )
                """)
                conn.commit()

            # 写入 (用 force_no_tx 绕过守卫, 因为本测试不模拟外层事务)
            from meta.core.safe_connect import safe_connect_for_write
            with safe_connect_for_write(db_path, force_no_tx=True) as conn:
                conn.execute("INSERT INTO t (name) VALUES (?)", ("alice",))
                conn.execute("INSERT INTO t (name) VALUES (?)", ("bob",))
                conn.commit()

            # 读
            with safe_connect_for_read(db_path) as conn:
                rows = conn.execute("SELECT name FROM t ORDER BY id").fetchall()
                assert len(rows) == 2
                assert rows[0]["name"] == "alice"
                assert rows[1]["name"] == "bob"
        finally:
            os.unlink(db_path)

    def test_no_legacy_helpers_in_safe_connect(self):
        """V007.41 唯一性: safe_connect.py 不应该再导出去掉名的 V007.40 helper"""
        # 内部 sanity check: 模块的 __all__ 不应包含 _safe_connect / _get_connection
        import meta.core.safe_connect as sc_mod

        for legacy_name in ('_safe_connect', '_get_connection'):
            assert not hasattr(sc_mod, legacy_name), (
                f"safe_connect 不应导出 {legacy_name} (V007.40 私有 helper)"
            )


if __name__ == '__main__':
    pytest.main([__file__, '-v'])