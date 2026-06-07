import pytest

pytestmark = pytest.mark.unit

"""
后端测试套件 - SQL 表名白名单校验测试
测试 meta.core.table_name_validator 模块
"""

import pytest
from unittest.mock import patch, MagicMock


class TestValidateTableName:
    """validate_table_name 函数测试"""

    def test_validate_valid_table_name(self):
        """TC-VAL-001: 合法的 table_name 应通过校验"""
        from meta.core.table_name_validator import validate_table_name

        with patch('meta.core.table_name_validator._build_valid_tables', return_value={'users', 'products', 'roles'}):
            result = validate_table_name('users')
            assert result == 'users'

    def test_validate_invalid_table_name_raises(self):
        """TC-VAL-002: 非法的 table_name 应抛出 ValueError"""
        from meta.core.table_name_validator import validate_table_name

        with patch('meta.core.table_name_validator._build_valid_tables', return_value={'users', 'products'}):
            with pytest.raises(ValueError) as excinfo:
                validate_table_name('hacked_table')
            assert 'Invalid table name' in str(excinfo.value)
            assert 'hacked_table' in str(excinfo.value)

    def test_validate_empty_string_raises(self):
        """TC-VAL-003: 空字符串应抛出 ValueError"""
        from meta.core.table_name_validator import validate_table_name

        with patch('meta.core.table_name_validator._build_valid_tables', return_value={'users'}):
            with pytest.raises(ValueError) as excinfo:
                validate_table_name('')
            assert 'Invalid table name' in str(excinfo.value)

    def test_validate_sql_injection_attempt(self):
        """TC-VAL-004: SQL注入尝试应被拒绝"""
        from meta.core.table_name_validator import validate_table_name

        with patch('meta.core.table_name_validator._build_valid_tables', return_value={'users'}):
            injection_attempts = [
                "users; DROP TABLE users;--",
                "users UNION SELECT * FROM passwords",
                "users' OR '1'='1",
                "users/**/UNION",
                "users\x00null",
            ]
            for attempt in injection_attempts:
                with pytest.raises(ValueError):
                    validate_table_name(attempt)

    def test_validate_case_sensitivity(self):
        """TC-VAL-005: 表名校验应区分大小写"""
        from meta.core.table_name_validator import validate_table_name

        with patch('meta.core.table_name_validator._build_valid_tables', return_value={'Users', 'users'}):
            assert validate_table_name('Users') == 'Users'
            assert validate_table_name('users') == 'users'
            with pytest.raises(ValueError):
                validate_table_name('USERS')

    def test_validate_with_special_chars(self):
        """TC-VAL-006: 含特殊字符的 table_name 应被拒绝"""
        from meta.core.table_name_validator import validate_table_name

        with patch('meta.core.table_name_validator._build_valid_tables', return_value={'my_table'}):
            special_names = [
                'my-table',
                'my table',
                'my@table',
                'my#table',
                '../etc/passwd',
                '..\\windows\\system32',
            ]
            for name in special_names:
                with pytest.raises(ValueError):
                    validate_table_name(name)


class TestIsValidTableName:
    """is_valid_table_name 函数测试"""

    def test_is_valid_returns_true_for_valid(self):
        """TC-VAL-010: 合法表名返回 True"""
        from meta.core.table_name_validator import is_valid_table_name

        with patch('meta.core.table_name_validator._build_valid_tables', return_value={'users', 'products'}):
            assert is_valid_table_name('users') is True
            assert is_valid_table_name('products') is True

    def test_is_valid_returns_false_for_invalid(self):
        """TC-VAL-011: 非法表名返回 False"""
        from meta.core.table_name_validator import is_valid_table_name

        with patch('meta.core.table_name_validator._build_valid_tables', return_value={'users'}):
            assert is_valid_table_name('hackers') is False
            assert is_valid_table_name('') is False

    def test_is_valid_does_not_raise(self):
        """TC-VAL-012: is_valid 不应抛出异常"""
        from meta.core.table_name_validator import is_valid_table_name

        with patch('meta.core.table_name_validator._build_valid_tables', return_value={'users'}):
            assert is_valid_table_name('anything') is False


class TestCacheInvalidation:
    """缓存失效测试"""

    def test_invalidate_cache_clears_internal_cache(self):
        """TC-VAL-020: invalidate_cache 应清除内部缓存"""
        import meta.core.table_name_validator as tnv

        tnv._VALID_TABLES_CACHE = {'cached_value'}
        assert tnv._VALID_TABLES_CACHE == {'cached_value'}

        tnv.invalidate_cache()
        assert tnv._VALID_TABLES_CACHE is None

    def test_validate_uses_cache_after_build(self):
        """TC-VAL-021: 缓存构建后应复用"""
        import meta.core.table_name_validator as tnv

        original_cache = tnv._VALID_TABLES_CACHE
        tnv._VALID_TABLES_CACHE = {'users'}
        try:
            from meta.core.table_name_validator import validate_table_name
            validate_table_name('users')
        finally:
            tnv._VALID_TABLES_CACHE = original_cache


class TestBuildValidTables:
    """_build_valid_tables 函数测试"""

    def test_build_returns_set(self):
        """TC-VAL-030: 返回类型应为 set"""
        from meta.core.table_name_validator import _build_valid_tables

        with patch('meta.core.table_name_validator.registry') as mock_registry:
            mock_meta = MagicMock()
            mock_meta.table_name = 'test_table'
            mock_registry.all.return_value = [mock_meta]

            result = _build_valid_tables()
            assert isinstance(result, set)
            assert 'test_table' in result

    def test_build_ignores_none_table_name(self):
        """TC-VAL-031: 应忽略 table_name 为 None 的对象"""
        import meta.core.table_name_validator as tnv

        original_cache = tnv._VALID_TABLES_CACHE
        tnv._VALID_TABLES_CACHE = None
        try:
            with patch('meta.core.table_name_validator.registry') as mock_registry:
                class MockMeta:
                    def __init__(self, table_name):
                        self.table_name = table_name

                mock_registry.all.return_value = [
                    MockMeta('valid_table'),
                    MockMeta(None),
                ]
                result = tnv._build_valid_tables()
                assert 'valid_table' in result
                assert 'users' in result
                assert None not in result
        finally:
            tnv._VALID_TABLES_CACHE = original_cache

    def test_build_returns_empty_set_when_no_tables(self):
        """TC-VAL-032: 无注册表时返回空 set"""
        import meta.core.table_name_validator as tnv

        original_cache = tnv._VALID_TABLES_CACHE
        tnv._VALID_TABLES_CACHE = None
        try:
            with patch('meta.core.table_name_validator.registry') as mock_registry:
                mock_registry.all.return_value = []
                result = tnv._build_valid_tables()
                assert 'users' in result
                assert 'sqlite_master' in result
        finally:
            tnv._VALID_TABLES_CACHE = original_cache
