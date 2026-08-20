# -*- coding: utf-8 -*-
"""
Phase 2 P2.6 (写) — WriteScopeInterceptor Feature Flag Hook 集成测试

[覆盖范围]
  1. effective_intents_enabled=False (默认) → 走原逻辑 (零影响)
  2. effective_intents_enabled=True → 调用 IntentScopeAdapter.check_record_allowed
  3. hook 允许 → 跳过 legacy _check_target
  4. hook 拒绝 → 抛 WriteScopeDenied
  5. hook 异常 → 安全回退到 legacy
  6. admin 用户跳过 hook
  7. 无 role_ids / 无 target → 回退到 legacy
  8. 多 target (associate src+dst) 全部通过才放行
  9. 任一 target 拒绝即抛异常
 10. action → action_name 映射 (create/update/delete)

[设计原则]
  - 跟 test_interceptor_phase2_hook.py (读 hook) 风格保持一致
  - mock 边界: _get_db_path / _get_role_ids / IntentScopeAdapter
  - 不依赖 Flask g.current_user (避免 RuntimeError)
"""
import os
import sys
import json
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

os.environ['TEST_ENTRY'] = '1'
os.environ['ALLOW_RAW_SQL'] = '1'


@pytest.fixture
def write_hook_db():
    """创建测试 DB (含 role_effective_intents + 业务表)"""
    tmp_dir = tempfile.mkdtemp(prefix='write_hook_')
    db_path = os.path.join(tmp_dir, 'test.db')

    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE role_effective_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            bo_id VARCHAR(100) NOT NULL,
            action_name VARCHAR(100) NOT NULL,
            data_scope TEXT,
            derivation_mode VARCHAR(20) DEFAULT 'static',
            source VARCHAR(50) DEFAULT 'derived',
            is_stale INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (role_id, bo_id, action_name)
        );

        CREATE TABLE group_roles (
            group_id INTEGER, role_id INTEGER
        );
        CREATE TABLE user_group_members (
            user_id INTEGER, group_id INTEGER
        );

        -- 用户 999 → group 1 → role 100
        INSERT INTO group_roles VALUES (1, 100);
        INSERT INTO user_group_members VALUES (999, 1);

        -- role 100 对 product 有 update 权限 (owner_id = ${user.id})
        INSERT INTO role_effective_intents
            (role_id, bo_id, action_name, data_scope, source)
        VALUES
            (100, 'product', 'update',
             '{"include":[{"field":"owner_id","op":"=","value":"${user.id}"}],"exclude":[]}',
             'derived');

        -- 业务表 (products 含 owner_id, 用于 _matches_any 查询)
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            code TEXT, name TEXT, owner_id INTEGER, created_by INTEGER,
            visibility TEXT
        );
        INSERT INTO products VALUES
            (1, 'P1', 'Product 1', 999, 999, 'public'),
            (2, 'P2', 'Product 2', 888, 888, 'public'),
            (3, 'P3', 'Product 3', 999, 999, 'private');
    ''')
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def write_mock_context(write_hook_db):
    """构造 mock ActionContext (crud_update product 1)"""
    ctx = MagicMock()
    ctx.user_id = 999
    ctx.object_type = 'product'
    ctx.object_id = 1
    ctx.action = 'crud_update'
    ctx.params = {}
    ctx.extra = {}
    ctx.is_query_action = False

    # mock user_info (模拟 flask.g.current_user)
    ctx.user_info = {'user_id': 999, 'id': 999, 'permissions': []}

    # mock data_source
    ds = MagicMock()
    ds.db_path = write_hook_db

    def execute(sql, params=None):
        conn = sqlite3.connect(write_hook_db)
        cursor = conn.execute(sql, params or [])
        rows = cursor.fetchall()
        cols = [c[0] for c in cursor.description] if cursor.description else []
        conn.close()
        m = MagicMock()
        m.fetchall.return_value = rows
        m.fetchone.return_value = rows[0] if rows else None
        m.description = [(c,) for c in cols]
        return m

    ds.execute.side_effect = execute
    ctx.data_source = ds
    return ctx


class TestWriteScopePhase2Hook:
    """WriteScopeInterceptor Phase 2 Hook 测试"""

    @pytest.fixture(autouse=True)
    def reset_flag(self):
        """每个测试前后重置 flag"""
        from meta.core.permission_flags import reset_flags
        reset_flags()
        yield
        reset_flags()

    def _make_interceptor(self):
        """构造拦截器实例"""
        from meta.core.interceptors.write_scope_interceptor import WriteScopeInterceptor
        return WriteScopeInterceptor()

    def test_flag_off_uses_legacy_path(self, write_mock_context, write_hook_db):
        """flag=False → 不调用 _apply_effective_intents_write_check"""
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', False)

        interceptor = self._make_interceptor()

        with patch.object(
            interceptor, '_apply_effective_intents_write_check'
        ) as mock_hook, patch.object(
            interceptor, '_get_targets', return_value=[]
        ), patch('meta.services.auth_middleware.is_admin', return_value=False):
            try:
                interceptor.before_action(write_mock_context)
            except Exception:
                pass  # 后续 legacy 逻辑可能因 mock 报错

        mock_hook.assert_not_called()

    def test_flag_on_calls_hook(self, write_mock_context, write_hook_db):
        """flag=True → 调用 _apply_effective_intents_write_check"""
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        interceptor = self._make_interceptor()

        with patch.object(
            interceptor, '_apply_effective_intents_write_check', return_value=True
        ) as mock_hook, patch('meta.services.auth_middleware.is_admin', return_value=False):
            interceptor.before_action(write_mock_context)

        mock_hook.assert_called_once()
        # 第一个参数是 context, 第二个是 user_id
        args, kwargs = mock_hook.call_args
        assert args[0] is write_mock_context or kwargs.get('context') is write_mock_context
        assert args[1] == 999 or kwargs.get('user_id') == 999

    def test_hook_returns_true_skips_legacy(self, write_mock_context, write_hook_db):
        """hook 返回 True → 跳过 legacy _check_target"""
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        interceptor = self._make_interceptor()

        with patch.object(
            interceptor, '_apply_effective_intents_write_check', return_value=True
        ), patch('meta.services.auth_middleware.is_admin', return_value=False), patch.object(
            interceptor, '_check_target'
        ) as mock_legacy_check, patch.object(
            interceptor, '_validate_fk_scope_policies'
        ) as mock_fk:
            interceptor.before_action(write_mock_context)

        mock_legacy_check.assert_not_called()
        mock_fk.assert_not_called()

    def test_hook_returns_false_falls_back_to_legacy(self, write_mock_context, write_hook_db):
        """hook 返回 False → 回退到 legacy 路径"""
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        interceptor = self._make_interceptor()

        with patch.object(
            interceptor, '_apply_effective_intents_write_check', return_value=False
        ), patch('meta.services.auth_middleware.is_admin', return_value=False), patch.object(
            interceptor, '_get_targets', return_value=[]
        ) as mock_targets, patch.object(
            interceptor, '_validate_fk_scope_policies'
        ) as mock_fk:
            interceptor.before_action(write_mock_context)

        # 回退到 legacy: 应调用 _get_targets (legacy 流程的入口)
        mock_targets.assert_called()
        mock_fk.assert_called_once_with(write_mock_context, 999)

    def test_hook_exception_falls_back_safely(self, write_mock_context, write_hook_db):
        """hook 抛非 WriteScopeDenied 异常 → 安全回退到 legacy"""
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        interceptor = self._make_interceptor()

        with patch.object(
            interceptor, '_apply_effective_intents_write_check',
            side_effect=RuntimeError('adapter boom')
        ), patch('meta.services.auth_middleware.is_admin', return_value=False), patch.object(
            interceptor, '_get_targets', return_value=[]
        ), patch.object(
            interceptor, '_validate_fk_scope_policies'
        ) as mock_fk:
            # 不应抛 RuntimeError
            interceptor.before_action(write_mock_context)

        # 异常后回退到 legacy
        mock_fk.assert_called_once_with(write_mock_context, 999)

    def test_admin_skips_hook(self, write_mock_context, write_hook_db):
        """admin 用户跳过 hook"""
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        interceptor = self._make_interceptor()

        with patch.object(
            interceptor, '_apply_effective_intents_write_check'
        ) as mock_hook, patch('meta.services.auth_middleware.is_admin', return_value=True):
            interceptor.before_action(write_mock_context)

        mock_hook.assert_not_called()

    def test_no_user_info_skips_hook(self, write_mock_context, write_hook_db):
        """无 user_info → 直接 return, 不调用 hook"""
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        # 清空 user_info
        write_mock_context.user_info = None

        interceptor = self._make_interceptor()

        with patch.object(
            interceptor, '_apply_effective_intents_write_check'
        ) as mock_hook, patch('meta.services.auth_middleware.is_admin', return_value=False):
            interceptor.before_action(write_mock_context)

        mock_hook.assert_not_called()

    def test_wildcard_permission_skips_hook(self, write_mock_context, write_hook_db):
        """permissions 含 '*' → 跳过 hook (superadmin)"""
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        # 模拟 superadmin
        write_mock_context.user_info = {
            'user_id': 999, 'id': 999, 'permissions': ['*']
        }

        interceptor = self._make_interceptor()

        with patch.object(
            interceptor, '_apply_effective_intents_write_check'
        ) as mock_hook, patch('meta.services.auth_middleware.is_admin', return_value=False):
            interceptor.before_action(write_mock_context)

        mock_hook.assert_not_called()

    def test_hook_allows_when_intent_matches(self, write_mock_context, write_hook_db):
        """hook + Intent 匹配 (owner_id=999 == user_id=999) → 放行"""
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        # product 1 的 owner_id=999, user_id=999 → 匹配 include
        write_mock_context.object_id = 1

        interceptor = self._make_interceptor()

        with patch('meta.services.auth_middleware.is_admin', return_value=False), patch.object(
            interceptor, '_get_db_path', return_value=write_hook_db
        ), patch.object(
            interceptor, '_validate_fk_scope_policies'
        ) as mock_fk:
            # 不应抛异常
            interceptor.before_action(write_mock_context)

        # hook 放行 → 跳过 legacy FK 校验
        mock_fk.assert_not_called()

    def test_hook_denies_when_intent_not_matches(self, write_mock_context, write_hook_db):
        """hook + Intent 不匹配 (owner_id=888 ≠ user_id=999) → 抛 WriteScopeDenied"""
        from meta.core.permission_flags import set_flag
        from meta.core.interceptors.write_scope_interceptor import WriteScopeDenied

        set_flag('effective_intents_enabled', True)

        # product 2 的 owner_id=888, user_id=999 → 不匹配
        write_mock_context.object_id = 2

        interceptor = self._make_interceptor()

        with patch('meta.services.auth_middleware.is_admin', return_value=False), patch.object(
            interceptor, '_get_db_path', return_value=write_hook_db
        ):
            # 应抛 WriteScopeDenied
            with pytest.raises(WriteScopeDenied) as exc_info:
                interceptor.before_action(write_mock_context)

            # 验证异常信息
            assert exc_info.value.target_id == 2
            assert exc_info.value.user_id == 999

    def test_hook_no_intent_denies(self, write_mock_context, write_hook_db):
        """hook + 无 Intent → 默认拒绝 (抛 WriteScopeDenied)"""
        from meta.core.permission_flags import set_flag
        from meta.core.interceptors.write_scope_interceptor import WriteScopeDenied

        set_flag('effective_intents_enabled', True)

        # 删除所有 Intent
        conn = sqlite3.connect(write_hook_db)
        conn.execute('DELETE FROM role_effective_intents')
        conn.commit()
        conn.close()

        interceptor = self._make_interceptor()

        with patch('meta.services.auth_middleware.is_admin', return_value=False), patch.object(
            interceptor, '_get_db_path', return_value=write_hook_db
        ):
            with pytest.raises(WriteScopeDenied):
                interceptor.before_action(write_mock_context)

    def test_hook_action_name_mapping_create(self, write_mock_context, write_hook_db):
        """action=crud_create → action_name='create'"""
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        # 修改 context 为 create
        write_mock_context.action = 'crud_create'
        write_mock_context.object_id = None
        # _get_targets 对 product create 返回 [] (顶层 BO), 所以 hook 应回退
        # 改为 version create (有 parent)
        write_mock_context.object_type = 'version'
        write_mock_context.params = {'product_id': 1}

        interceptor = self._make_interceptor()

        # mock adapter.check_record_allowed 验证 action_name 参数
        with patch('meta.services.auth_middleware.is_admin', return_value=False), patch.object(
            interceptor, '_get_db_path', return_value=write_hook_db
        ), patch(
            'meta.core.intent_scope_adapter.IntentScopeAdapter.check_record_allowed'
        ) as mock_check:
            mock_check.return_value = {'allowed': True, 'source': 'include', 'reason': 'ok'}
            interceptor.before_action(write_mock_context)

            # 验证 action_name 参数为 'create'
            args, kwargs = mock_check.call_args
            assert kwargs.get('action_name') == 'create' or 'create' in args

    def test_hook_action_name_mapping_delete(self, write_mock_context, write_hook_db):
        """action=crud_delete → action_name='delete'"""
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        write_mock_context.action = 'crud_delete'
        write_mock_context.object_id = 1

        interceptor = self._make_interceptor()

        with patch('meta.services.auth_middleware.is_admin', return_value=False), patch.object(
            interceptor, '_get_db_path', return_value=write_hook_db
        ), patch(
            'meta.core.intent_scope_adapter.IntentScopeAdapter.check_record_allowed'
        ) as mock_check:
            mock_check.return_value = {'allowed': True, 'source': 'include', 'reason': 'ok'}
            interceptor.before_action(write_mock_context)

            args, kwargs = mock_check.call_args
            assert kwargs.get('action_name') == 'delete' or 'delete' in args

    def test_hook_multiple_targets_all_must_pass(self, write_mock_context, write_hook_db):
        """associate 操作: src + dst 两个 target 都要通过才放行"""
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        # associate: src_id=1, tgt_id=3 (两个都是 user 999 owner)
        write_mock_context.action = 'associate'
        write_mock_context.object_type = 'relationship'
        write_mock_context.params = {'src_id': 1, 'tgt_id': 3}

        # 补充 Intent: relationship update
        conn = sqlite3.connect(write_hook_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope, source) "
            "VALUES (100, 'relationship', 'update', '{}', 'derived')"
        )
        conn.commit()
        conn.close()

        interceptor = self._make_interceptor()

        with patch('meta.services.auth_middleware.is_admin', return_value=False), patch.object(
            interceptor, '_get_db_path', return_value=write_hook_db
        ), patch.object(
            interceptor, '_validate_fk_scope_policies'
        ) as mock_fk:
            # 不应抛异常 (两个 target 都通过)
            interceptor.before_action(write_mock_context)

        mock_fk.assert_not_called()  # hook 放行 → 跳过 legacy

    def test_hook_any_target_denies_raises(self, write_mock_context, write_hook_db):
        """associate: src 通过但 dst 拒绝 → 整体抛 WriteScopeDenied"""
        from meta.core.permission_flags import set_flag
        from meta.core.interceptors.write_scope_interceptor import WriteScopeDenied

        set_flag('effective_intents_enabled', True)

        # src=1 (owner=999 通过), dst=2 (owner=888 拒绝)
        write_mock_context.action = 'associate'
        write_mock_context.object_type = 'relationship'
        write_mock_context.params = {'src_id': 1, 'tgt_id': 2}

        # relationship 的 Intent: owner_id=${user.id}
        conn = sqlite3.connect(write_hook_db)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope, source) "
            "VALUES (100, 'relationship', 'update', "
            "'{\"include\":[{\"field\":\"owner_id\",\"op\":\"=\",\"value\":\"${user.id}\"}],\"exclude\":[]}', "
            "'derived')"
        )
        conn.commit()
        conn.close()

        interceptor = self._make_interceptor()

        with patch('meta.services.auth_middleware.is_admin', return_value=False), patch.object(
            interceptor, '_get_db_path', return_value=write_hook_db
        ):
            with pytest.raises(WriteScopeDenied):
                interceptor.before_action(write_mock_context)

    def test_hook_empty_include_allows_all(self, write_mock_context, write_hook_db):
        """空 include = 全部允许"""
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        # 修改 Intent: 空 include (允许所有)
        conn = sqlite3.connect(write_hook_db)
        conn.execute(
            "UPDATE role_effective_intents SET data_scope = "
            "'{\"include\":[],\"exclude\":[]}' "
            "WHERE role_id = 100 AND bo_id = 'product' AND action_name = 'update'"
        )
        conn.commit()
        conn.close()

        # product 2 (owner=888) 也应允许 (空 include)
        write_mock_context.object_id = 2

        interceptor = self._make_interceptor()

        with patch('meta.services.auth_middleware.is_admin', return_value=False), patch.object(
            interceptor, '_get_db_path', return_value=write_hook_db
        ), patch.object(
            interceptor, '_validate_fk_scope_policies'
        ) as mock_fk:
            interceptor.before_action(write_mock_context)

        mock_fk.assert_not_called()  # hook 放行

    def test_hook_exclude_denies(self, write_mock_context, write_hook_db):
        """exclude 命中 → 拒绝"""
        from meta.core.permission_flags import set_flag
        from meta.core.interceptors.write_scope_interceptor import WriteScopeDenied

        set_flag('effective_intents_enabled', True)

        # 修改 Intent: 空 include + exclude owner_id=999
        conn = sqlite3.connect(write_hook_db)
        conn.execute(
            "UPDATE role_effective_intents SET data_scope = "
            "'{\"include\":[],\"exclude\":[{\"field\":\"owner_id\",\"op\":\"=\",\"value\":999}]}' "
            "WHERE role_id = 100 AND bo_id = 'product' AND action_name = 'update'"
        )
        conn.commit()
        conn.close()

        # product 1 (owner=999) → exclude 命中 → 拒绝
        write_mock_context.object_id = 1

        interceptor = self._make_interceptor()

        with patch('meta.services.auth_middleware.is_admin', return_value=False), patch.object(
            interceptor, '_get_db_path', return_value=write_hook_db
        ):
            with pytest.raises(WriteScopeDenied):
                interceptor.before_action(write_mock_context)
