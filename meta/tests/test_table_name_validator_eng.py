# -*- coding: utf-8 -*-
"""
SVC-011: table_name_validator (5 测试) - SQL 注入防护

[MARKER] unit - 单元测试 (无外部依赖)
[FEATURE] validate_table_name / is_valid_table_name / register / invalidate_cache
"""
import pytest
from meta.core.table_name_validator import (
    validate_table_name,
    is_valid_table_name,
    register_table_name,
    invalidate_cache,
)

pytestmark = [pytest.mark.unit]


class TestTableNameValidator:
    """table_name_validator 测试 (5 用例)"""

    def test_validate_system_table(self):
        """合法系统表 (users/roles 等) → 通过"""
        assert validate_table_name('users') == 'users'
        assert validate_table_name('roles') == 'roles'
        assert validate_table_name('permissions') == 'permissions'

    def test_is_valid_table_name(self):
        """is_valid_table_name 返回 bool 而不抛异常"""
        assert is_valid_table_name('users') is True
        assert is_valid_table_name('roles') is True
        assert is_valid_table_name('nonexistent_table_xyz') is False
        assert is_valid_table_name('; DROP TABLE users;') is False

    def test_validate_invalid_table_raises(self):
        """非法表名 → ValueError"""
        with pytest.raises(ValueError) as exc_info:
            validate_table_name('nonexistent_table_xyz')
        assert 'Invalid table name' in str(exc_info.value)

    # ---------- register/invalidate_cache 合并 (3 → 1, 3 cases) ----------
    @pytest.mark.parametrize('table_name,expected_valid,id_label', [
        pytest.param('custom_table_a', True, 'custom_valid', id='register_custom'),
        pytest.param('temp_stats_view', True, 'custom_view', id='register_view'),
        pytest.param('; DROP TABLE users;', False,
                    'sql_injection_still_blocked', id='sql_injection_blocked'),
    ])
    def test_register_table_name(self, table_name, expected_valid, id_label):
        """register_table_name 注册后生效, SQL 注入仍被拒绝"""
        if id_label == 'sql_injection_still_blocked':
            # SQL 注入防护：register_table_name 应该直接拒绝不安全表名
            with pytest.raises(ValueError) as exc_info:
                register_table_name(table_name)
            assert 'Invalid table name' in str(exc_info.value)
            # 即便 register 失败，is_valid_table_name 也不应返回 True
            assert is_valid_table_name(table_name) is False
        else:
            register_table_name(table_name)
            invalidate_cache()  # 强制重建缓存
            assert is_valid_table_name(table_name) is expected_valid
            # 清理: 注销回滚缓存
            invalidate_cache()
