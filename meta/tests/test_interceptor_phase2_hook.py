# -*- coding: utf-8 -*-
"""
Phase 2 P2.6 — Interceptor Feature Flag Hook 集成测试

[覆盖范围]
  1. effective_intents_enabled=False (默认) → 走原逻辑 (零影响)
  2. effective_intents_enabled=True → 走 IntentScopeAdapter
  3. flag on + 无 Intent → 注入 1=0 (默认拒绝)
  4. flag on + 有 Intent → 注入 cond_expr
  5. flag on + 异常 → 回退到原逻辑 (防御性)
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
def hook_db():
    """创建测试 DB"""
    tmp_dir = tempfile.mkdtemp(prefix='hook_')
    db_path = os.path.join(tmp_dir, 'test.db')

    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE role_effective_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            permission_set_id INTEGER NOT NULL,
            bo_id VARCHAR(100) NOT NULL,
            action_name VARCHAR(100) NOT NULL,
            data_scope TEXT,
            derivation_mode VARCHAR(20) DEFAULT 'static',
            source VARCHAR(50) DEFAULT 'derived',
            is_stale INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (permission_set_id, bo_id, action_name)
        );

        CREATE TABLE group_roles (
            group_id INTEGER, permission_set_id INTEGER
        );
        CREATE TABLE user_group_members (
            user_id INTEGER, group_id INTEGER
        );

        INSERT INTO group_roles VALUES (1, 100);
        INSERT INTO user_group_members VALUES (999, 1);

        INSERT INTO role_effective_intents
            (permission_set_id, bo_id, action_name, data_scope, source)
        VALUES
            (100, 'product', 'read',
             '{"include":[{"field":"owner_id","op":"=","value":"${user.id}"}],"exclude":[]}',
             'derived');
    ''')
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def mock_context(hook_db):
    """构造 mock ActionContext"""
    ctx = MagicMock()
    ctx.user_id = 999
    ctx.object_type = 'product'
    ctx.is_query_action = True
    ctx.extra = {}

    # mock data_source
    ds = MagicMock()
    ds.db_path = hook_db

    def execute(sql, params=None):
        conn = sqlite3.connect(hook_db)
        cursor = conn.execute(sql, params or [])
        rows = cursor.fetchall()
        conn.close()
        # 返回 mock cursor
        m = MagicMock()
        m.fetchall.return_value = rows
        m.fetchone.return_value = rows[0] if rows else None
        return m

    ds.execute.side_effect = execute
    ctx.data_source = ds
    return ctx


class TestInterceptorFeatureFlagHook:
    """Interceptor Feature flag hook 测试"""

    @pytest.fixture(autouse=True)
    def reset_flag(self):
        """每个测试前后重置 flag"""
        from meta.core.permission_flags import set_flag, reset_flags
        reset_flags()
        yield
        reset_flags()

    def test_flag_off_uses_legacy_path(self, mock_context, hook_db):
        """flag=False → 不调用 IntentScopeAdapter"""
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        from meta.core.permission_flags import set_flag

        # 确保 flag 关闭
        set_flag('effective_intents_enabled', False)

        interceptor = DataPermissionInterceptor()

        with patch.object(
            interceptor, '_apply_effective_intents_filter'
        ) as mock_hook, patch.object(
            interceptor, '_apply_dimension_scope_filter', return_value=False
        ) as mock_legacy:
            # 模拟 _is_admin 返回 False
            with patch.object(interceptor, '_is_admin', return_value=False):
                try:
                    interceptor.before_action(mock_context)
                except Exception:
                    pass  # 后续逻辑可能因 mock 报错, 但不影响验证

        # flag 关闭时, hook 不应被调用
        mock_hook.assert_not_called()

    def test_flag_on_calls_hook(self, mock_context, hook_db):
        """flag=True → 调用 _apply_effective_intents_filter"""
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        interceptor = DataPermissionInterceptor()

        with patch.object(
            interceptor, '_apply_effective_intents_filter', return_value=True
        ) as mock_hook, patch.object(interceptor, '_is_admin', return_value=False):
            interceptor.before_action(mock_context)

        mock_hook.assert_called_once_with(mock_context)

    def test_hook_returns_true_skips_legacy(self, mock_context, hook_db):
        """hook 返回 True → 跳过 legacy 路径"""
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        interceptor = DataPermissionInterceptor()

        with patch.object(
            interceptor, '_apply_effective_intents_filter', return_value=True
        ), patch.object(interceptor, '_is_admin', return_value=False), patch.object(
            interceptor, '_apply_dimension_scope_filter'
        ) as mock_legacy:
            interceptor.before_action(mock_context)

        mock_legacy.assert_not_called()

    def test_hook_returns_false_falls_back_to_legacy(self, mock_context, hook_db):
        """hook 返回 False → 回退到 legacy 路径"""
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        interceptor = DataPermissionInterceptor()

        with patch.object(
            interceptor, '_apply_effective_intents_filter', return_value=False
        ), patch.object(interceptor, '_is_admin', return_value=False), patch.object(
            interceptor, '_apply_dimension_scope_filter', return_value=False
        ) as mock_legacy, patch.object(interceptor, '_apply_scope_filter'), patch.object(
            interceptor, '_apply_data_permission_filter'
        ):
            interceptor.before_action(mock_context)

        mock_legacy.assert_called_once_with(mock_context)

    def test_hook_with_intent_injects_condition(self, mock_context, hook_db):
        """hook + 有 Intent → 注入 cond_expr 到 query_conditions"""
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        interceptor = DataPermissionInterceptor()

        with patch.object(interceptor, '_is_admin', return_value=False), patch.object(
            interceptor, '_get_db_path', return_value=hook_db
        ):
            interceptor.before_action(mock_context)

        # 验证 query_conditions 被注入
        assert 'query_conditions' in mock_context.extra
        qcs = mock_context.extra['query_conditions']
        assert len(qcs) >= 1
        # 应该有 raw 类型条件
        raw_qcs = [q for q in qcs if q.get('type') == 'raw']
        assert len(raw_qcs) >= 1
        # cond_expr 应该包含 owner_id (从 Intent data_scope 来的)
        assert 'owner_id' in raw_qcs[0]['expr']

    def test_hook_with_no_intent_injects_default_deny(self, mock_context, hook_db):
        """hook + 无 Intent → 注入 1=0 (默认拒绝)"""
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        from meta.core.permission_flags import set_flag

        # 删除所有 Intent
        conn = sqlite3.connect(hook_db)
        conn.execute('DELETE FROM role_effective_intents')
        conn.commit()
        conn.close()

        set_flag('effective_intents_enabled', True)

        interceptor = DataPermissionInterceptor()

        with patch.object(interceptor, '_is_admin', return_value=False), patch.object(
            interceptor, '_get_db_path', return_value=hook_db
        ):
            interceptor.before_action(mock_context)

        # 验证 1=0 被注入
        assert 'query_conditions' in mock_context.extra
        qcs = mock_context.extra['query_conditions']
        raw_qcs = [q for q in qcs if q.get('type') == 'raw']
        assert any('1=0' in q['expr'] for q in raw_qcs)

    def test_hook_exception_falls_back_safely(self, mock_context, hook_db):
        """hook 抛异常 → 安全回退到 legacy 路径"""
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        interceptor = DataPermissionInterceptor()

        with patch.object(interceptor, '_is_admin', return_value=False), patch.object(
            interceptor, '_apply_effective_intents_filter',
            side_effect=Exception('test error')
        ), patch.object(
            interceptor, '_apply_dimension_scope_filter', return_value=False
        ) as mock_legacy, patch.object(interceptor, '_apply_scope_filter'), patch.object(
            interceptor, '_apply_data_permission_filter'
        ):
            # 不应抛异常
            interceptor.before_action(mock_context)

        # 异常后回退到 legacy
        mock_legacy.assert_called_once_with(mock_context)

    def test_admin_skips_hook(self, mock_context, hook_db):
        """admin 用户跳过 hook"""
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        from meta.core.permission_flags import set_flag

        set_flag('effective_intents_enabled', True)

        interceptor = DataPermissionInterceptor()

        with patch.object(interceptor, '_is_admin', return_value=True), patch.object(
            interceptor, '_apply_effective_intents_filter'
        ) as mock_hook:
            interceptor.before_action(mock_context)

        mock_hook.assert_not_called()
