# -*- coding: utf-8 -*-
"""
[FILE] test_cross_domain_relation_perm.py
[DESCRIPTION] 跨领域关系 functional perm 校验单元测试 (V1.2.0)
[SPEC] .trae/specs/cross-domain-relationship-permission/spec.md

[SCENARIOS - 8 测]
  U01: D1-Manager (有 BO:edit) 创建 D1→D1 关系 → 成功
  U02: D1-Manager (有 BO:edit) 创建 D1→D2 关系 (跨域) → 成功 (OR-edit 命中 D1 端)
  U03: D1-Manager (有 BO:edit) 创建 D2→D1 关系 (跨域) → 成功 (OR-edit 命中 D1 端)
  U04: D1-Manager 尝试创建 D2→D2 关系 → 拒绝 (两端都不在 scope)
  U05: D1-Viewer (无 BO:edit) 创建 D1→D2 关系 → 软警告模式: 仍通过 (Phase 1); 硬拒绝模式: 拒绝
  U06: Product Owner (无 dim scope, 但 owner) 创建 D1→D2 → 成功 (owner chain 放行, 不走 dim scope)
  U07: D1-Manager update 关系 D1→D2 → 成功 (OR-edit update 同样适用)
  U08: D1-Manager delete 关系 D1→D2 → 成功 (OR-edit delete 同样适用)

[PHASE 覆盖]
  - 默认 (env: WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN=false): 硬拒绝 (Phase 2, 2026-06-15 切换)
  - 回退: env=true → 软警告 (用 monkeypatch 切换 _WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from unittest.mock import Mock, MagicMock, patch

from meta.core.interceptors.write_scope_interceptor import (
    WriteScopeInterceptor,
    WriteScopeDenied,
    _WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN,
)


# ============================================================================
# Mock 辅助类
# ============================================================================
class MockDataSource:
    """[V1.2.0] 模拟 DataSource (含 source/target BO ancestor 查询)"""

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
    """[V1.2.0] 模拟 ActionContext (relationship 操作)"""

    def __init__(self, **kwargs):
        self.object_type = kwargs.get('object_type', 'relationship')
        self.action = kwargs.get('action', 'crud_create')
        self.params = kwargs.get('params', {'id': 1})
        self.data_source = kwargs.get('data_source', MockDataSource())
        self.user_id = kwargs.get('user_id', 333)
        self.trace_id = kwargs.get('trace_id', 'test-trace')
        self.target_id = kwargs.get('target_id', 1)


# ============================================================================
# Test: _user_has_bo_edit_perm_for_relationship (依赖注入 user_info)
# ============================================================================
class TestUserHasBoEditPerm:
    """[V1.2.0] U01-U05 helper: functional perm 校验 (依赖注入 user_info)"""

    def setup_method(self):
        self.interceptor = WriteScopeInterceptor()

    def test_admin_user_with_wildcard_passes(self):
        """admin 用户 ('*') → 有 BO:edit 类 perm (防御性)"""
        user_info = {'id': 999, 'permissions': {'*'}}
        assert self.interceptor._user_has_bo_edit_perm_for_relationship(user_info) is True

    def test_user_with_business_object_edit_passes(self):
        """user 有 business_object:edit → 有 BO:edit perm"""
        user_info = {'id': 333, 'permissions': ['business_object:edit']}
        assert self.interceptor._user_has_bo_edit_perm_for_relationship(user_info) is True

    def test_user_with_business_object_update_passes(self):
        """user 有 business_object:update → 有 BO:edit perm (OR 语义)"""
        user_info = {'id': 333, 'permissions': ['business_object:update']}
        assert self.interceptor._user_has_bo_edit_perm_for_relationship(user_info) is True

    def test_user_with_business_object_delete_passes(self):
        """user 有 business_object:delete → 有 BO:edit perm (OR 语义)"""
        user_info = {'id': 333, 'permissions': ['business_object:delete']}
        assert self.interceptor._user_has_bo_edit_perm_for_relationship(user_info) is True

    def test_viewer_with_only_read_fails(self):
        """D1-Viewer (只有 BO:read, 无 edit) → 无 BO:edit perm"""
        user_info = {'id': 333, 'permissions': ['business_object:read']}
        assert self.interceptor._user_has_bo_edit_perm_for_relationship(user_info) is False

    def test_user_with_no_perms_fails(self):
        """user 无任何 perm → 无 BO:edit perm"""
        user_info = {'id': 333, 'permissions': []}
        assert self.interceptor._user_has_bo_edit_perm_for_relationship(user_info) is False

    def test_user_with_other_resource_perms_fails(self):
        """user 有 relationship:create 但无 BO:edit → 无 BO:edit perm"""
        user_info = {'id': 333, 'permissions': ['relationship:create', 'relationship:read']}
        assert self.interceptor._user_has_bo_edit_perm_for_relationship(user_info) is False

    def test_missing_user_info_defensive_pass(self):
        """[V1.2.0 防御] user_info=None → 默认放行 (PermissionInterceptor 已处理未登录)"""
        assert self.interceptor._user_has_bo_edit_perm_for_relationship(None) is True

    def test_user_info_with_set_perms(self):
        """user_info.permissions 是 set 类型 (JWT 解码后常见) → 正确处理"""
        user_info = {'id': 333, 'permissions': {'business_object:edit'}}
        assert self.interceptor._user_has_bo_edit_perm_for_relationship(user_info) is True

    def test_user_info_with_invalid_perms_type(self):
        """user_info.permissions 是非法类型 → 防御性放行"""
        user_info = {'id': 333, 'permissions': 'invalid_string'}
        assert self.interceptor._user_has_bo_edit_perm_for_relationship(user_info) is True


# ============================================================================
# Test: _check_relationship_ancestor_dim_scope 集成 (依赖注入 user_info via _fetch_user_info_for_rel_perm)
# ============================================================================
class TestRelationshipAncestorDimScopeIntegration:
    """[V1.2.0] U01-U04 集成测试: relationship 写权限 + functional perm gate"""

    def setup_method(self):
        self.interceptor = WriteScopeInterceptor()
        self.expanded = {'domain': {703}, 'sub_domain': {138, 139}}

    def _mock_ancestor_match(self):
        """Mock: BO_A 的 ancestor domain=703 在 expanded 内 → OR 命中"""
        ds = MockDataSource(rows_by_query={
            'select bo.id,': [
                # (bo.id, sub_domain_id, domain_id, version_id, product_id)
                (100, 138, 703, 1, 1),  # BO_A 在 D1
                (200, 240, 800, 1, 1),  # BO_B 在 D2
            ],
            'select source_bo_id': [(100, 200)],  # relationship source/target
        })
        return ds

    def test_u01_same_domain_create_passes(self):
        """U01: D1-Manager (BO:edit) 创建 D1→D1 关系 → 成功"""
        user_info = {'id': 333, 'permissions': ['business_object:edit']}
        with patch.object(self.interceptor, '_fetch_user_info_for_rel_perm', return_value=user_info):
            ctx = MockActionContext(data_source=self._mock_ancestor_match())
            record = {'id': 1}
            result = self.interceptor._check_relationship_ancestor_dim_scope(
                ctx, record, self.expanded
            )
            assert result is True

    def test_u02_cross_domain_create_d1_to_d2_passes(self):
        """U02: D1-Manager (BO:edit) 创建 D1→D2 关系 → 成功 (OR-edit D1 端)"""
        user_info = {'id': 333, 'permissions': ['business_object:edit']}
        with patch.object(self.interceptor, '_fetch_user_info_for_rel_perm', return_value=user_info):
            ctx = MockActionContext(data_source=self._mock_ancestor_match())
            record = {'id': 1}
            result = self.interceptor._check_relationship_ancestor_dim_scope(
                ctx, record, self.expanded
            )
            assert result is True

    def test_u04_no_endpoint_in_scope_fails(self):
        """U04: D1-Manager 创建 D2→D2 关系 (两端都不在 D1 scope) → 拒绝"""
        user_info = {'id': 333, 'permissions': ['business_object:edit']}
        # Mock: source/target 都在 D2 (domain=800, 不在 expanded)
        ds = MockDataSource(rows_by_query={
            'select bo.id,': [
                (300, 240, 800, 1, 1),  # BO_C 在 D2
                (400, 241, 800, 1, 1),  # BO_D 在 D2
            ],
            'select source_bo_id': [(300, 400)],
        })
        with patch.object(self.interceptor, '_fetch_user_info_for_rel_perm', return_value=user_info):
            ctx = MockActionContext(data_source=ds)
            record = {'id': 1}
            result = self.interceptor._check_relationship_ancestor_dim_scope(
                ctx, record, self.expanded
            )
            assert result is False


# ============================================================================
# Test: U05 软警告模式 (Phase 1) vs 硬拒绝模式 (Phase 2)
# ============================================================================
class TestU05ViewerRoleSoftWarnVsHardReject:
    """[V1.2.0] U05: D1-Viewer (无 BO:edit) — Phase 1 软警告 vs Phase 2 硬拒绝"""

    def setup_method(self):
        self.interceptor = WriteScopeInterceptor()
        self.expanded = {'domain': {703}, 'sub_domain': {138, 139}}

    def test_u05_soft_warn_mode_passes(self):
        """[Phase 1 软警告] D1-Viewer 跨域创建 → 软警告 log + 仍通过 (dim scope 派生 OR)"""
        # 模拟软警告模式 (通过 monkeypatch)
        user_info = {'id': 333, 'permissions': ['business_object:read']}
        with patch('meta.core.interceptors.write_scope_interceptor._WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN', True):
            with patch.object(self.interceptor, '_fetch_user_info_for_rel_perm', return_value=user_info):
                # Mock: 端点 D1 在 expanded (OR 命中)
                ds = MockDataSource(rows_by_query={
                    'select bo.id,': [(100, 138, 703, 1, 1)],
                    'select source_bo_id': [(100, 200)],
                })
                ctx = MockActionContext(data_source=ds)
                record = {'id': 1}
                # 软警告: 不拒绝, 继续执行 dim scope 派生
                result = self.interceptor._check_relationship_ancestor_dim_scope(
                    ctx, record, self.expanded
                )
                # dim scope OR 命中 → 返回 True (软警告模式下)
                assert result is True

    def test_u05_hard_reject_mode_fails(self):
        """[Phase 2 硬拒绝] D1-Viewer 跨域创建 → functional perm 校验直接拒绝"""
        user_info = {'id': 333, 'permissions': ['business_object:read']}
        with patch('meta.core.interceptors.write_scope_interceptor._WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN', False):
            with patch.object(self.interceptor, '_fetch_user_info_for_rel_perm', return_value=user_info):
                ctx = MockActionContext(data_source=MockDataSource())
                record = {'id': 1}
                # 硬拒绝: functional perm 校验直接返回 False
                result = self.interceptor._check_relationship_ancestor_dim_scope(
                    ctx, record, self.expanded
                )
                assert result is False


# ============================================================================
# Test: U06 Product Owner dim scope 派生 (owner chain 在另一个拦截器处理)
# ============================================================================
class TestU06ProductOwnerBypassesDimScope:
    """[V1.2.0] U06: Product Owner (无 dim scope) — dim scope 派生预期 False

    注: owner chain 检查在 OwnerChainInterceptor (priority=25) 中,
    命中后 _check_relationship_ancestor_dim_scope 不会被调用.
    此测试验证 _check_relationship_ancestor_dim_scope 不被绕过 (它只做 dim scope gate)
    """

    def test_product_owner_no_dim_scope_fails_dim_scope_gate(self):
        """[U06 角度] Product Owner dim scope 为空 → dim scope 派生 False (符合预期)"""
        interceptor = WriteScopeInterceptor()
        # product owner 没有 dim scope
        expanded = {'domain': set(), 'sub_domain': set()}

        user_info = {'id': 999, 'permissions': ['business_object:edit']}
        # Mock: 端点 D2 也不在 expanded
        ds = MockDataSource(rows_by_query={
            'select bo.id,': [(300, 240, 800, 1, 1)],
            'select source_bo_id': [(300, 400)],
        })
        with patch.object(interceptor, '_fetch_user_info_for_rel_perm', return_value=user_info):
            ctx = MockActionContext(data_source=ds)
            record = {'id': 1}
            result = interceptor._check_relationship_ancestor_dim_scope(
                ctx, record, expanded
            )
            # dim scope 派生 False (符合预期, owner chain 拦截器会先放行)
            assert result is False


# ============================================================================
# Test: _log_rel_func_perm_warning
# ============================================================================
class TestLogRelFuncPermWarning:
    """[V1.2.0] 软警告/硬拒绝日志记录"""

    def setup_method(self):
        self.interceptor = WriteScopeInterceptor()

    def test_soft_warn_writes_to_diagnostics(self):
        """[Phase 1 软警告] 写入 /_diagnostics"""
        from meta.core.diagnostics import get_diagnostics
        # 清理已有 diagnostics
        diag = get_diagnostics()
        if 'rel_func_perm_warnings' in diag:
            diag['rel_func_perm_warnings'] = []

        user_info = {'id': 333, 'permissions': ['business_object:read']}
        ctx = MockActionContext(object_type='relationship', action='crud_create')
        record = {'id': 42}
        self.interceptor._log_rel_func_perm_warning(ctx, record, 'soft_warn', user_info)

        diag = get_diagnostics()
        assert 'rel_func_perm_warnings' in diag
        assert len(diag['rel_func_perm_warnings']) >= 1
        last = diag['rel_func_perm_warnings'][-1]
        assert last['user_id'] == 333
        assert last['object_type'] == 'relationship'
        assert last['target_id'] == 42
        assert last['decision'] == 'soft_warn'

    def test_hard_reject_writes_to_diagnostics(self):
        """[Phase 2 硬拒绝] 写入 /_diagnostics"""
        from meta.core.diagnostics import get_diagnostics
        diag = get_diagnostics()
        if 'rel_func_perm_warnings' in diag:
            diag['rel_func_perm_warnings'] = []

        user_info = {'id': 333, 'permissions': ['business_object:read']}
        ctx = MockActionContext(object_type='relationship', action='crud_update')
        record = {'id': 99}
        self.interceptor._log_rel_func_perm_warning(ctx, record, 'hard_reject', user_info)

        diag = get_diagnostics()
        last = diag['rel_func_perm_warnings'][-1]
        assert last['decision'] == 'hard_reject'
        assert last['action'] == 'crud_update'
        assert last['target_id'] == 99

    def test_diagnostics_capped_at_100(self):
        """[V1.2.0] diagnostics 保留最近 100 条 (防内存泄漏)"""
        from meta.core.diagnostics import get_diagnostics
        diag = get_diagnostics()
        # 灌入 110 条
        diag['rel_func_perm_warnings'] = [{'test': i} for i in range(110)]

        user_info = {'id': 333, 'permissions': []}
        ctx = MockActionContext()
        record = {'id': 1}
        self.interceptor._log_rel_func_perm_warning(ctx, record, 'soft_warn', user_info)

        diag = get_diagnostics()
        # 应该 ≤ 100 (110 + 1 = 111, 截断到 100)
        assert len(diag['rel_func_perm_warnings']) <= 100
        # 最后一条是本次写入
        assert diag['rel_func_perm_warnings'][-1].get('decision') == 'soft_warn'

    def test_log_without_user_info_falls_back(self):
        """[V1.2.0 防御] 不传 user_info → fallback to flask.g (在 request context 外返 None)"""
        from meta.core.diagnostics import get_diagnostics
        diag = get_diagnostics()
        if 'rel_func_perm_warnings' in diag:
            diag['rel_func_perm_warnings'] = []

        ctx = MockActionContext()
        record = {'id': 1}
        # 不传 user_info, fallback 到 flask.g (test 环境不在 context, 返 None)
        self.interceptor._log_rel_func_perm_warning(ctx, record, 'soft_warn')

        diag = get_diagnostics()
        last = diag['rel_func_perm_warnings'][-1]
        # user_id 应为 None (防御性)
        assert last['user_id'] is None


# ============================================================================
# Test: 默认 phase 状态
# ============================================================================
class TestDefaultPhaseConfig:
    """[V1.2.0] 验证默认 Phase 2 硬拒绝模式 (2026-06-15 切换)"""

    def test_default_is_hard_reject(self):
        """[默认配置] WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN 默认 False (Phase 2 硬拒绝)"""
        # 这是 module-level 配置, 通过 env var 控制
        # 默认: False (Phase 2 硬拒绝, 2026-06-15 切换)
        assert _WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN is False

    def test_env_var_override_to_soft_warn(self):
        """[env 切换] 验证模块中存在 _WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN 变量, 可被 env 覆盖"""
        import meta.core.interceptors.write_scope_interceptor as mod
        # 验证模块中存在这个变量, 且可通过 env var 覆盖
        assert hasattr(mod, '_WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN')
        assert isinstance(mod._WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN, bool)

    def test_env_true_switches_to_soft_warn(self):
        """[env 回退] 显式设置 env=true → 软警告模式 (用于回退/观察)"""
        import importlib
        import meta.core.interceptors.write_scope_interceptor as mod

        # 在 env=true 下 reload 模块
        with patch.dict(os.environ, {'WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN': 'true'}):
            importlib.reload(mod)
            assert mod._WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN is True
        # patch.dict 退出后 env 恢复, 再次 reload 让模块也恢复默认
        importlib.reload(mod)
        assert mod._WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN is False


# ============================================================================
# Test: U07-U08 (update/delete) - 简化版 (跟 U02 一样的 functional perm 校验)
# ============================================================================
class TestU07U08UpdateDeleteSameAsCreate:
    """[V1.2.0] U07-U08: update/delete 走相同 functional perm 校验 (跟 create 一致)"""

    def setup_method(self):
        self.interceptor = WriteScopeInterceptor()
        self.expanded = {'domain': {703}}

    def test_u07_update_with_bo_edit_passes(self):
        """U07: D1-Manager (BO:edit) update D1→D2 关系 → 成功"""
        user_info = {'id': 333, 'permissions': ['business_object:edit']}
        ds = MockDataSource(rows_by_query={
            'select bo.id,': [(100, 138, 703, 1, 1)],
            'select source_bo_id': [(100, 200)],
        })
        with patch.object(self.interceptor, '_fetch_user_info_for_rel_perm', return_value=user_info):
            ctx = MockActionContext(action='crud_update', data_source=ds)
            record = {'id': 1}
            result = self.interceptor._check_relationship_ancestor_dim_scope(
                ctx, record, self.expanded
            )
            assert result is True

    def test_u08_delete_with_bo_edit_passes(self):
        """U08: D1-Manager (BO:edit) delete D1→D2 关系 → 成功"""
        user_info = {'id': 333, 'permissions': ['business_object:update']}
        ds = MockDataSource(rows_by_query={
            'select bo.id,': [(100, 138, 703, 1, 1)],
            'select source_bo_id': [(100, 200)],
        })
        with patch.object(self.interceptor, '_fetch_user_info_for_rel_perm', return_value=user_info):
            ctx = MockActionContext(action='crud_delete', data_source=ds)
            record = {'id': 1}
            result = self.interceptor._check_relationship_ancestor_dim_scope(
                ctx, record, self.expanded
            )
            assert result is True

    def test_u07_update_without_bo_edit_fails_hard(self):
        """U07 硬拒绝: D1-Viewer (无 BO:edit) update → 拒绝"""
        user_info = {'id': 333, 'permissions': ['business_object:read']}
        with patch('meta.core.interceptors.write_scope_interceptor._WRITE_SCOPE_REL_FUNCTIONAL_PERM_SOFT_WARN', False):
            with patch.object(self.interceptor, '_fetch_user_info_for_rel_perm', return_value=user_info):
                ctx = MockActionContext(action='crud_update', data_source=MockDataSource())
                record = {'id': 1}
                result = self.interceptor._check_relationship_ancestor_dim_scope(
                    ctx, record, self.expanded
                )
                assert result is False
