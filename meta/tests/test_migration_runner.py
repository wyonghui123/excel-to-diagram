# -*- coding: utf-8 -*-
"""
COV-007: MigrationRunner 8 个单元测试

测试 meta.core.migration_runner.MigrationRunner
"""
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.unit


def _make_cursor(rows):
    """模拟 DB cursor（execute 返回的对象）"""
    cursor = MagicMock()
    cursor.fetchall = MagicMock(return_value=rows)
    cursor.fetchone = MagicMock(return_value=rows[0] if rows else None)
    return cursor


def _make_data_source(executed_migrations=None, executed_one=None):
    """构造 data_source mock：execute() 返回 cursor"""
    ds = MagicMock()
    ds.in_transaction = False
    ds.commit = MagicMock()
    if executed_migrations is not None:
        # SELECT migration_name 返回多行
        cursor = _make_cursor([(name,) for name in executed_migrations])
        ds.execute = MagicMock(return_value=cursor)
    elif executed_one is not None:
        # SELECT 1 WHERE 返回单行
        cursor = _make_cursor([(1,)] if executed_one else [])
        ds.execute = MagicMock(return_value=cursor)
    else:
        # 默认：execute 总是返回一个空 cursor
        ds.execute = MagicMock(return_value=_make_cursor([]))
    return ds


class TestMigrationRunner:
    """MigrationRunner 单元测试 (COV-007)"""

    def test_ensure_migrations_table_executes_ddl(self):
        """ensure_migrations_table 执行 CREATE TABLE"""
        from meta.core.migration_runner import MigrationRunner
        ds = _make_data_source()
        runner = MigrationRunner(ds, migrations_dir=tempfile.mkdtemp())
        runner.ensure_migrations_table()
        ds.execute.assert_called()
        sql = ds.execute.call_args[0][0]
        assert 'CREATE TABLE' in sql
        assert 'schema_migrations' in sql

    def test_get_executed_migrations_returns_list(self):
        """get_executed_migrations 返回 list[str]"""
        from meta.core.migration_runner import MigrationRunner
        ds = _make_data_source(executed_migrations=['001_init.sql', '002_add_user.sql'])
        runner = MigrationRunner(ds, migrations_dir=tempfile.mkdtemp())
        result = runner.get_executed_migrations()
        assert isinstance(result, list)
        assert '001_init.sql' in result
        assert '002_add_user.sql' in result

    def test_is_migration_executed_returns_bool(self):
        """is_migration_executed 返回 bool"""
        from meta.core.migration_runner import MigrationRunner
        # 第一次查询返回行（有），第二次返回空（无）
        ds1 = _make_data_source(executed_one=True)
        runner1 = MigrationRunner(ds1, migrations_dir=tempfile.mkdtemp())
        assert runner1.is_migration_executed('001_init.sql') is True

        ds2 = _make_data_source(executed_one=False)
        runner2 = MigrationRunner(ds2, migrations_dir=tempfile.mkdtemp())
        assert runner2.is_migration_executed('999_not.sql') is False

    def test_record_migration_inserts_row(self):
        """record_migration 调用 execute 插入记录"""
        from meta.core.migration_runner import MigrationRunner
        ds = _make_data_source()
        runner = MigrationRunner(ds, migrations_dir=tempfile.mkdtemp())
        runner.record_migration('001_test.sql', checksum='abc123')
        ds.execute.assert_called()
        sql = ds.execute.call_args[0][0]
        assert 'INSERT' in sql
        assert 'schema_migrations' in sql
        # 第二个位置参数是 (name, checksum) tuple
        assert ds.execute.call_args[0][1] == ('001_test.sql', 'abc123')

    def test_parse_sql_statements_splits_correctly(self):
        """_parse_sql_statements 正确切分多条 SQL"""
        from meta.core.migration_runner import MigrationRunner
        ds = _make_data_source()
        runner = MigrationRunner(ds, migrations_dir=tempfile.mkdtemp())
        content = """
        CREATE TABLE a (id INT);
        CREATE TABLE b (id INT);
        INSERT INTO c VALUES (1);
        """
        stmts = runner._parse_sql_statements(content)
        assert len(stmts) == 3
        assert 'CREATE TABLE a' in stmts[0]
        assert 'CREATE TABLE b' in stmts[1]
        assert 'INSERT INTO c' in stmts[2]

    def test_parse_sql_statements_skips_comments(self):
        """_parse_sql_statements 跳过 -- 注释行"""
        from meta.core.migration_runner import MigrationRunner
        ds = _make_data_source()
        runner = MigrationRunner(ds, migrations_dir=tempfile.mkdtemp())
        content = """
        -- This is a comment
        CREATE TABLE a (id INT);
        -- Another comment
        CREATE TABLE b (id INT);
        """
        stmts = runner._parse_sql_statements(content)
        # _parse_sql_statements 跳过整行以 -- 开头的行（保留非注释行）
        # 预期：注释行被跳过，但 CREATE TABLE 语句保留
        assert len(stmts) >= 2
        for s in stmts:
            assert '-- This is a comment' not in s
            assert '-- Another comment' not in s

    def test_default_migrations_dir_returns_existing_path(self):
        """_get_default_migrations_dir 返回存在的路径"""
        from meta.core.migration_runner import MigrationRunner
        ds = MagicMock()
        runner = MigrationRunner(ds)
        path = runner._get_default_migrations_dir()
        assert isinstance(path, str)
        assert os.path.isdir(path)

    def test_run_change_notification_migration_runs_known_migration(self):
        """run_change_notification_migration 触发指定 SQL 迁移并返回状态"""
        from meta.core.migration_runner import MigrationRunner
        ds = MagicMock()
        ds.in_transaction = False
        runner = MigrationRunner(ds)
        # 隔离外部副作用：直接 patch 内部方法
        with patch.object(runner, 'ensure_migrations_table') as mock_ensure, \
             patch.object(runner, 'run_migration', return_value=True) as mock_run:
            result = runner.run_change_notification_migration()
        # 调用顺序：先 ensure_migrations_table, 再 run_migration(已知名字)
        assert mock_ensure.called
        mock_run.assert_called_once_with('add_change_notification_tables.sql')
        assert result is True

    def test_run_change_notification_migration_module_function(self):
        """模块级 init_change_notification_tables 创建一个 runner 并委派"""
        from meta.core import migration_runner as mod
        ds = MagicMock()
        ds.in_transaction = False
        # 直接调用模块级便捷函数
        with patch.object(mod.MigrationRunner, 'run_change_notification_migration',
                          return_value=True) as mock_method:
            result = mod.init_change_notification_tables(ds)
        mock_method.assert_called_once_with()
        assert result is True
