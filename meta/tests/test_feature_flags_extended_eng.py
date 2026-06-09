# -*- coding: utf-8 -*-
"""
SVC-018: feature_flags (5 测试) - v1.3 全局特性开关 (补充 round 9 已测的部分)

[MARKER] unit - 单元测试 (无外部依赖)
[FEATURE] is_enabled / set_flag / clear_cache / list_flags / _get_env_bool
"""
import os
import pytest
from meta.core import feature_flags
from meta.core.feature_flags import (
    is_enabled,
    set_flag,
    clear_cache,
    list_flags,
    _get_env_bool,
    DEFAULT_FLAGS,
)

pytestmark = [pytest.mark.unit]


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
