# -*- coding: utf-8 -*-
"""MigrationRunner.verify_migration 返回值归一化测试。

背景: v224 的 verify() 返回 {'ok': bool, ...}; dict 非空恒为真，
原实现直接 bool(dict) 会把 verify 失败误报成 OK。
"""

import pytest
from unittest.mock import MagicMock

pytestmark = pytest.mark.unit


class TestVerifyResultNormalization:
    def _runner(self, tmp_path, return_expr):
        migration = tmp_path / 'v999_verify_shape.py'
        migration.write_text(
            'def verify(db_path):\n    return %s\n' % return_expr,
            encoding='utf-8')
        ds = MagicMock()
        ds.in_transaction = False
        ds._db_path = str(tmp_path / 'architecture.db')
        from meta.core.migration_runner import MigrationRunner
        return MigrationRunner(ds, migrations_dir=str(tmp_path))

    def test_dict_ok_false_reported_as_failure(self, tmp_path):
        runner = self._runner(tmp_path, "{'ok': False, 'checks': {'column': False}}")
        ran, ok, _ = runner.verify_migration('v999_verify_shape.py')
        assert ran is True
        assert ok is False

    def test_dict_ok_true_reported_as_success(self, tmp_path):
        runner = self._runner(tmp_path, "{'ok': True, 'checks': {}}")
        ran, ok, _ = runner.verify_migration('v999_verify_shape.py')
        assert ran is True
        assert ok is True

    def test_bool_result_unchanged(self, tmp_path):
        runner = self._runner(tmp_path, "False")
        ran, ok, _ = runner.verify_migration('v999_verify_shape.py')
        assert ran is True
        assert ok is False
