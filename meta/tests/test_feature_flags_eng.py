# -*- coding: utf-8 -*-
"""
ENG-003: feature_flags (16 测试) - 全局特性开关

[MARKER] unit - 单元测试 (无外部依赖)
[FEATURE] is_enabled / set_flag / clear_cache / list_flags / _get_env_bool
"""
import os
import pytest
from meta.core.feature_flags import (
    is_enabled,
    set_flag,
    clear_cache,
    list_flags,
    DEFAULT_FLAGS,
    _get_env_bool,
)

pytestmark = [pytest.mark.unit]


class TestFeatureFlags:
    """feature_flags 测试"""

    def setup_method(self):
        clear_cache()
        # 清理可能干扰的环境变量
        for flag in DEFAULT_FLAGS:
            os.environ.pop(flag, None)

    def teardown_method(self):
        clear_cache()
        for flag in DEFAULT_FLAGS:
            os.environ.pop(flag, None)

    def test_default_flag_enabled(self):
        """默认 DEFAULT_FLAGS 里的都是 True"""
        assert is_enabled('ENABLE_RUNTIME_RESOLUTION') is True
        assert is_enabled('ENABLE_OWNER_FILTER') is True
        assert is_enabled('ENABLE_DRAFT_PATTERN') is True

    def test_v2_path_flags_default_disabled(self):
        """v2 路径默认 disabled (灰度)"""
        assert is_enabled('USE_V2_QUERY_LIST') is False
        assert is_enabled('USE_V2_QUERY_ASSOC') is False

    def test_unknown_flag_default_true(self):
        """未知 flag 默认 True (fail-open)"""
        assert is_enabled('UNKNOWN_FLAG_XYZ') is True

    # ---------- env override 合并 (2 → 1) ----------
    @pytest.mark.parametrize('env_value,expected', [
        pytest.param('true', True, id='true'),
        pytest.param('false', False, id='false'),
    ])
    def test_env_override(self, env_value, expected):
        os.environ['ENABLE_RUNTIME_RESOLUTION'] = env_value
        clear_cache()
        assert is_enabled('ENABLE_RUNTIME_RESOLUTION') is expected

    # ---------- env various values 合并 (2 → 1) ----------
    @pytest.mark.parametrize('val,expected', [
        pytest.param('true', True, id='true'),
        pytest.param('1', True, id='one'),
        pytest.param('yes', True, id='yes'),
        pytest.param('on', True, id='on'),
        pytest.param('TRUE', True, id='TRUE_upper'),
        pytest.param('Yes', True, id='Yes_cap'),
        pytest.param('false', False, id='false'),
        pytest.param('0', False, id='zero'),
        pytest.param('no', False, id='no'),
        pytest.param('off', False, id='off'),
        pytest.param('FALSE', False, id='FALSE_upper'),
        pytest.param('No', False, id='No_cap'),
    ])
    def test_env_override_various(self, val, expected):
        os.environ['USE_V2_QUERY_LIST'] = val
        clear_cache()
        assert is_enabled('USE_V2_QUERY_LIST') is expected, f"Failed for {val}"

    def test_set_flag_override(self):
        """set_flag 显式覆盖 (测试用)"""
        set_flag('USE_V2_QUERY_LIST', True)
        assert is_enabled('USE_V2_QUERY_LIST') is True
        set_flag('USE_V2_QUERY_LIST', False)
        assert is_enabled('USE_V2_QUERY_LIST') is False

    def test_set_flag_bypasses_env(self):
        """set_flag 后再设 env, set_flag 优先级高 (因为 cache)"""
        set_flag('USE_V2_QUERY_LIST', True)
        os.environ['USE_V2_QUERY_LIST'] = 'false'
        clear_cache()  # 但 clear_cache 后 env 生效
        # clear_cache 后, set_flag 失效
        assert is_enabled('USE_V2_QUERY_LIST') is False

    def test_clear_cache(self):
        set_flag('USE_V2_QUERY_LIST', True)
        clear_cache()
        # clear_cache 后, 回到默认值 (false)
        assert is_enabled('USE_V2_QUERY_LIST') is False

    def test_list_flags(self):
        flags = list_flags()
        # 包含所有 DEFAULT_FLAGS keys
        for key in DEFAULT_FLAGS:
            assert key in flags
        # 未知 flag 不在 list_flags 返回
        assert 'UNKNOWN_FLAG_XYZ' not in flags

    def test_cache_after_first_call(self):
        """首次调用后值被缓存"""
        clear_cache()
        # 首次调用 → 读 env
        first = is_enabled('USE_V2_QUERY_LIST')
        # 改变 env 不影响已缓存值
        os.environ['USE_V2_QUERY_LIST'] = 'true'
        second = is_enabled('USE_V2_QUERY_LIST')
        assert first == second  # 都是 False (default)
        # clear 后才生效
        clear_cache()
        third = is_enabled('USE_V2_QUERY_LIST')
        assert third is True


class TestGetEnvBool:
    def test_missing_returns_default_true(self, monkeypatch):
        monkeypatch.delenv('TEST_FLAG', raising=False)
        assert _get_env_bool('TEST_FLAG', True) is True

    def test_missing_returns_default_false(self, monkeypatch):
        monkeypatch.delenv('TEST_FLAG', raising=False)
        assert _get_env_bool('TEST_FLAG', False) is False

    def test_present_true(self, monkeypatch):
        monkeypatch.setenv('TEST_FLAG', 'true')
        assert _get_env_bool('TEST_FLAG', False) is True

    def test_present_invalid_returns_default(self, monkeypatch):
        monkeypatch.setenv('TEST_FLAG', 'garbage')
        # 任何非 'true'/'1'/'yes'/'on' 都视为 false (但 default 不生效)
        assert _get_env_bool('TEST_FLAG', True) is False
