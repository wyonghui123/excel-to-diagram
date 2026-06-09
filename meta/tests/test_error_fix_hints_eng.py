# -*- coding: utf-8 -*-
"""
SVC-016: error_fix_hints (5 测试) - v3.18 D.6/M.6 错误码 fix_hint 表

[MARKER] unit - 单元测试 (无外部依赖)
[FEATURE] get_fix_hint / get_all_codes / get_codes_count
"""
import pytest
from meta.core.error_fix_hints import (
    get_fix_hint,
    get_all_codes,
    get_codes_count,
    FIX_HINTS,
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
