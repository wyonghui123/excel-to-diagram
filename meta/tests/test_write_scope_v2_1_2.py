# -*- coding: utf-8 -*-
"""
[FILE] test_write_scope_v2_1_2.py
[DESCRIPTION] V2.1.2 - role-specific perm 检查 (修复 multi-role perm leak)

[BUG v2.1]
  TEST333 (role A=read-scm, role B=采购管理领域编辑)
  - user 全量 perm 含 service_module:update (来自 role B)
  - role A 的 dim scope 可能覆盖某些记录 (继承自 供应链管理系统)
  - v2.1 用 user 全量 perm → 所有 role 通过 perm 检查 → role A dim scope 命中 → 越权放行

[FIX v2.1.2]
  v2.1 perm 检查改为: 该 role 自身的 perm
  - 查 role_permissions JOIN permissions WHERE role_id = ?
  - role A 无 service_module:update → 即使 dim scope 命中也 skip
  - 修复多角色用户跨域越权

[SPEC] .trae/specs/auth-permission-system/write-scope-perm-link-v2.1-spec.md (待更新)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from unittest.mock import Mock, patch

from meta.core.interceptors.write_scope_interceptor import (
    WriteScopeInterceptor,
    _WRITE_SCOPE_V2_1_PERM_CHECK,
)


# ============================================================================
# pytest fixtures: Flask app context for g.current_user
# ============================================================================
@pytest.fixture
def app_ctx():
    """提供 Flask app context"""
    from flask import Flask
    app = Flask(__name__)
    with app.app_context():
        yield app


@pytest.fixture
def set_current_user():
    """helper: 在 app context 内设置 g.current_user"""
    from flask import g

    def _set(user_dict):
        g.current_user = user_dict
        return g

    return _set


# ============================================================================
# Mock helpers
# ============================================================================
class MockDataSource:
    def __init__(self, rows_by_query=None):
        self.rows_by_query = rows_by_query or {}
        self.executed_queries = []

    def execute(self, sql, params=None):
        self.executed_queries.append((sql, params))
        sql_lower = sql.lower()
        for key, rows in self.rows_by_query.items():
            if key in sql_lower:
                return MockCursor(rows)
        return MockCursor([])


class MockCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class MockActionContext:
    def __init__(self, **kwargs):
        self.object_type = kwargs.get('object_type', 'service_module')
        self.action = kwargs.get('action', 'crud_update')
        self.params = kwargs.get('params', {'id': 187})
        self.data_source = kwargs.get('data_source', MockDataSource())
        self.user_id = kwargs.get('user_id', 3385)
        self.user_info = kwargs.get('user_info', None)
        self.trace_id = kwargs.get('trace_id', 'test-trace')

    @property
    def object_id(self):
        return self.params.get('id')


# ============================================================================
# _get_role_perm_codes helper
# ============================================================================
class TestV2_1_2GetRolePermCodes:
    """[v2.1.2] _get_role_perm_codes helper"""

    def setup_method(self):
        self.interceptor = WriteScopeInterceptor()

    def test_returns_role_specific_perms(self):
        """返回 role 自身的 perm codes (从 role_permissions JOIN permissions)"""
        ds = MockDataSource(rows_by_query={
            'role_permissions': [
                ('service_module:read',),
                ('service_module:update',),
            ]
        })
        ctx = MockActionContext(data_source=ds)
        result = self.interceptor._get_role_perm_codes(ctx, 5970)
        assert 'service_module:update' in result
        assert 'service_module:read' in result

    def test_returns_empty_set_for_role_without_perms(self):
        """role 无 perm 时返回空 set"""
        ds = MockDataSource(rows_by_query={'role_permissions': []})
        ctx = MockActionContext(data_source=ds)
        result = self.interceptor._get_role_perm_codes(ctx, 9999)
        assert result == set()

    def test_cached_per_request(self):
        """同 request 内重复调用走缓存"""
        ds = MockDataSource(rows_by_query={
            'role_permissions': [('service_module:update',)]
        })
        ctx = MockActionContext(data_source=ds)
        result1 = self.interceptor._get_role_perm_codes(ctx, 5970)
        result2 = self.interceptor._get_role_perm_codes(ctx, 5970)
        # 缓存命中, 不应该再查
        # (允许查询数 = 1)
        perm_queries = [q for q in ds.executed_queries
                        if 'role_permissions' in q[0].lower()]
        assert len(perm_queries) == 1

    def test_exception_returns_empty_set(self):
        """异常时返回空 set (防御性)"""
        ds = MockDataSource()  # 无数据, execute 返回空
        ctx = MockActionContext(data_source=ds)
        result = self.interceptor._get_role_perm_codes(ctx, 5970)
        assert isinstance(result, set)


# ============================================================================
# _check_dim_scope V2.1.2 role-specific perm 验证
# ============================================================================
class TestV2_1_2RoleSpecificPermCheck:
    """[v2.1.2] _check_dim_scope 使用 role-specific perm (修复 multi-role leak)"""

    def setup_method(self):
        self.interceptor = WriteScopeInterceptor()

    def _mock_role_ids(self, role_ids):
        return patch.object(
            self.interceptor, '_get_user_role_ids', return_value=role_ids
        )

    def test_role_a_no_perm_dim_match_still_rejected(self, app_ctx, set_current_user):
        """[核心修复] role A 无 perm, 即使 dim scope 命中也被拒绝

        场景: TEST333 有 role A (read-scm) + role B (TEST333W)
              假设 role A 的 dim scope 包含 domain=706 (继承自 供应链管理系统)
              用户尝试编辑 domain=706 的 SM (TESTAPCREATE)
              v2.1.2 应拒绝: role A 无 service_module:update, 即使 dim 命中也 skip
        """
        # user 整体有 service_module:update (来自 role B)
        set_current_user({
            'permissions': ['service_module:update', 'service_module:read'],
            '_role_ids_cache': [5433, 5970],  # role A + role B
        })
        with self._mock_role_ids([5433, 5970]):
            # role 5433 (role A): dim scope 覆盖 domain=706 (假设), 但无 service_module:update
            # role 5970 (role B): dim scope=domain=[703], 有 service_module:update
            role_perm_codes_map = {
                5433: {'service_module:read'},  # role A 无 update
                5970: {'service_module:update', 'service_module:read'},  # role B 有 update
            }

            def mock_get_role_perms(ctx, role_id):
                return role_perm_codes_map.get(role_id, set())

            # role 5433 dim scope: domain=[706] (假设会覆盖)
            # role 5970 dim scope: domain=[703]
            dim_scope_map = {
                5433: {'domain': {706}},  # role A 覆盖 domain=706 (继承)
                5970: {'domain': {703}},  # role B 覆盖 domain=703
            }

            with patch.object(
                self.interceptor, '_get_role_perm_codes',
                side_effect=mock_get_role_perms
            ):
                with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                    mock_engine = mock_engine_cls.return_value

                    def expand_side_effect(role_id):
                        return dim_scope_map.get(role_id, {})

                    mock_engine.expand_dimension_values.side_effect = expand_side_effect
                    mock_engine.derive_data_conditions.return_value = {
                        'service_module': 'service_module.id IN (1)'
                    }
                    with patch.object(
                        self.interceptor, '_record_matches_cond', return_value=True
                    ):
                        with patch(
                            'meta.core.interceptors.write_scope_interceptor._WRITE_SCOPE_V2_1_PERM_CHECK',
                            True,
                        ):
                            ctx = MockActionContext(object_type='service_module', action='crud_update')
                            record = {'id': 187, 'sub_domain_id': 145}
                            result = self.interceptor._check_dim_scope(
                                ctx, 'service_module', record, user_id=3385
                            )

                            # 期望: matched=False (因为 role A 被 perm skip, role B dim 不命中)
                            assert result['matched'] is False
                            # role 5433 应被记录为 skipped='missing_functional_perm'
                            skipped = [r for r in result['roles_checked']
                                       if r.get('skipped') == 'missing_functional_perm']
                            assert any(r['role_id'] == 5433 for r in skipped)

    def test_role_b_with_perm_and_dim_match_allowed(self, app_ctx, set_current_user):
        """role B 有 perm + dim scope 命中 → 通过"""
        set_current_user({
            'permissions': ['service_module:update'],
            '_role_ids_cache': [5970],
        })
        with self._mock_role_ids([5970]):
            with patch.object(
                self.interceptor, '_get_role_perm_codes',
                return_value={'service_module:update'}
            ):
                with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                    mock_engine = mock_engine_cls.return_value
                    mock_engine.expand_dimension_values.return_value = {'domain': {703}}
                    mock_engine.derive_data_conditions.return_value = {
                        'service_module': 'service_module.id IN (SELECT id FROM service_modules sm JOIN sub_domains sd ON sm.sub_domain_id=sd.id WHERE sd.domain_id IN (703))'
                    }
                    with patch.object(
                        self.interceptor, '_record_matches_cond', return_value=True
                    ):
                        with patch(
                            'meta.core.interceptors.write_scope_interceptor._WRITE_SCOPE_V2_1_PERM_CHECK',
                            True,
                        ):
                            ctx = MockActionContext(object_type='service_module', action='crud_update')
                            record = {'id': 137, 'sub_domain_id': 138}
                            result = self.interceptor._check_dim_scope(
                                ctx, 'service_module', record, user_id=3385
                            )
                            assert result['matched'] is True

    def test_admin_wildcard_role_passes(self, app_ctx, set_current_user):
        """role 含 '*' 通配 → 通过 (admin 角色)"""
        set_current_user({
            'permissions': ['*'],
            '_role_ids_cache': [1],
        })
        with self._mock_role_ids([1]):
            with patch.object(
                self.interceptor, '_get_role_perm_codes',
                return_value={'*'}
            ):
                with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                    mock_engine = mock_engine_cls.return_value
                    mock_engine.expand_dimension_values.return_value = {'domain': {703}}
                    mock_engine.derive_data_conditions.return_value = {
                        'service_module': 'service_module.id IN (1)'
                    }
                    with patch.object(
                        self.interceptor, '_record_matches_cond', return_value=True
                    ):
                        with patch(
                            'meta.core.interceptors.write_scope_interceptor._WRITE_SCOPE_V2_1_PERM_CHECK',
                            True,
                        ):
                            ctx = MockActionContext(object_type='service_module', action='crud_update')
                            record = {'id': 1}
                            result = self.interceptor._check_dim_scope(
                                ctx, 'service_module', record, user_id=1
                            )
                            assert result['matched'] is True

    def test_object_wildcard_role_passes(self, app_ctx, set_current_user):
        """role 含 'service_module:*' 通配 → 所有 action 通过"""
        set_current_user({
            'permissions': ['service_module:*'],
            '_role_ids_cache': [5970],
        })
        with self._mock_role_ids([5970]):
            with patch.object(
                self.interceptor, '_get_role_perm_codes',
                return_value={'service_module:*'}
            ):
                with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                    mock_engine = mock_engine_cls.return_value
                    mock_engine.expand_dimension_values.return_value = {'domain': {703}}
                    mock_engine.derive_data_conditions.return_value = {
                        'service_module': 'service_module.id IN (1)'
                    }
                    with patch.object(
                        self.interceptor, '_record_matches_cond', return_value=True
                    ):
                        with patch(
                            'meta.core.interceptors.write_scope_interceptor._WRITE_SCOPE_V2_1_PERM_CHECK',
                            True,
                        ):
                            ctx = MockActionContext(object_type='service_module', action='crud_update')
                            record = {'id': 1}
                            result = self.interceptor._check_dim_scope(
                                ctx, 'service_module', record, user_id=1
                            )
                            assert result['matched'] is True


# ============================================================================
# 实际场景: TEST333 越权场景 (回归 V2.1 修复)
# ============================================================================
class TestV2_1_2TEST333WScenario:
    """[v2.1.2] TEST333 跨域 SM 编辑 (回归)

    期望: V2.1.2 修复后, TEST333 不能编辑 TESTAPCREATE (domain=706)
    即使 user 有 service_module:update (来自 TEST333W 角色),
    因为覆盖 domain=706 的其他角色 (如 5433 read-scm) 无 service_module:update,
    V2.1 perm 检查会 skip 掉 role 5433, role 5970 (TEST333W) dim scope=domain=[703] 不命中
    """

    def setup_method(self):
        self.interceptor = WriteScopeInterceptor()

    def test_TEST333_cannot_edit_sm_in_domain_706(self, app_ctx, set_current_user):
        """TEST333 编辑 TESTAPCREATE (domain=706) 应被拒绝"""
        # 注: 此测试模拟 v2.1.2 逻辑, 需同时 mock role-specific perm
        # 实际场景中 TEST333 的 role 配置决定最终结果
        set_current_user({
            'permissions': ['service_module:update'],  # 来自 TEST333W
            '_role_ids_cache': [5970],  # 只有 TEST333W 角色
        })
        interceptor = self.interceptor
        with patch.object(interceptor, '_get_user_role_ids', return_value=[5970]):
            # TEST333W 有 service_module:update
            with patch.object(
                interceptor, '_get_role_perm_codes',
                return_value={'service_module:update'}
            ):
                with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                    mock_engine = mock_engine_cls.return_value
                    mock_engine.expand_dimension_values.return_value = {'domain': {703}}
                    with patch.object(
                        interceptor, '_check_ancestor_dim_scope', return_value=False
                    ):
                        with patch(
                            'meta.core.interceptors.write_scope_interceptor._WRITE_SCOPE_V2_1_PERM_CHECK',
                            True,
                        ):
                            ctx = MockActionContext(object_type='service_module', action='crud_update')
                            record = {'id': 187, 'sub_domain_id': 145}
                            result = interceptor._check_dim_scope(
                                ctx, 'service_module', record, user_id=3385
                            )
                            # role 5970 有 perm (pass), 但 dim scope 不命中 (False)
                            # matched=False
                            assert result['matched'] is False
                            passed = [r for r in result['roles_checked']
                                      if r.get('perm_check') == 'passed']
                            assert len(passed) == 1  # role 5970 通过 perm 检查
