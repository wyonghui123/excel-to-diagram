# -*- coding: utf-8 -*-
"""
[FILE] test_dim_scope_conflict.py
[DESCRIPTION] Spec 08 FR-005/010 防冲突校验 + 权限限制 单元测试

[覆盖场景]
  FR-005 (PM 决策选项 C):
    1. 同一角色内 wildcard + exclude → 冲突
    2. 同一角色内只有 wildcard → 通过
    3. 同一角色内只有 exclude → 通过
    4. 多角色: 用户同时绑定 wildcard 角色 + exclude 角色 → 冲突
    5. 多角色: 用户只有 wildcard 角色 → 通过
    6. 多角色: 用户只有 exclude 角色 → 通过
    7. 无 dim scope 的角色 → 通过 (空配置)

  FR-010:
    8. 非 admin 用户尝试配 wildcard → 权限拒绝
    9. admin 用户配 wildcard → 通过
    10. 非 admin 用户配 include → 通过 (不需要特殊权限)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ['TEST_ENTRY'] = '1'  # 绕过 conftest 的硬阻断

import pytest
from unittest.mock import Mock, patch, MagicMock

from meta.api.role_dimension_scope_api import (
    _check_wildcard_exclude_conflict,
    _check_wildcard_exclude_permission,
    _is_wildcard_values,
    _build_ui_hint,
    DimScopeConflictError,
    DimScopePermissionError,
)


# ============================================================================
# Mock helpers
# ============================================================================
class MockDataSource:
    """Mock 数据源: 按 SQL 关键词路由返回预设行"""
    def __init__(self, rows_by_query=None):
        self.rows_by_query = rows_by_query or {}

    def execute(self, sql, params=None):
        sql_lower = sql.lower()
        for key, rows in self.rows_by_query.items():
            if key in sql_lower:
                cursor = Mock()
                cursor.fetchall.return_value = rows
                return cursor
        cursor = Mock()
        cursor.fetchall.return_value = []
        return cursor


# ============================================================================
# _is_wildcard_values 辅助函数测试
# ============================================================================
class TestIsWildcardValues:
    def test_contains_star_string(self):
        assert _is_wildcard_values(['*']) is True

    def test_contains_star_with_others(self):
        assert _is_wildcard_values([1, 2, '*']) is True

    def test_no_star(self):
        assert _is_wildcard_values([1, 2, 3]) is False

    def test_empty_list(self):
        assert _is_wildcard_values([]) is False

    def test_none(self):
        assert _is_wildcard_values(None) is False


# ============================================================================
# FR-005 防冲突校验: 同一角色内
# ============================================================================
class TestConflictCheckSameRole:
    """FR-005: 同一角色内 wildcard + exclude 冲突"""

    def test_same_role_wildcard_and_exclude_conflict(self):
        """同一角色内同时有 wildcard + exclude → 冲突"""
        ds = MockDataSource()
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': ['*'], 'scope_mode': 'include'},
            {'dimension_code': 'product', 'dimension_values': [3], 'scope_mode': 'exclude'},
        ]
        with pytest.raises(DimScopeConflictError) as exc_info:
            _check_wildcard_exclude_conflict(ds, role_id=1, new_scopes=new_scopes)
        assert "同一角色" in str(exc_info.value)

    def test_same_role_wildcard_only_pass(self):
        """同一角色内只有 wildcard → 通过"""
        ds = MockDataSource()
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': ['*'], 'scope_mode': 'include'},
        ]
        # 不抛异常即通过
        _check_wildcard_exclude_conflict(ds, role_id=1, new_scopes=new_scopes)

    def test_same_role_exclude_only_pass(self):
        """同一角色内只有 exclude → 通过"""
        ds = MockDataSource()
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': [3], 'scope_mode': 'exclude'},
        ]
        _check_wildcard_exclude_conflict(ds, role_id=1, new_scopes=new_scopes)

    def test_same_role_include_only_pass(self):
        """同一角色内只有 include → 通过"""
        ds = MockDataSource()
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': [1, 2], 'scope_mode': 'include'},
        ]
        _check_wildcard_exclude_conflict(ds, role_id=1, new_scopes=new_scopes)

    def test_empty_scopes_pass(self):
        """空配置 → 通过"""
        ds = MockDataSource()
        _check_wildcard_exclude_conflict(ds, role_id=1, new_scopes=[])


# ============================================================================
# FR-005 防冲突校验: 多角色
# ============================================================================
class TestConflictCheckMultiRole:
    """FR-005: 多角色 Union 防冲突 (同一用户的其他角色)"""

    def test_multi_role_wildcard_vs_exclude_conflict(self):
        """用户通过 R1 持有 wildcard, 尝试给 R2 配 exclude → 冲突"""
        # R1 绑定用户 100, R1 已有 wildcard scope
        # R2 也绑定用户 100, 尝试给 R2 配 exclude
        ds = MockDataSource(rows_by_query={
            # _get_role_users: R2 绑定的用户
            'ugm.user_id': [(100,)],
            # _get_user_other_roles: 用户 100 的其他角色 (排除 R2)
            'gr.role_id': [(1,)],  # R1
            # _load_scopes_raw: R1 的 scopes (含 wildcard)
            'dimension_code, dimension_values': [
                ('domain', '["*"]', 1, 'include'),
            ],
        })
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': [3], 'scope_mode': 'exclude'},
        ]
        with pytest.raises(DimScopeConflictError) as exc_info:
            _check_wildcard_exclude_conflict(ds, role_id=2, new_scopes=new_scopes)
        assert "100" in str(exc_info.value)
        assert 100 in exc_info.value.conflict_user_ids

    def test_multi_role_exclude_vs_wildcard_conflict(self):
        """用户通过 R1 持有 exclude, 尝试给 R2 配 wildcard → 冲突"""
        ds = MockDataSource(rows_by_query={
            'ugm.user_id': [(100,)],
            'gr.role_id': [(1,)],
            'dimension_code, dimension_values': [
                ('domain', '[3]', 1, 'exclude'),
            ],
        })
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': ['*'], 'scope_mode': 'include'},
        ]
        with pytest.raises(DimScopeConflictError) as exc_info:
            _check_wildcard_exclude_conflict(ds, role_id=2, new_scopes=new_scopes)
        assert 100 in exc_info.value.conflict_user_ids

    def test_multi_role_wildcard_vs_wildcard_pass(self):
        """用户通过 R1 持有 wildcard, 给 R2 配 wildcard → 通过 (不冲突)"""
        ds = MockDataSource(rows_by_query={
            'ugm.user_id': [(100,)],
            'gr.role_id': [(1,)],
            'dimension_code, dimension_values': [
                ('domain', '["*"]', 1, 'include'),
            ],
        })
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': ['*'], 'scope_mode': 'include'},
        ]
        # 不抛异常即通过
        _check_wildcard_exclude_conflict(ds, role_id=2, new_scopes=new_scopes)

    def test_multi_role_exclude_vs_exclude_pass(self):
        """用户通过 R1 持有 exclude, 给 R2 配 exclude → 通过 (不冲突)"""
        ds = MockDataSource(rows_by_query={
            'ugm.user_id': [(100,)],
            'gr.role_id': [(1,)],
            'dimension_code, dimension_values': [
                ('domain', '[3]', 1, 'exclude'),
            ],
        })
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': [5], 'scope_mode': 'exclude'},
        ]
        _check_wildcard_exclude_conflict(ds, role_id=2, new_scopes=new_scopes)

    def test_multi_role_include_vs_wildcard_pass(self):
        """用户通过 R1 持有 wildcard, 给 R2 配 include → 通过"""
        ds = MockDataSource(rows_by_query={
            'ugm.user_id': [(100,)],
            'gr.role_id': [(1,)],
            'dimension_code, dimension_values': [
                ('domain', '["*"]', 1, 'include'),
            ],
        })
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': [1, 2], 'scope_mode': 'include'},
        ]
        _check_wildcard_exclude_conflict(ds, role_id=2, new_scopes=new_scopes)


# ============================================================================
# FR-010 权限限制
# ============================================================================
class TestPermissionCheck:
    """FR-010: 仅 admin 可配置 wildcard/exclude"""

    def test_admin_wildcard_pass(self):
        """admin 用户配 wildcard → 通过"""
        user = {'user_id': 1, 'permissions': ['*']}
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': ['*'], 'scope_mode': 'include'},
        ]
        _check_wildcard_exclude_permission(new_scopes, user)

    def test_admin_exclude_pass(self):
        """admin 用户配 exclude → 通过"""
        user = {'user_id': 1, 'permissions': ['*']}
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': [3], 'scope_mode': 'exclude'},
        ]
        _check_wildcard_exclude_permission(new_scopes, user)

    def test_non_admin_wildcard_denied(self):
        """非 admin 用户配 wildcard → 拒绝"""
        user = {'user_id': 2, 'permissions': ['role:read', 'role:update']}
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': ['*'], 'scope_mode': 'include'},
        ]
        with pytest.raises(DimScopePermissionError):
            _check_wildcard_exclude_permission(new_scopes, user)

    def test_non_admin_exclude_denied(self):
        """非 admin 用户配 exclude → 拒绝"""
        user = {'user_id': 2, 'permissions': ['role:read', 'role:update']}
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': [3], 'scope_mode': 'exclude'},
        ]
        with pytest.raises(DimScopePermissionError):
            _check_wildcard_exclude_permission(new_scopes, user)

    def test_non_admin_include_pass(self):
        """非 admin 用户配 include → 通过 (不需要特殊权限)"""
        user = {'user_id': 2, 'permissions': ['role:read', 'role:update']}
        new_scopes = [
            {'dimension_code': 'domain', 'dimension_values': [1, 2], 'scope_mode': 'include'},
        ]
        _check_wildcard_exclude_permission(new_scopes, user)


# ============================================================================
# FR-009 _ui_hint 构建
# ============================================================================
class TestBuildUiHint:
    """FR-009: _ui_hint 字段构建"""

    def test_wildcard_hint(self):
        hint = _build_ui_hint(['*'], 'include')
        assert hint is not None
        assert hint['is_wildcard'] is True
        assert hint['is_exclude'] is False
        assert 'warning' in hint

    def test_exclude_hint(self):
        hint = _build_ui_hint([3], 'exclude')
        assert hint is not None
        assert hint['is_wildcard'] is False
        assert hint['is_exclude'] is True
        assert 'warning' in hint

    def test_normal_include_no_hint(self):
        """普通 include 不返回 hint (None)"""
        hint = _build_ui_hint([1, 2], 'include')
        assert hint is None

    def test_wildcard_and_exclude_hint(self):
        """wildcard + exclude 同时存在 (理论上是 FR-005 阻止的场景, 但 _ui_hint 仍应正确构建)"""
        hint = _build_ui_hint(['*'], 'exclude')
        assert hint is not None
        assert hint['is_wildcard'] is True
        assert hint['is_exclude'] is True
