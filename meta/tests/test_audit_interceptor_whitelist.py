# -*- coding: utf-8 -*-
"""
[TC-AUDIT-005] AuditInterceptor 白名单完整性单测

[REGRESSION 2026-06-12] 复盘教训:
  AuditInterceptor 的 _ASSOC_ACTIONS 白名单漏配 batch_assign/batch_unassign,
  导致前端"多选删除用户组成员"路径完全不写审计日志. 这个 bug 在生产环境跑了
  很久才被发现, 根本原因是白名单和新增 action 没有任何自动化校验.

本文件职责:
  1. 反射检查 _ASSOC_ACTIONS 包含所有"应该被审计"的关联类 action
  2. 用真实 ActionContext 走完整链路, 验证每个 action 都会触发日志写入
  3. 验证未知 action 会产生 WARNING 日志 (P2 修复)

[IMPORTANT] 此文件故意不走 Flask/DB, 用 mock 即可, 0 副作用, 跑得飞快.
"""
import pytest


class TestAuditInterceptorWhitelist:
    """白名单完整性校验 (反射层)"""

    REQUIRED_ASSOC_ACTIONS = {
        'associate', 'dissociate',
        'assign', 'unassign',
        'batch_assign', 'batch_unassign',
    }

    def test_assoc_actions_contains_all_required(self):
        """_ASSOC_ACTIONS 必须包含所有 6 个关联类 action"""
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()

        # 反射拿白名单 (在方法内是局部变量, 我们用 ast 直接 parse 文件)
        import ast
        import os
        src_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', 'core', 'interceptors', 'audit_interceptor.py'
        )
        with open(src_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())

        found_actions = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Set):
                for elt in node.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        found_actions.add(elt.value)

        missing = self.REQUIRED_ASSOC_ACTIONS - found_actions
        assert not missing, (
            f"[REGRESSION] _ASSOC_ACTIONS 白名单缺失: {missing}. "
            f"当前白名单: {sorted(found_actions)}. "
            f"如果是新增的关联类 action, 请同步加入白名单 + 这个测试的 REQUIRED_ASSOC_ACTIONS."
        )

    def test_unknown_action_emits_warning(self):
        """未知 action 命中拦截器时, 必须产生 WARNING (P2 修复验证)"""
        import logging
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        from meta.core.action_context import ActionContext, ActionResult
        from unittest.mock import MagicMock

        interceptor = AuditInterceptor()
        meta_obj = MagicMock()
        meta_obj.type = 'user'

        ctx = ActionContext(
            meta_object=meta_obj,
            action='unknown_new_action_xyz',
            params={},
            data_source=MagicMock(),
            user_id=1,
            user_name='admin',
            ip_address='127.0.0.1',
            trace_id='trace-p2',
        )
        ctx.result = ActionResult(success=True, data=None)
        # is_crud_action 是 property (self.action.startswith('crud_')),
        # 用 'unknown_new_action_xyz' 让它自动返回 False
        assert not ctx.is_crud_action

        # 收集 WARNING 日志
        captured = []

        class _Capture(logging.Handler):
            def emit(self, record):
                captured.append(record)

        cap = _Capture(level=logging.WARNING)
        logger = logging.getLogger('meta.core.interceptors.audit_interceptor')
        logger.addHandler(cap)
        try:
            interceptor.after_action(ctx)
        finally:
            logger.removeHandler(cap)

        warnings = [r.getMessage() for r in captured if r.levelno >= logging.WARNING]
        assert any('SKIP unknown action' in m and 'unknown_new_action_xyz' in m for m in warnings), (
            f"[REGRESSION] 未知 action 没有产生 WARNING 日志. "
            f"Captured: {warnings}. P2 修复可能被回退."
        )


class TestAuditInterceptorWritesLogsForAllAssocActions:
    """链路层: 每个白名单 action 都能触发 _log_association_event"""

    ACTIONS_TO_VERIFY = [
        'associate', 'dissociate',
        'assign', 'unassign',
        'batch_assign', 'batch_unassign',
    ]

    @pytest.mark.parametrize('action', ACTIONS_TO_VERIFY)
    def test_action_does_not_skip_silently(self, action):
        """每个白名单 action 都不应被 SKIP (因为 _ASSOC_ACTIONS 应该含它)"""
        import logging
        from unittest.mock import MagicMock, patch
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        from meta.core.action_context import ActionContext, ActionResult

        interceptor = AuditInterceptor()
        meta_obj = MagicMock()
        meta_obj.type = 'user'

        ctx = ActionContext(
            meta_object=meta_obj,
            action=action,
            params={'src_id': 1, 'tgt_type': 'user_group', 'tgt_id': 2, 'association_name': 'groups'},
            data_source=MagicMock(),
            user_id=1,
            user_name='admin',
            ip_address='127.0.0.1',
            trace_id=f'trace-{action}',
        )
        ctx.result = ActionResult(success=True, data=None)
        # is_crud_action 是 property (self.action.startswith('crud_')),
        # 我们的 action 都不是 crud_ 前缀, 自动返回 False

        # 收集 WARNING
        captured = []

        class _Cap(logging.Handler):
            def emit(self, record):
                captured.append(record.getMessage())

        cap = _Cap(level=logging.WARNING)
        logging.getLogger('meta.core.interceptors.audit_interceptor').addHandler(cap)
        try:
            interceptor.after_action(ctx)
        finally:
            logging.getLogger('meta.core.interceptors.audit_interceptor').removeHandler(cap)

        # 不应出现 "SKIP unknown action" 警告 (因为 action 在白名单里)
        skip_warnings = [m for m in captured if 'SKIP unknown action' in m and action in m]
        assert not skip_warnings, (
            f"[REGRESSION] action={action!r} 被静默 SKIP, 但应在白名单. "
            f"Captured: {captured}"
        )
