import pytest

pytestmark = pytest.mark.integration

import os
import pytest
from meta.core.sql_config import (
    PoolConfig,
    WriteQueueConfig,
    CheckpointConfig,
    MonitorConfig,
    DatabaseConfig,
    get_database_config,
    set_database_config,
)


class TestPoolConfig:
    """测试连接池配置"""

    def test_default_values(self):
        """测试默认值"""
        config = PoolConfig()
        assert config.max_readers == 5
        assert config.idle_timeout == 300.0
        assert config.max_lifetime == 3600.0
        assert config.acquire_timeout == 30.0
        assert config.db_timeout == 30.0
        assert config.wal_auto_checkpoint == 1000

    def test_custom_values(self):
        """测试自定义值"""
        config = PoolConfig(max_readers=20, idle_timeout=600.0)
        assert config.max_readers == 20
        assert config.idle_timeout == 600.0


class TestWriteQueueConfig:
    """测试写队列配置"""

    def test_default_values(self):
        config = WriteQueueConfig()
        assert config.max_queue_size == 1000
        assert config.submit_timeout == 30.0
        assert config.operation_timeout == 60.0
        assert config.checkpoint_interval == 50
        assert config.checkpoint_mode == "TRUNCATE"

    def test_checkpoint_mode_options(self):
        """测试检查点模式选项"""
        for mode in ["TRUNCATE", "PASSIVE", "RESTART"]:
            config = WriteQueueConfig(checkpoint_mode=mode)
            assert config.checkpoint_mode == mode


class TestMonitorConfig:
    """测试监控配置"""

    def test_default_values(self):
        config = MonitorConfig()
        assert config.enabled is True
        assert config.slow_query_threshold_ms == 100.0
        assert config.slow_query_alert_threshold == 10
        assert config.slow_query_buffer_size == 200
        assert config.metrics_collect_interval_seconds == 15.0

    def test_disable_monitor(self):
        config = MonitorConfig(enabled=False)
        assert config.enabled is False


class TestDatabaseConfig:
    """测试数据库总配置"""

    def test_default_config(self):
        config = DatabaseConfig()
        assert config.use_pool is True
        assert isinstance(config.pool, PoolConfig)
        assert isinstance(config.write_queue, WriteQueueConfig)
        assert isinstance(config.checkpoint, CheckpointConfig)
        assert isinstance(config.monitor, MonitorConfig)

    def test_custom_db_path(self):
        config = DatabaseConfig(db_path="/tmp/test.db")
        assert config.db_path == "/tmp/test.db"

    def test_to_connect_kwargs(self):
        """测试转换为连接参数"""
        config = DatabaseConfig(
            db_path=":memory:",
            pool=PoolConfig(max_readers=10),
        )
        kwargs = config.to_connect_kwargs()
        assert kwargs["path"] == ":memory:"
        assert kwargs["max_readers"] == 10
        assert "idle_timeout" in kwargs
        assert "acquire_timeout" in kwargs

    def test_from_env_defaults(self):
        """测试从环境变量加载默认值"""
        original_env = dict(os.environ)
        try:
            for key in list(os.environ.keys()):
                if key.startswith("DATABASE_") or key == "SQLITE_DB_PATH":
                    del os.environ[key]

            config = DatabaseConfig.from_env()
            assert config.use_pool is True
            assert config.pool.max_readers == 5
        finally:
            os.environ.clear()
            os.environ.update(original_env)

    def test_from_env_with_pool_settings(self):
        """测试从环境变量加载连接池设置"""
        original_env = dict(os.environ)
        try:
            os.environ["DATABASE_POOL_MAX_READERS"] = "20"
            os.environ["DATABASE_POOL_IDLE_TIMEOUT"] = "600"
            os.environ["DATABASE_USE_POOL"] = "false"

            config = DatabaseConfig.from_env()
            assert config.pool.max_readers == 20
            assert config.pool.idle_timeout == 600.0
            assert config.use_pool is False
        finally:
            os.environ.clear()
            os.environ.update(original_env)


class TestDatabaseConfigSingleton:
    """测试数据库配置单例模式"""

    def setup_method(self):
        from meta.core import sql_config
        sql_config._default_config = None

    def test_get_database_config_returns_singleton(self):
        """测试单例模式"""
        config1 = get_database_config()
        config2 = get_database_config()
        assert config1 is config2

    def test_set_database_config(self):
        """测试设置自定义配置"""
        custom = DatabaseConfig(db_path="/custom/path.db")
        set_database_config(custom)
        
        retrieved = get_database_config()
        assert retrieved.db_path == "/custom/path.db"

    def teardown_method(self):
        from meta.core import sql_config
        sql_config._default_config = None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
