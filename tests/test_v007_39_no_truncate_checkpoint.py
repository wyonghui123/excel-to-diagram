# -*- coding: utf-8 -*-
"""
V007.39 BUG-FIX 验证: 运行时禁止 wal_checkpoint(TRUNCATE)

根因: WriteQueue 每 10 commit 调用 wal_checkpoint(TRUNCATE),
     TRUNCATE 截断 WAL 文件 → 读连接 mmap 视图失效 → disk I/O error

修复: 所有运行时 checkpoint 改为 PASSIVE (不阻塞读, 不截断 WAL)
"""
import ast
import re
import os
import sys

import pytest

# 项目根
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class TestV00739WriteQueueConfig:
    """WriteQueueConfig 默认 checkpoint_mode 必须是 PASSIVE"""

    def test_01_default_checkpoint_mode_is_passive(self):
        from meta.core.sql_write_queue import WriteQueueConfig
        cfg = WriteQueueConfig()
        assert cfg.checkpoint_mode == "PASSIVE", \
            f"Expected PASSIVE, got {cfg.checkpoint_mode!r}"

    def test_02_checkpoint_method_default_is_passive(self):
        from meta.core.sql_write_queue import WriteQueue
        import inspect
        sig = inspect.signature(WriteQueue.checkpoint)
        default_mode = sig.parameters['mode'].default
        assert default_mode == "PASSIVE", \
            f"WriteQueue.checkpoint(mode=) default should be PASSIVE, got {default_mode!r}"


class TestV00739NoTruncateInProductionCode:
    """生产代码中不应有 wal_checkpoint(TRUNCATE) 调用 (迁移脚本除外)"""

    # 允许 TRUNCATE 的路径 (迁移脚本, 一次性工具)
    ALLOWED_PATTERNS = [
        r'meta[/\\]scripts[/\\]',      # 迁移脚本
        r'meta[/\\]migrations[/\\]',   # 数据库迁移
        r'tests[/\\]',                 # 测试代码
        r'verify_disk_io_root_cause',  # 验证脚本 (证明 bug 存在的)
        r'deploy_bundle[/\\]',         # 生成文件 (rebuild_bundle 复制)
        r'__pycache__',                # 缓存
    ]

    # 必须检查的生产代码目录
    PRODUCTION_DIRS = [
        os.path.join(ROOT, 'meta', 'core'),
        os.path.join(ROOT, 'meta', 'services'),
        os.path.join(ROOT, 'meta', 'api'),
        os.path.join(ROOT, 'meta', 'server.py'),
        os.path.join(ROOT, 'tools', 'log_service.py'),
    ]

    def test_01_no_truncate_in_production_code(self):
        """所有生产代码文件中不应包含 wal_checkpoint(TRUNCATE)"""
        violations = []
        for prod_path in self.PRODUCTION_DIRS:
            if os.path.isfile(prod_path):
                files = [prod_path]
            elif os.path.isdir(prod_path):
                files = []
                for dirpath, dirnames, filenames in os.walk(prod_path):
                    # 跳过 __pycache__
                    dirnames[:] = [d for d in dirnames if d != '__pycache__']
                    for fn in filenames:
                        if fn.endswith('.py'):
                            files.append(os.path.join(dirpath, fn))
            else:
                continue

            for fpath in files:
                # 跳过允许的路径
                rel = os.path.relpath(fpath, ROOT)
                if any(re.search(p, rel) for p in self.ALLOWED_PATTERNS):
                    continue

                with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # 检查 wal_checkpoint(TRUNCATE) 或 wal_checkpoint("TRUNCATE")
                for i, line in enumerate(content.split('\n'), 1):
                    if 'wal_checkpoint' in line and 'TRUNCATE' in line:
                        # 排除注释行
                        stripped = line.strip()
                        if stripped.startswith('#'):
                            continue
                        violations.append(f"{rel}:{i}: {stripped}")

        assert not violations, \
            f"Found wal_checkpoint(TRUNCATE) in production code:\n" + \
            "\n".join(violations)


class TestV00739NoFullCheckpointInMonitor:
    """db_health_monitor 不应使用 FULL 模式 (会阻塞读)"""

    def test_01_monitor_uses_passive(self):
        fpath = os.path.join(ROOT, 'meta', 'core', 'db_health_monitor.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 找所有 wal_checkpoint 调用
        matches = re.findall(r'wal_checkpoint\((\w+)\)', content)
        for mode in matches:
            assert mode in ('PASSIVE',), \
                f"db_health_monitor should only use PASSIVE, found {mode}"


class TestV00739AsyncAuditWriterNoPragmaJournalMode:
    """async_audit_writer 不应重复执行 PRAGMA journal_mode=WAL"""

    def test_01_no_journal_mode_wal_in_audit_writer(self):
        fpath = os.path.join(ROOT, 'meta', 'services', 'async_audit_writer.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查是否有 PRAGMA journal_mode 调用 (非注释行, pool 已处理)
        for i, line in enumerate(content.split('\n'), 1):
            stripped = line.strip()
            if 'PRAGMA journal_mode' in stripped and not stripped.startswith('#'):
                pytest.fail(
                    f"async_audit_writer.py:{i} executes PRAGMA journal_mode "
                    f"(pool handles it with idempotent protection): {stripped}"
                )


class TestV00739DatabaseApiDefaultPassive:
    """database_api.py /wal-checkpoint 端点默认 mode 应为 PASSIVE"""

    def test_01_default_mode_is_passive(self):
        fpath = os.path.join(ROOT, 'meta', 'api', 'database_api.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 找 request.args.get('mode', ...) 的默认值
        m = re.search(r"request\.args\.get\('mode',\s*'(\w+)'\)", content)
        assert m, "Cannot find mode default in database_api.py"
        assert m.group(1) == 'PASSIVE', \
            f"database_api.py /wal-checkpoint default mode should be PASSIVE, got {m.group(1)}"


class TestV00739SqlAdaptersNoDuplicateCheckpoint:
    """sql_adapters.py _do_write 不应有重复的 checkpoint 逻辑"""

    def test_01_no_checkpoint_in_do_write(self):
        fpath = os.path.join(ROOT, 'meta', 'core', 'sql_adapters.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        # 找 _do_write 函数
        idx = content.find('def _do_write')
        if idx < 0:
            pytest.skip("_do_write not found (code structure changed)")

        # 取函数体 (到下一个同级别 def)
        func_body = content[idx:]
        # 检查是否还有 wal_checkpoint 调用
        assert 'wal_checkpoint' not in func_body[:2000], \
            "_do_write should NOT contain wal_checkpoint (WriteQueue.commit handles it)"


class TestV00739ServerNoTruncateCheckpoint:
    """server.py 启动和关闭不应使用 TRUNCATE"""

    def test_01_server_uses_passive(self):
        fpath = os.path.join(ROOT, 'meta', 'server.py')
        with open(fpath, 'r', encoding='utf-8') as f:
            content = f.read()

        for i, line in enumerate(content.split('\n'), 1):
            stripped = line.strip()
            if 'wal_checkpoint' in stripped and 'TRUNCATE' in stripped:
                if not stripped.startswith('#'):
                    pytest.fail(f"server.py:{i} still uses TRUNCATE: {stripped}")
