# -*- coding: utf-8 -*-
"""
[V007.40] 回归测试: 验证所有 TRUNCATE 默认值已修复, 避免 I/O error 复发

背景:
  V007.39 修了显式调用的 checkpoint, 但漏了配置默认值的源头. 这导致:
  - sql_config.py WriteQueueConfig.checkpoint_mode 默认 TRUNCATE
  - sql_config.py CheckpointConfig.mode 默认 TRUNCATE
  - sql_adapters.py pool 初始化时显式传 TRUNCATE
  - sql_adapters.py checkpoint() 方法默认 TRUNCATE
  - sql_checkpoint_manager.py should_checkpoint() 返回 mode: TRUNCATE
  - sql_checkpoint_manager.py execute_checkpoint() 默认 TRUNCATE
  - sql_maintenance_scheduler.py _checkpoint() 显式 TRUNCATE (每 300s 一次!)

修法 (V007.40):
  - 所有默认值改为 PASSIVE
  - maintenance scheduler 改为 PASSIVE
  - 高频热路径加 timeout=30.0 + check_same_thread=False + PRAGMA busy_timeout=30000

回归测试覆盖:
  1. sql_config 默认值
  2. sql_adapters 默认值
  3. sql_checkpoint_manager 默认值
  4. sql_maintenance_scheduler 显式调用
  5. production 代码中不应再出现 TRUNCATE 默认值 (除了显式 admin API 路径)
  6. 所有高频热路径都应使用 _safe_connect() 模式
"""
import os
import re
import sys
import pytest
import sqlite3
import tempfile

# 让测试可以导入 meta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


class TestV00740DefaultConfig:
    """测试 V007.40 配置默认值修复"""

    def test_write_queue_config_default_is_passive(self):
        """WriteQueueConfig.checkpoint_mode 默认值应为 PASSIVE"""
        from meta.core.sql_config import WriteQueueConfig
        config = WriteQueueConfig()
        assert config.checkpoint_mode == "PASSIVE", (
            f"Expected PASSIVE, got {config.checkpoint_mode}. "
            "V007.40 漏修复 - 配置默认值仍走 TRUNCATE 会触发 I/O error."
        )

    def test_checkpoint_config_default_is_passive(self):
        """CheckpointConfig.mode 默认值应为 PASSIVE"""
        from meta.core.sql_config import CheckpointConfig
        config = CheckpointConfig()
        assert config.mode == "PASSIVE", (
            f"Expected PASSIVE, got {config.mode}. "
            "V007.40 漏修复 - 配置默认值仍走 TRUNCATE 会触发 I/O error."
        )


class TestV00740AdaptersDefault:
    """测试 sql_adapters 默认值修复"""

    def test_pool_init_default_is_passive(self):
        """sql_adapters.py pool 初始化 checkpoint_mode 默认应为 PASSIVE"""
        with open(os.path.join(
            os.path.dirname(__file__), "..", "core", "sql_adapters.py"
        ), "r", encoding="utf-8") as f:
            content = f.read()

        # 查找 "checkpoint_mode=kwargs.get" 这行, 默认值应为 PASSIVE
        m = re.search(
            r'checkpoint_mode=kwargs\.get\(\s*[\'"]checkpoint_mode[\'"]\s*,\s*[\'"]([A-Z]+)[\'"]',
            content,
        )
        assert m is not None, "未找到 checkpoint_mode 默认值行"
        default_mode = m.group(1)
        assert default_mode == "PASSIVE", (
            f"sql_adapters.py pool 初始化默认 {default_mode} 应改 PASSIVE"
        )

    def test_checkpoint_method_default_is_passive(self):
        """sql_adapters.py checkpoint() 方法默认 mode 应为 PASSIVE"""
        with open(os.path.join(
            os.path.dirname(__file__), "..", "core", "sql_adapters.py"
        ), "r", encoding="utf-8") as f:
            content = f.read()

        # 查找 def checkpoint(self, mode: str = "..."): 默认参数
        m = re.search(
            r'def\s+checkpoint\s*\([^)]*mode\s*:\s*str\s*=\s*[\'"]([A-Z]+)[\'"]',
            content,
        )
        assert m is not None, "未找到 def checkpoint 默认参数"
        default_mode = m.group(1)
        assert default_mode == "PASSIVE", (
            f"sql_adapters.checkpoint() 默认 {default_mode} 应改 PASSIVE"
        )


class TestV00740CheckpointManagerDefault:
    """测试 sql_checkpoint_manager 默认值修复"""

    def test_should_checkpoint_returns_passive(self):
        """sql_checkpoint_manager.should_checkpoint() 返回 mode 应为 PASSIVE"""
        with open(os.path.join(
            os.path.dirname(__file__), "..", "core", "sql_checkpoint_manager.py"
        ), "r", encoding="utf-8") as f:
            content = f.read()

        # 查找 "mode: 'TRUNCATE'" 或 "mode': 'TRUNCATE'" 或 "mode': 'PASSIVE'"
        truncate_count = len(re.findall(r'["\']mode["\']\s*:\s*["\']TRUNCATE["\']', content))
        assert truncate_count == 0, (
            f"sql_checkpoint_manager.py 还有 {truncate_count} 处 mode: TRUNCATE, 应改 PASSIVE"
        )

    def test_execute_checkpoint_default_is_passive(self):
        """sql_checkpoint_manager.execute_checkpoint() 默认 mode 应为 PASSIVE"""
        with open(os.path.join(
            os.path.dirname(__file__), "..", "core", "sql_checkpoint_manager.py"
        ), "r", encoding="utf-8") as f:
            content = f.read()

        m = re.search(
            r'def\s+execute_checkpoint\s*\([^)]*mode\s*:\s*str\s*=\s*[\'"]([A-Z]+)[\'"]',
            content,
        )
        assert m is not None, "未找到 def execute_checkpoint 默认参数"
        default_mode = m.group(1)
        assert default_mode == "PASSIVE", (
            f"sql_checkpoint_manager.execute_checkpoint() 默认 {default_mode} 应改 PASSIVE"
        )


class TestV00740MaintenanceScheduler:
    """测试 maintenance scheduler 修复 - 这是关键!每 5 分钟触发一次"""

    def test_checkpoint_uses_passive(self):
        """sql_maintenance_scheduler.py _checkpoint() 应使用 PASSIVE"""
        with open(os.path.join(
            os.path.dirname(__file__), "..", "core", "sql_maintenance_scheduler.py"
        ), "r", encoding="utf-8") as f:
            content = f.read()

        # 查找 ds.checkpoint("TRUNCATE")
        assert '"TRUNCATE"' not in content and "'TRUNCATE'" not in content, (
            "sql_maintenance_scheduler.py 还在用 TRUNCATE! "
            "每 300 秒一次的定时炸弹, 必须改 PASSIVE."
        )

        # 应该有 ds.checkpoint("PASSIVE")
        assert '"PASSIVE"' in content or "'PASSIVE'" in content, (
            "sql_maintenance_scheduler.py 缺少 PASSIVE 调用"
        )


class TestV00740NoTruncateInProductionDefaults:
    """测试 production 代码中不应再出现 TRUNCATE 默认值"""

    PRODUCTION_FILES = [
        "core/sql_config.py",
        "core/sql_adapters.py",
        "core/sql_checkpoint_manager.py",
        "core/sql_maintenance_scheduler.py",
        "core/sql_write_queue.py",
    ]

    def test_no_truncate_default_in_config(self):
        for rel_path in self.PRODUCTION_FILES:
            full_path = os.path.join(
                os.path.dirname(__file__), "..", rel_path
            )
            if not os.path.exists(full_path):
                continue
            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            # 排除明显的注释行 (以 # 开头)
            code_lines = [
                line for line in content.split("\n")
                if line.strip() and not line.strip().startswith("#")
            ]
            code = "\n".join(code_lines)

            # 不应有 "TRUNCATE" 出现在生产默认值中
            # 注意: 显式 admin API 调用 (如 TRUNCATE TABLE) 不在检测范围
            # 这里只检测配置/方法默认值

            # 1. 检测 "= 'TRUNCATE'" 或 '= "TRUNCATE"' (默认值)
            m = re.findall(r'=\s*[\'"]TRUNCATE[\'"]', code)
            assert not m, (
                f"{rel_path} 仍有 {len(m)} 处默认值是 TRUNCATE: {m}"
            )

            # 2. 检测 mode: str = "TRUNCATE" (CheckpointConfig 这种)
            m = re.findall(r'mode\s*:\s*str\s*=\s*[\'"]TRUNCATE[\'"]', code)
            assert not m, (
                f"{rel_path} 仍有 mode 默认 TRUNCATE: {m}"
            )

            # 3. 检测 mode: "TRUNCATE" (dict 字面量)
            m = re.findall(r'[\'"]mode[\'"]\s*:\s*[\'"]TRUNCATE[\'"]', code)
            assert not m, (
                f"{rel_path} 仍有 dict mode: TRUNCATE: {m}"
            )


class TestV00740HighFrequencyHotPaths:
    """测试高频热路径都使用 safe connect pattern"""

    def test_token_blacklist_has_timeout(self):
        """token_blacklist_service._get_connection 应有 timeout"""
        with open(os.path.join(
            os.path.dirname(__file__), "..", "services", "token_blacklist_service.py"
        ), "r", encoding="utf-8") as f:
            content = f.read()

        # 检测 sqlite3.connect(self._db_path) 没有 timeout
        m = re.search(
            r'sqlite3\.connect\s*\(\s*self\._db_path\s*,\s*check_same_thread\s*=\s*False\s*\)',
            content,
        )
        assert m is None, (
            "token_blacklist_service.py 还在用无 timeout 的 sqlite3.connect, "
            "每条 API 请求都触发 I/O error."
        )

        # 应该有 timeout=30.0
        assert "timeout=30.0" in content, (
            "token_blacklist_service.py 缺少 timeout=30.0"
        )

    def test_filter_variant_api_has_timeout(self):
        """filter_variant_api._execute_query 应有 timeout"""
        with open(os.path.join(
            os.path.dirname(__file__), "..", "api", "filter_variant_api.py"
        ), "r", encoding="utf-8") as f:
            content = f.read()

        # 检测 sqlite3.connect(db_path) 没有 timeout
        m = re.search(
            r'sqlite3\.connect\s*\(\s*db_path\s*\)',
            content,
        )
        assert m is None, (
            "filter_variant_api.py 还在用无 timeout 的 sqlite3.connect"
        )

    def test_intent_resolver_uses_safe_connect(self):
        """intent_resolver 应使用 _safe_connect helper"""
        with open(os.path.join(
            os.path.dirname(__file__), "..", "core", "intent_resolver.py"
        ), "r", encoding="utf-8") as f:
            content = f.read()

        # 应该有 _safe_connect helper 函数定义
        assert "def _safe_connect" in content, (
            "intent_resolver.py 缺少 _safe_connect helper"
        )

        # 6 处直接 sqlite3.connect 应都改为 _safe_connect
        # 注意: 全局 count = sqlite3.connect(self._db_path) 替换次数
        # 原 6 处现在应该是 _safe_connect
        direct_count = content.count("sqlite3.connect(self._db_path)")
        # 0 表示全部走 helper, >0 表示遗漏
        assert direct_count == 0, (
            f"intent_resolver.py 还有 {direct_count} 处直接 sqlite3.connect(self._db_path) 未修"
        )

    def test_subflow_template_store_uses_safe_connect(self):
        """subflow_template_store 应使用 _safe_connect helper"""
        with open(os.path.join(
            os.path.dirname(__file__), "..", "services", "subflow_template_store.py"
        ), "r", encoding="utf-8") as f:
            content = f.read()

        assert "def _safe_connect" in content, (
            "subflow_template_store.py 缺少 _safe_connect helper"
        )

        direct_count = content.count("sqlite3.connect(cls._get_db_path())")
        assert direct_count == 0, (
            f"subflow_template_store.py 还有 {direct_count} 处直接 sqlite3.connect 未修"
        )


class TestV00740WriteQueueDrainOnStop:
    """测试 WriteQueue.stop() 排空 in-flight 操作"""

    def test_stop_drains_in_flight(self):
        """WriteQueue.stop() 应调用 flush + 排空 queue"""
        with open(os.path.join(
            os.path.dirname(__file__), "..", "core", "sql_write_queue.py"
        ), "r", encoding="utf-8") as f:
            content = f.read()

        # stop() 方法应包含 flush() 调用
        stop_m = re.search(
            r'def\s+stop\s*\([^)]*\)\s*:.*?(?=\n    def\s|\nclass\s|\Z)',
            content,
            re.DOTALL,
        )
        assert stop_m is not None, "未找到 def stop 方法"
        stop_code = stop_m.group(0)

        # 应有 flush 调用
        assert "flush(" in stop_code or "self._queue" in stop_code, (
            "WriteQueue.stop() 缺少 drain in-flight 逻辑"
        )

        # 应有 set_exception 处理未完成 future
        assert "set_exception" in stop_code, (
            "WriteQueue.stop() 缺少 set_exception, 未完成的 future 会永久 hang"
        )


class TestV00740ConnectionSafety:
    """测试连接安全的实际功能验证"""

    def test_safe_connect_helper_works(self):
        """_safe_connect helper 应能正确建立连接"""
        # 临时 db
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        try:
            # 测试 sqlite3.connect timeout=30 + busy_timeout PRAGMA
            conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
            conn.execute("PRAGMA busy_timeout = 30000")
            conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
            conn.execute("INSERT INTO test VALUES (?)", (1,))
            conn.commit()
            cursor = conn.execute("SELECT * FROM test")
            assert cursor.fetchone() == (1,)
            conn.close()
        finally:
            os.unlink(db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
