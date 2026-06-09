# -*- coding: utf-8 -*-
"""
[TEST] test_permission_v101.py — v1.0.1 permission_interceptor 单元测试
[DESCRIPTION] 覆盖:
- A.4: read/list/query 合并 (FR-001)
- A.5a: 父读 audit-only (FR-003 D9) + env 升级
- A.5b.1: 链 read 类型级 audit-only (FR-003b.1 D10) + env 升级
- A.5b.2: 链 read 实例级硬拒 (FR-003b.2 D13)
- admin 跳过所有
- 通配符 '*' 跳过

[USAGE]
    python d:\filework\test.py --file meta/tests/test_permission_v101.py
    或
    pytest meta/tests/test_permission_v101.py  # 必须用 test.py 入口
"""
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# 确保路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'excel-to-diagram'))


class TestReadListMerge(unittest.TestCase):
    """[A.4] FR-001: crud_list / crud_query 映射到 'read' 权限"""

    def setUp(self):
        from meta.core.interceptors.permission_interceptor import _ACTION_PERMISSION_SUFFIX
        self.suffix = _ACTION_PERMISSION_SUFFIX

    def test_crud_list_uses_read(self):
        """[v1.0.1] crud_list 应映射到 read, 而不是 list"""
        self.assertEqual(self.suffix['crud_list'], 'read',
                         'crud_list 应该映射到 read 权限 (修复 TEST60 403)')

    def test_crud_query_uses_read(self):
        """[v1.0.1] crud_query 应映射到 read"""
        self.assertEqual(self.suffix['crud_query'], 'read',
                         'crud_query 应该映射到 read 权限')

    def test_crud_read_uses_read(self):
        """[v1.0.1] crud_read 仍用 read"""
        self.assertEqual(self.suffix['crud_read'], 'read')

    def test_crud_create_uses_create(self):
        """[v1.0.1] crud_create 仍用 create"""
        self.assertEqual(self.suffix['crud_create'], 'create')

    def test_crud_update_uses_update(self):
        """[v1.0.1] crud_update 仍用 update"""
        self.assertEqual(self.suffix['crud_update'], 'update')

    def test_crud_delete_uses_delete(self):
        """[v1.0.1] crud_delete 仍用 delete"""
        self.assertEqual(self.suffix['crud_delete'], 'delete')


class TestBoYamlCache(unittest.TestCase):
    """[BoYamlCache] 测试 BO 关系查询"""

    def setUp(self):
        from meta.core.bo_yaml_cache import BoYamlCache
        self.BoYamlCache = BoYamlCache

    def test_get_parent_product_is_none(self):
        """product 是顶层, 无父"""
        self.assertIsNone(self.BoYamlCache.get_parent('product'))

    def test_get_parent_version_is_product(self):
        """version 的父是 product"""
        parent = self.BoYamlCache.get_parent('version')
        self.assertIsNotNone(parent)
        self.assertEqual(parent['object'], 'product')
        self.assertEqual(parent['field'], 'product_id')

    def test_get_parent_chain_sub_domain_4_levels(self):
        """sub_domain 的 chain 应是 4 级: sub_domain → domain → version → product"""
        chain = self.BoYamlCache.get_parent_chain('sub_domain')
        self.assertEqual(chain, ['sub_domain', 'domain', 'version', 'product'])

    def test_get_parent_chain_product_top(self):
        """product 是顶层, chain 只有自身"""
        chain = self.BoYamlCache.get_parent_chain('product')
        self.assertEqual(chain, ['product'])

    def test_get_parent_chain_business_object_6_levels(self):
        """business_object 是最底层, chain 6 级"""
        chain = self.BoYamlCache.get_parent_chain('business_object')
        self.assertEqual(len(chain), 6)
        self.assertEqual(chain[0], 'business_object')
        self.assertEqual(chain[-1], 'product')

    def test_is_top_bo(self):
        """is_top_bo 判断"""
        self.assertTrue(self.BoYamlCache.is_top_bo('product'))
        self.assertFalse(self.BoYamlCache.is_top_bo('version'))
        self.assertFalse(self.BoYamlCache.is_top_bo('business_object'))

    def test_dump(self):
        """dump 暴露给 /_diagnostics"""
        d = self.BoYamlCache.dump()
        self.assertIn('parent_map', d)
        self.assertIn('top_bos', d)
        self.assertEqual(d['version'], 'v1.0.1-hardcoded')

    def test_chain_no_cycle(self):
        """防御性: 即使外部有循环配置, 也能防无限循环"""
        # 模拟循环: a → b → a
        # BoYamlCache 设计是查询已配置, 这里只验证 visited 集合生效
        # 直接调用现有链, 应不会循环
        chain = self.BoYamlCache.get_parent_chain('sub_domain')
        self.assertEqual(len(chain), len(set(chain)),
                         'chain 中不应有重复元素 (防循环)')


class TestHelperFunctions(unittest.TestCase):
    """[v1.0.1] user_info_has_perm helper"""

    def setUp(self):
        from meta.core.interceptors.permission_interceptor import user_info_has_perm
        self.has_perm = user_info_has_perm

    def test_empty_permissions_returns_false(self):
        self.assertFalse(self.has_perm([], 'product:read'))
        self.assertFalse(self.has_perm(set(), 'product:read'))
        self.assertFalse(self.has_perm(None, 'product:read'))

    def test_wildcard_returns_true(self):
        self.assertTrue(self.has_perm(['*'], 'product:read'))
        self.assertTrue(self.has_perm({'*'}, 'any:action'))

    def test_direct_match_returns_true(self):
        self.assertTrue(self.has_perm(['product:read', 'domain:read'], 'product:read'))

    def test_no_match_returns_false(self):
        self.assertFalse(self.has_perm(['product:read'], 'domain:read'))


class TestParentReadAdvisory(unittest.TestCase):
    """[A.5a] FR-003 D9: 父读 audit-only 模式"""

    def setUp(self):
        from meta.core.interceptors.permission_interceptor import (
            PermissionInterceptor, ParentPermissionDenied
        )
        self.interceptor = PermissionInterceptor()
        self.ParentPermissionDenied = ParentPermissionDenied

    def _make_context(self, action: str, object_type: str = 'sub_domain'):
        ctx = MagicMock()
        ctx.action = action
        ctx.object_type = object_type
        return ctx

    def test_no_parent_config_skips(self):
        """无父配置的 BO (product) 跳过 audit"""
        ctx = self._make_context('crud_create', object_type='product')
        user_info = {'id': 1, 'permissions': set()}  # 无 product:read
        # product 无父, 不触发
        self.interceptor._check_parent_read_advisory(ctx, user_info)
        # 无异常 = pass

    def test_has_parent_read_skips(self):
        """有父 read 权限 → 不告警"""
        ctx = self._make_context('crud_create', object_type='sub_domain')
        user_info = {'id': 1, 'permissions': {'sub_domain:create', 'domain:read'}}
        # sub_domain 的父是 domain, user 有 domain:read
        self.interceptor._check_parent_read_advisory(ctx, user_info)
        # 无异常 = pass

    def test_missing_parent_read_audit_only(self):
        """缺父 read → audit-only (不抛错)"""
        ctx = self._make_context('crud_create', object_type='sub_domain')
        user_info = {'id': 1, 'permissions': {'sub_domain:create'}}  # 无 domain:read
        # 默认 audit-only, 不抛错
        self.interceptor._check_parent_read_advisory(ctx, user_info)
        # 无异常 = pass

    def test_wildcard_skips(self):
        """'*' 通配符跳过"""
        ctx = self._make_context('crud_create', object_type='sub_domain')
        user_info = {'id': 1, 'permissions': {'*'}}
        self.interceptor._check_parent_read_advisory(ctx, user_info)


class TestChainReadTypeLevel(unittest.TestCase):
    """[A.5b.1] FR-003b.1 D10: 链 read 类型级 audit-only"""

    def setUp(self):
        from meta.core.interceptors.permission_interceptor import PermissionInterceptor
        self.interceptor = PermissionInterceptor()

    def _make_context(self, action: str, object_type: str = 'sub_domain'):
        ctx = MagicMock()
        ctx.action = action
        ctx.object_type = object_type
        return ctx

    def test_has_any_chain_read_skips(self):
        """链中任一 read 即可 (B 链中模式)"""
        ctx = self._make_context('crud_create', object_type='sub_domain')
        # sub_domain chain: [sub_domain, domain, version, product]
        # 有 product:read 即通过
        user_info = {'id': 1, 'permissions': {'sub_domain:create', 'product:read'}}
        self.interceptor._check_chain_read(ctx, user_info)

    def test_no_chain_read_audit_only(self):
        """链中无 read → audit-only"""
        ctx = self._make_context('crud_create', object_type='sub_domain')
        # chain 全部无 read
        user_info = {'id': 1, 'permissions': {'sub_domain:create'}}
        # 默认 audit-only, 不抛错
        self.interceptor._check_chain_read(ctx, user_info)

    def test_read_actions_skip_chain_check(self):
        """D11 A2: crud_read/list/query 不触发链校验"""
        for action in ('crud_read', 'crud_list', 'crud_query'):
            ctx = self._make_context(action, object_type='sub_domain')
            user_info = {'id': 1, 'permissions': set()}
            self.interceptor._check_chain_read(ctx, user_info)  # 无异常

    def test_top_bo_skips(self):
        """顶层 BO (product) chain 为 [product], 仍校验自身 read"""
        ctx = self._make_context('crud_create', object_type='product')
        user_info = {'id': 1, 'permissions': {'product:create'}}
        # product:read 缺失 → audit-only
        self.interceptor._check_chain_read(ctx, user_info)


class TestChainReadInstanceLevel(unittest.TestCase):
    """[A.5b.2] FR-003b.2 D13: 链 read 实例级硬拒"""

    def setUp(self):
        from meta.core.interceptors.permission_interceptor import (
            PermissionInterceptor, ChainInstanceOutOfScope
        )
        self.interceptor = PermissionInterceptor()
        self.ChainInstanceOutOfScope = ChainInstanceOutOfScope

    def test_no_target_id_skips_instance_check(self):
        """无 target_id 跳过实例级 (CREATE 新数据场景)"""
        from unittest.mock import MagicMock
        ctx = MagicMock()
        ctx.action = 'crud_create'
        ctx.object_type = 'sub_domain'
        user_info = {'id': 1, 'permissions': {'sub_domain:create'}}
        # 无 target_id → 跳过
        self.interceptor._check_chain_read(ctx, user_info, target_id=None)

    def test_target_id_in_scope_passes(self):
        """target_id 解析后所有 parent 在 data scope 内 → 通过"""
        from unittest.mock import MagicMock, patch
        ctx = MagicMock()
        ctx.action = 'crud_update'
        ctx.object_type = 'sub_domain'
        user_info = {
            'id': 1,
            'permissions': {'sub_domain:create', 'domain:read'},
            'data_scope': {'domain': [5, 6, 7], 'version': [3, 4], 'product': [1, 2]}
        }
        # Mock BoYamlCache.resolve_parent_chain
        with patch('meta.core.bo_yaml_cache.BoYamlCache.resolve_parent_chain',
                   return_value=[
                       {'bo': 'domain', 'id': 5, 'field': 'domain_id'},
                       {'bo': 'version', 'id': 3, 'field': 'version_id'},
                       {'bo': 'product', 'id': 1, 'field': 'product_id'},
                   ]):
            self.interceptor._check_chain_read(ctx, user_info, target_id=100)
            # 都在 scope 内 → 无异常

    def test_target_id_out_of_scope_rejects(self):
        """target_id 解析后 parent 不在 data scope → 硬拒"""
        from unittest.mock import MagicMock, patch
        ctx = MagicMock()
        ctx.action = 'crud_update'
        ctx.object_type = 'sub_domain'
        user_info = {
            'id': 1,
            'permissions': {'sub_domain:create', 'domain:read'},
            'data_scope': {'domain': [5, 6], 'version': [3], 'product': [1]}  # version 4 缺失
        }
        with patch('meta.core.bo_yaml_cache.BoYamlCache.resolve_parent_chain',
                   return_value=[
                       {'bo': 'domain', 'id': 5, 'field': 'domain_id'},
                       {'bo': 'version', 'id': 4, 'field': 'version_id'},  # out of scope
                       {'bo': 'product', 'id': 1, 'field': 'product_id'},
                   ]):
            with self.assertRaises(self.ChainInstanceOutOfScope) as cm:
                self.interceptor._check_chain_read(ctx, user_info, target_id=100)
            # 验证异常 payload
            self.assertEqual(cm.exception.object_type, 'sub_domain')
            self.assertEqual(cm.exception.target_id, 100)
            self.assertEqual(len(cm.exception.out_of_scope_parents), 1)
            self.assertEqual(cm.exception.out_of_scope_parents[0]['bo'], 'version')
            self.assertEqual(cm.exception.out_of_scope_parents[0]['instance_id'], 4)


class TestEnvStrictMode(unittest.TestCase):
    """[A.5c] env 升级模式"""

    def test_parent_read_strict_mode_default_off(self):
        """默认 PARENT_READ_STRICT_MODE 未设 → audit-only"""
        # 确保 env 未设
        os.environ.pop('PARENT_READ_STRICT_MODE', None)
        # 重新 import 模块 (env 在 import 时读)
        import importlib
        import meta.core.interceptors.permission_interceptor as pi
        importlib.reload(pi)
        self.assertFalse(pi._PARENT_READ_STRICT_MODE)

    def test_chain_strict_mode_default_off(self):
        """默认 CHAIN_DERIVATION_STRICT_MODE 未设 → audit-only"""
        os.environ.pop('CHAIN_DERIVATION_STRICT_MODE', None)
        import importlib
        import meta.core.interceptors.permission_interceptor as pi
        importlib.reload(pi)
        self.assertFalse(pi._CHAIN_DERIVATION_STRICT_MODE)


class TestErrorCodes(unittest.TestCase):
    """[A.11] 错码 fix_hint 完整性"""

    def setUp(self):
        from meta.core.error_fix_hints import get_fix_hint
        self.get_hint = get_fix_hint

    def test_parent_permission_denied_hint(self):
        h = self.get_hint('parent_permission_denied')
        self.assertIsNotNone(h)
        self.assertIn('D9', h['fix_hint'])
        self.assertIn('PARENT_READ_STRICT_MODE', h['fix_hint'])

    def test_err_chain_read_denied_hint(self):
        h = self.get_hint('err_chain_read_denied')
        self.assertIsNotNone(h)
        self.assertIn('D10', h['fix_hint'])
        self.assertIn('CHAIN_DERIVATION_STRICT_MODE', h['fix_hint'])

    def test_err_chain_instance_out_of_scope_hint(self):
        h = self.get_hint('err_chain_instance_out_of_scope')
        self.assertIsNotNone(h)
        self.assertIn('D13', h['fix_hint'])
        self.assertIn('硬拒', h['fix_hint'])


class TestDiagnosticsModule(unittest.TestCase):
    """diagnostics 模块测试"""

    def setUp(self):
        from meta.core import diagnostics
        diagnostics.reset_diagnostics()

    def test_initial_state_empty(self):
        from meta.core.diagnostics import get_warning_summary
        s = get_warning_summary()
        self.assertEqual(s['parent_read_warnings'], 0)
        self.assertEqual(s['chain_read_warnings'], 0)
        self.assertEqual(s['chain_instance_out_of_scope'], 0)

    def test_append_warning(self):
        from meta.core.diagnostics import get_diagnostics, get_warning_summary
        diag = get_diagnostics()
        diag['parent_read_warnings'].append({
            'child_object': 'sub_domain',
            'parent_object': 'domain',
            'action': 'crud_create',
        })
        s = get_warning_summary()
        self.assertEqual(s['parent_read_warnings'], 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
