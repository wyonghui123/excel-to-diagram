# -*- coding: utf-8 -*-
"""
[FILE] test_write_scope_v2_1.py
[DESCRIPTION] WriteScopeInterceptor v2.1 写权限 × Dim Scope 联动校验测试
[COVERAGE]
  - 灰度开关 WRITE_SCOPE_V2_1_PERM_CHECK
  - _role_has_perm 通配模式 (exact / wildcard / no-suffix / admin)
  - _get_user_perm_codes per-request 缓存
  - _check_dim_scope 前置 perm 检查 (target_perm_suffix=update/create/delete)
  - 与 owner chain / admin / data_permissions fallback 兼容性

[SPEC] .trae/specs/auth-permission-system/write-scope-perm-link-v2.1-spec.md
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from unittest.mock import Mock, MagicMock, patch

from meta.core.interceptors.write_scope_interceptor import (
    WriteScopeInterceptor,
    WriteScopeDenied,
    _WRITE_SCOPE_V2_1_PERM_CHECK,
    _ACTION_TO_PERM_SUFFIX,
)


# ============================================================================
# Mock 辅助类
# ============================================================================
class MockDataSource:
    """模拟 DataSource, 根据 SQL 关键字返回预置结果"""

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
    """模拟 ActionContext"""

    def __init__(self, **kwargs):
        self.object_type = kwargs.get('object_type', 'service_module')
        self.action = kwargs.get('action', 'crud_update')
        self.params = kwargs.get('params', {'id': 1})
        self.data_source = kwargs.get('data_source', MockDataSource())
        self.user_id = kwargs.get('user_id', 1)
        self.user_info = kwargs.get('user_info', None)
        self.trace_id = kwargs.get('trace_id', 'test-trace')

    @property
    def object_id(self):
        if self.action in ('associate', 'dissociate', 'assign', 'unassign'):
            return self.params.get('src_id')
        return self.params.get('id')


# ============================================================================
# pytest fixture: Flask app context 用于设置 g.current_user
# ============================================================================
@pytest.fixture
def app_ctx():
    """提供 Flask app context, 便于 _get_user_perm_codes 设置 g.current_user"""
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
# 灰度开关 + Action 映射
# ============================================================================
class TestV2_1FlagsAndMapping:
    """[v2.1] 灰度开关 + action→perm suffix 映射"""

    def test_v2_1_perm_check_default_false(self):
        """默认 _WRITE_SCOPE_V2_1_PERM_CHECK=false (兼容 V1.1.8)"""
        assert _WRITE_SCOPE_V2_1_PERM_CHECK is False

    def test_action_to_perm_suffix_mapping(self):
        """action → perm suffix 映射完整"""
        assert _ACTION_TO_PERM_SUFFIX['crud_create'] == 'create'
        assert _ACTION_TO_PERM_SUFFIX['crud_update'] == 'update'
        assert _ACTION_TO_PERM_SUFFIX['crud_delete'] == 'delete'
        assert _ACTION_TO_PERM_SUFFIX['associate'] == 'update'
        assert _ACTION_TO_PERM_SUFFIX['dissociate'] == 'delete'

    def test_action_to_perm_suffix_default(self):
        """未知 action 默认 'update'"""
        assert _ACTION_TO_PERM_SUFFIX.get('unknown_action', 'update') == 'update'


# ============================================================================
# _role_has_perm 通配模式
# ============================================================================
class TestV2_1RoleHasPerm:
    """[v2.1] _role_has_perm 通配模式支持"""

    def setup_method(self):
        self.interceptor = WriteScopeInterceptor()

    def test_exact_match(self):
        """精确匹配: target='service_module:update' in user_perm"""
        assert self.interceptor._role_has_perm(
            1, 'service_module:update', {'service_module:update'}
        ) is True

    def test_admin_wildcard(self):
        """admin 通配: '*' in user_perm"""
        assert self.interceptor._role_has_perm(
            1, 'service_module:update', {'*'}
        ) is True

    def test_object_wildcard(self):
        """object 通配: 'service_module:*' in user_perm"""
        assert self.interceptor._role_has_perm(
            1, 'service_module:update', {'service_module:*'}
        ) is True
        assert self.interceptor._role_has_perm(
            1, 'service_module:delete', {'service_module:*'}
        ) is True

    def test_no_suffix_shorthand(self):
        """无后缀简写: 'service_module' in user_perm"""
        assert self.interceptor._role_has_perm(
            1, 'service_module:update', {'service_module'}
        ) is True

    def test_different_object_returns_false(self):
        """不同 object_type 不命中"""
        assert self.interceptor._role_has_perm(
            1, 'service_module:update', {'business_object:update'}
        ) is False

    def test_empty_perm_set_returns_false(self):
        """空 perm set 返回 False"""
        assert self.interceptor._role_has_perm(1, 'service_module:update', set()) is False

    def test_none_perm_set_returns_false(self):
        """None perm set 返回 False (防御性)"""
        assert self.interceptor._role_has_perm(1, 'service_module:update', None) is False

    def test_partial_wildcard_does_not_match_other_object(self):
        """object 通配仅作用于同 object"""
        assert self.interceptor._role_has_perm(
            1, 'business_object:update', {'service_module:*'}
        ) is False


# ============================================================================
# _get_user_perm_codes per-request 缓存
# ============================================================================
class TestV2_1GetUserPermCodes:
    """[v2.1] _get_user_perm_codes per-request 缓存"""

    def test_get_perm_from_g_current_user_list(self, app_ctx, set_current_user):
        """从 g.current_user.permissions (list) 提取"""
        set_current_user({
            'permissions': ['service_module:update', 'business_object:read']
        })
        interceptor = WriteScopeInterceptor()
        ctx = MockActionContext()
        result = interceptor._get_user_perm_codes(ctx)
        assert 'service_module:update' in result
        assert 'business_object:read' in result
        assert isinstance(result, set)

    def test_get_perm_from_set(self, app_ctx, set_current_user):
        """从 set 类型提取"""
        set_current_user({
            'permissions': {'*'}
        })
        interceptor = WriteScopeInterceptor()
        ctx = MockActionContext()
        result = interceptor._get_user_perm_codes(ctx)
        assert '*' in result

    def test_perm_codes_cached_in_g_current_user(self, app_ctx, set_current_user):
        """per-request 缓存到 g.current_user._perm_codes_cache"""
        user = {'permissions': ['service_module:update']}
        set_current_user(user)
        interceptor = WriteScopeInterceptor()
        ctx = MockActionContext()
        result1 = interceptor._get_user_perm_codes(ctx)
        # 第二次应直接读缓存
        result2 = interceptor._get_user_perm_codes(ctx)
        assert result1 == result2
        assert '_perm_codes_cache' in user
        assert user['_perm_codes_cache'] == result1

    def test_no_user_returns_empty_set(self, app_ctx):
        """无 g.current_user 时返回空 set"""
        # 不设置 g.current_user
        from flask import g
        if hasattr(g, 'current_user'):
            try:
                del g.current_user
            except Exception:
                pass
        interceptor = WriteScopeInterceptor()
        ctx = MockActionContext()
        result = interceptor._get_user_perm_codes(ctx)
        assert result == set()


# ============================================================================
# _check_dim_scope V2.1 前置 perm 检查 (env 开启)
# ============================================================================
class TestV2_1CheckDimScopeWithPermCheck:
    """[v2.1] _check_dim_scope 前置 perm 检查 (WRITE_SCOPE_V2_1_PERM_CHECK=true)"""

    def setup_method(self):
        self.interceptor = WriteScopeInterceptor()

    def _mock_role_ids(self, role_ids):
        """mock _get_user_role_ids 返回指定 role_ids"""
        return patch.object(
            self.interceptor, '_get_user_role_ids', return_value=role_ids
        )

    def test_role_with_perm_and_dim_scope_match(self, app_ctx, set_current_user):
        """Scenario 1.1: role 有 perm + dim scope 命中 → 通过"""
        set_current_user({
            'permissions': ['service_module:update'],
            '_role_ids_cache': [100],
        })
        with self._mock_role_ids([100]):
            with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.expand_dimension_values.return_value = {'service_module': {1}}
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
                        record = {'id': 1, 'service_module_id': 1}
                        result = self.interceptor._check_dim_scope(
                            ctx, 'service_module', record, user_id=333
                        )
                        assert result['matched'] is True

    def test_role_missing_perm_skipped(self, app_ctx, set_current_user):
        """Scenario 1.3: role 缺 perm → 直接跳过"""
        set_current_user({
            'permissions': ['business_object:update'],  # 没 service_module:update
            '_role_ids_cache': [100],
        })
        with self._mock_role_ids([100]):
            with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.expand_dimension_values.return_value = {'service_module': {1}}
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
                            ctx, 'service_module', record, user_id=333
                        )
                        # 角色因缺 perm 被 skip, matched=False
                        assert result['matched'] is False
                        # roles_checked 应包含 skipped='missing_functional_perm'
                        skipped = [r for r in result['roles_checked']
                                   if r.get('skipped') == 'missing_functional_perm']
                        assert len(skipped) == 1
                        assert skipped[0]['perm_required'] == 'service_module:update'

    def test_admin_wildcard_bypasses_perm_check(self, app_ctx, set_current_user):
        """Scenario 1.4: admin '*' 通配 → 跳过 perm 检查"""
        set_current_user({
            'permissions': ['*'],
            '_role_ids_cache': [100],
        })
        with self._mock_role_ids([100]):
            with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.expand_dimension_values.return_value = {'service_module': {1}}
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
                        # perm_check='passed' 表示通过了 perm 检查
                        passed = [r for r in result['roles_checked']
                                  if r.get('perm_check') == 'passed']
                        assert len(passed) >= 1

    def test_target_perm_suffix_create(self, app_ctx, set_current_user):
        """Scenario 2.1: target_perm_suffix='create' 时检查 :create"""
        set_current_user({
            'permissions': ['service_module:update'],  # 只有 update, 没 create
            '_role_ids_cache': [100],
        })
        with self._mock_role_ids([100]):
            with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.expand_dimension_values.return_value = {'service_module': {1}}
                with patch.object(
                    self.interceptor, '_record_matches_cond', return_value=True
                ):
                    with patch(
                        'meta.core.interceptors.write_scope_interceptor._WRITE_SCOPE_V2_1_PERM_CHECK',
                        True,
                    ):
                        ctx = MockActionContext(object_type='service_module', action='crud_create')
                        record = {'id': 1}
                        result = self.interceptor._check_dim_scope(
                            ctx, 'service_module', record,
                            user_id=333, target_perm_suffix='create'
                        )
                        # perm_required 应该是 service_module:create
                        skipped = [r for r in result['roles_checked']
                                   if r.get('skipped') == 'missing_functional_perm']
                        assert len(skipped) == 1
                        assert skipped[0]['perm_required'] == 'service_module:create'

    def test_target_perm_suffix_delete(self, app_ctx, set_current_user):
        """Scenario 2.3: target_perm_suffix='delete' 时检查 :delete"""
        set_current_user({
            'permissions': ['service_module:update'],
            '_role_ids_cache': [100],
        })
        with self._mock_role_ids([100]):
            with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.expand_dimension_values.return_value = {'service_module': {1}}
                with patch.object(
                    self.interceptor, '_record_matches_cond', return_value=True
                ):
                    with patch(
                        'meta.core.interceptors.write_scope_interceptor._WRITE_SCOPE_V2_1_PERM_CHECK',
                        True,
                    ):
                        ctx = MockActionContext(object_type='service_module', action='crud_delete')
                        record = {'id': 1}
                        result = self.interceptor._check_dim_scope(
                            ctx, 'service_module', record,
                            user_id=333, target_perm_suffix='delete'
                        )
                        skipped = [r for r in result['roles_checked']
                                   if r.get('skipped') == 'missing_functional_perm']
                        assert len(skipped) == 1
                        assert skipped[0]['perm_required'] == 'service_module:delete'

    def test_object_wildcard_in_user_perms(self, app_ctx, set_current_user):
        """Scenario 3.3: user perm 含 'service_module:*' → 所有 action 都通过"""
        set_current_user({
            'permissions': ['service_module:*'],  # object 通配
            '_role_ids_cache': [100],
        })
        with self._mock_role_ids([100]):
            with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.expand_dimension_values.return_value = {'service_module': {1}}
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
                            ctx, 'service_module', record,
                            user_id=333, target_perm_suffix='update'
                        )
                        assert result['matched'] is True

    def test_no_suffix_shorthand_in_user_perms(self, app_ctx, set_current_user):
        """Scenario 3.4: user perm 含 'service_module' (无后缀简写) → 所有 action 通过"""
        set_current_user({
            'permissions': ['service_module'],  # 无后缀简写
            '_role_ids_cache': [100],
        })
        with self._mock_role_ids([100]):
            with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.expand_dimension_values.return_value = {'service_module': {1}}
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
                            ctx, 'service_module', record, user_id=333
                        )
                        assert result['matched'] is True


# ============================================================================
# _check_dim_scope V1.1.8 兼容模式 (env 关闭)
# ============================================================================
class TestV2_1LegacyV118Compatibility:
    """[v2.1] WRITE_SCOPE_V2_1_PERM_CHECK=false 时保持 V1.1.8 行为"""

    def setup_method(self):
        self.interceptor = WriteScopeInterceptor()

    def test_no_perm_check_when_disabled(self, app_ctx, set_current_user):
        """默认关闭时, 即使 perm 缺失, dim scope 检查照常执行"""
        set_current_user({
            'permissions': [],  # 无 perm
            '_role_ids_cache': [100],
        })
        with patch.object(
            self.interceptor, '_get_user_role_ids', return_value=[100]
        ):
            with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.expand_dimension_values.return_value = {'service_module': {1}}
                mock_engine.derive_data_conditions.return_value = {
                    'service_module': 'service_module.id IN (1)'
                }
                with patch.object(
                    self.interceptor, '_record_matches_cond', return_value=True
                ):
                    with patch(
                        'meta.core.interceptors.write_scope_interceptor._WRITE_SCOPE_V2_1_PERM_CHECK',
                        False,
                    ):
                        ctx = MockActionContext(object_type='service_module', action='crud_update')
                        record = {'id': 1}
                        result = self.interceptor._check_dim_scope(
                            ctx, 'service_module', record, user_id=333
                        )
                        # V1.1.8 行为: 无 perm 也允许 dim scope 命中
                        assert result['matched'] is True
                        # 不应有 skipped='missing_functional_perm'
                        skipped = [r for r in result['roles_checked']
                                   if r.get('skipped') == 'missing_functional_perm']
                        assert len(skipped) == 0
                        # 也不应有 perm_check 字段
                        for r in result['roles_checked']:
                            assert 'perm_check' not in r


# ============================================================================
# 实际场景: TEST333W 越权场景
# ============================================================================
class TestV2_1TEST333WScenario:
    """[v2.1] TEST333W 角色: service_module:update + dim scope=domain=[703]

    改 SM (domain=703) → 通过
    改 SM (domain=706) → 拒绝 (V2.1 因 dim scope 不命中; V1.1.8 也会拒绝, 但原因不同)
    """

    def setup_method(self):
        self.interceptor = WriteScopeInterceptor()

    def test_edit_sm_in_scope_703_allowed(self, app_ctx, set_current_user):
        """同域 SM (domain=703) → 通过 (经 _check_ancestor_dim_scope 路径)

        object_type=service_module, expanded={'domain': {703}}, record sub_domain_id=138(domain=703)
        走 update 路径 → _check_ancestor_dim_scope 返回 True
        """
        set_current_user({
            'permissions': ['service_module:update', 'service_module:read'],
            '_role_ids_cache': [5970],
        })
        with patch.object(
            self.interceptor, '_get_user_role_ids', return_value=[5970]
        ):
            with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.expand_dimension_values.return_value = {'domain': {703}}
                with patch.object(
                    self.interceptor, '_check_ancestor_dim_scope', return_value=True
                ):
                    with patch(
                        'meta.core.interceptors.write_scope_interceptor._WRITE_SCOPE_V2_1_PERM_CHECK',
                        True,
                    ):
                        ctx = MockActionContext(object_type='service_module', action='crud_update')
                        record = {'id': 1, 'sub_domain_id': 138}
                        result = self.interceptor._check_dim_scope(
                            ctx, 'service_module', record, user_id=3385
                        )
                        assert result['matched'] is True
                        # perm_check='passed' 说明 v2.1 perm 前置通过
                        passed = [r for r in result['roles_checked']
                                  if r.get('perm_check') == 'passed']
                        assert len(passed) >= 1

    def test_edit_sm_out_of_scope_706_denied(self, app_ctx, set_current_user):
        """跨域 SM (domain=706) → 拒绝 (dim scope 不命中)"""
        set_current_user({
            'permissions': ['service_module:update', 'service_module:read'],
            '_role_ids_cache': [5970],
        })
        with patch.object(
            self.interceptor, '_get_user_role_ids', return_value=[5970]
        ):
            with patch('meta.services.dimension_scope_engine.DimensionScopeEngine') as mock_engine_cls:
                mock_engine = mock_engine_cls.return_value
                mock_engine.expand_dimension_values.return_value = {'domain': {703}}
                with patch.object(
                    self.interceptor, '_check_ancestor_dim_scope', return_value=False
                ):
                    with patch(
                        'meta.core.interceptors.write_scope_interceptor._WRITE_SCOPE_V2_1_PERM_CHECK',
                        True,
                    ):
                        ctx = MockActionContext(object_type='service_module', action='crud_update')
                        record = {'id': 2, 'sub_domain_id': 200}  # domain=706
                        result = self.interceptor._check_dim_scope(
                            ctx, 'service_module', record, user_id=3385
                        )
                        assert result['matched'] is False
                        # perm_check='passed' 但 dim_scope 不命中 (ancestor_match=False)
                        passed = [r for r in result['roles_checked']
                                  if r.get('perm_check') == 'passed']
                        assert len(passed) >= 1


# ============================================================================
# 集成: V2.1 与 owner chain / admin 优先级
# ============================================================================
class TestV2_1PriorityIntegration:
    """[v2.1] V2.1 不影响 owner chain 优先 + admin 短路 (这些在 step 1/step 2 处理)"""

    def test_owner_check_unaffected_by_v2_1(self):
        """_check_owner_chain 不依赖 V2.1 perm check, 行为不变"""
        interceptor = WriteScopeInterceptor()
        record = {'id': 1, 'owner_id': 123}
        result = interceptor._check_owner_chain(
            MockActionContext(), 'product', record, 123
        )
        assert result['matched'] is True