# -*- coding: utf-8 -*-
"""核心基础服务模块契约测试（error_fix_hints / feature_flags / table_name_validator）。

[TEST-EFF P2-1] 由三个 <=5 用例的同域（meta.core 无外部依赖）小文件合并而来，
减少逐文件收集与启动开销：
- test_error_fix_hints_eng.py    (SVC-016)
- test_feature_flags_extended_eng.py (SVC-018)
- test_table_name_validator_eng.py   (SVC-011)
"""

import os

import pytest

from meta.core.error_fix_hints import (
    get_fix_hint,
    get_all_codes,
    get_codes_count,
    FIX_HINTS,
)
from meta.core.feature_flags import (
    is_enabled,
    set_flag,
    clear_cache,
    list_flags,
    _get_env_bool,
    DEFAULT_FLAGS,
)
from meta.core.table_name_validator import (
    validate_table_name,
    is_valid_table_name,
    register_table_name,
    invalidate_cache,
)

pytestmark = [pytest.mark.unit]


class TestErrorFixHints:
    """error_fix_hints 测试 (5 用例)"""

    def test_get_fix_hint_existing(self):
        """已注册错误码 → 返回 fix_hint dict"""
        hint = get_fix_hint('unauthorized')
        assert hint is not None
        assert 'fix_hint' in hint
        assert 'see_also' in hint
        assert 'meta/api/auth.py' in hint['see_also']

    def test_get_fix_hint_nonexistent_returns_none(self):
        """未注册错误码 → 返回 None"""
        hint = get_fix_hint('nonexistent_code_xyz_123')
        assert hint is None

    def test_get_all_codes(self):
        """get_all_codes 返回所有错误码列表"""
        codes = get_all_codes()
        assert isinstance(codes, list)
        # 至少包含 6 大类
        assert 'unauthorized' in codes
        assert 'action_not_found' in codes
        assert 'subflow_timeout' in codes
        assert 'db_integrity_error' in codes
        # 不重复
        assert len(codes) == len(set(codes))

    def test_get_codes_count(self):
        """get_codes_count 返回错误码总数"""
        count = get_codes_count()
        assert count == len(FIX_HINTS)
        assert count > 10  # 至少有 10+ 错误码

    # ---------- 跨类别错误码结构 合并 (4 → 1, 4 cases) ----------
    @pytest.mark.parametrize('code,expected_category,id_label', [
        pytest.param('unauthorized', 'auth', 'auth', id='auth_category'),
        pytest.param('action_not_found', 'action', 'action', id='action_category'),
        pytest.param('subflow_timeout', 'subflow', 'subflow', id='subflow_category'),
        pytest.param('db_locked', 'db', 'db_category', id='db_category'),
    ])
    def test_hint_structure_across_categories(self, code, expected_category, id_label):
        """所有 4 大类别错误码结构一致 (fix_hint + see_also 必存在)"""
        hint = get_fix_hint(code)
        assert hint is not None
        assert 'fix_hint' in hint
        assert 'see_also' in hint
        assert isinstance(hint['see_also'], list)
        assert len(hint['see_also']) >= 1
        # fix_hint 应包含中文 (v3.18 中文本地化)
        assert any('\u4e00' <= c <= '\u9fff' for c in hint['fix_hint'])


class TestFeatureFlagsExtended:
    """feature_flags 补充测试 (5 用例, 已在 round 9 测过 env-var 部分)"""

    def setup_method(self):
        clear_cache()  # 每个测试前清空, 避免污染

    def teardown_method(self):
        clear_cache()

    def test_default_flag_unknown_returns_true(self):
        """未知 flag → 默认 True (向后兼容)"""
        # 没有 env var, 没有 DEFAULT_FLAGS → True
        os.environ.pop('UNKNOWN_FLAG_XYZ', None)
        assert is_enabled('UNKNOWN_FLAG_XYZ') is True

    def test_set_flag_override(self):
        """set_flag 强制覆盖 (不读 env)"""
        # set_flag('USE_V2_QUERY_LIST', True) → 即便 default=False
        set_flag('USE_V2_QUERY_LIST', True)
        assert is_enabled('USE_V2_QUERY_LIST') is True
        set_flag('USE_V2_QUERY_LIST', False)
        assert is_enabled('USE_V2_QUERY_LIST') is False

    def test_list_flags_returns_all_defaults(self):
        """list_flags 返回所有 DEFAULT_FLAGS 当前状态"""
        flags = list_flags()
        # 应包含所有 7 个默认 flag
        for name in DEFAULT_FLAGS:
            assert name in flags
        # ENABLE_RUNTIME_RESOLUTION 默认 True
        assert flags['ENABLE_RUNTIME_RESOLUTION'] is True
        # USE_V2_QUERY_LIST 默认 False
        assert flags['USE_V2_QUERY_LIST'] is False

    # ---------- _get_env_bool 各种值 合并 (5 → 1, 5 cases) ----------
    @pytest.mark.parametrize('env_value,default,expected,id_label', [
        pytest.param(None, True, True, 'missing_default_true', id='missing_true'),
        pytest.param(None, False, False, 'missing_default_false', id='missing_false'),
        pytest.param('true', False, True, 'env_true', id='env_true'),
        pytest.param('1', False, True, 'env_1', id='env_one'),
        pytest.param('garbage', True, False, 'env_invalid', id='env_garbage'),
    ])
    def test_get_env_bool(self, monkeypatch, env_value, default, expected, id_label):
        """_get_env_bool 各种 env 场景"""
        if env_value is None:
            monkeypatch.delenv('TEST_FLAG', raising=False)
        else:
            monkeypatch.setenv('TEST_FLAG', env_value)
        assert _get_env_bool('TEST_FLAG', default) is expected

    def test_clear_cache(self, monkeypatch):
        """clear_cache → 重新读 env"""
        monkeypatch.setenv('USE_V2_QUERY_LIST', 'true')
        assert is_enabled('USE_V2_QUERY_LIST') is True
        # 改 env 但不 clear
        monkeypatch.setenv('USE_V2_QUERY_LIST', 'false')
        # 仍然返回 cached value
        assert is_enabled('USE_V2_QUERY_LIST') is True
        # clear 后重新读
        clear_cache()
        assert is_enabled('USE_V2_QUERY_LIST') is False


class TestTableNameValidator:
    """table_name_validator 测试 (5 用例)"""

    def test_validate_system_table(self):
        """合法系统表 (users/orgs 等) → 通过"""
        assert validate_table_name('users') == 'users'
        assert validate_table_name('orgs') == 'orgs'
        assert validate_table_name('permissions') == 'permissions'

    def test_is_valid_table_name(self):
        """is_valid_table_name 返回 bool 而不抛异常"""
        assert is_valid_table_name('users') is True
        assert is_valid_table_name('orgs') is True
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
