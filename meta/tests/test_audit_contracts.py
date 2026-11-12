# -*- coding: utf-8 -*-
"""审计链路契约测试（批量审计上下文 / 拦截器白名单）。

[TEST-EFF P2-1] 由两个同域（audit 纯 mock、0 DB 副作用）的 <=5 用例小文件合并：
- test_batch_audit_context.py      (FR-LOG-007 BatchAuditContext)
- test_audit_interceptor_whitelist.py (TC-AUDIT-005 白名单完整性)
原文件均无 marker，合并后保持无 module 级 marker，不改变 `-m` 选择口径。
"""

import ast
import logging
import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---------------------------------------------------------------------------
# test_batch_audit_context.py — FR-LOG-007: 1 header + N details
# ---------------------------------------------------------------------------
class TestBatchAuditContext:
    """FR-LOG-007: 1 header + N details (Stripe batch events 模式)"""

    def test_creates_header_on_enter(self):
        from meta.services.audit_service import BatchAuditContext, AuditRecord

        class MockAudit:
            def __init__(self):
                self.created = []
            def create(self, rec):
                rec.id = len(self.created) + 1
                self.created.append(rec)
                return rec.id
            def update(self, id, **kwargs):
                for r in self.created:
                    if r.id == id:
                        for k, v in kwargs.items():
                            setattr(r, k, v)
                        return True
                return False

        audit = MockAudit()
        with BatchAuditContext(
            action='batch_create_users',
            object_type='user',
            audit_service=audit,
            user_context={'user_id': 1, 'user_name': 'alice'},
        ) as batch:
            assert batch.header_id is not None
            assert len(audit.created) == 1  # header

        # header 应是 static + batch 标记
        header = audit.created[0]
        assert header.action_kind == 'static'
        assert header.object_id == 'batch'
        assert header.action == 'batch_create_users'
        assert header.outcome == 'success'

    def test_add_detail_creates_with_parent_id(self):
        from meta.services.audit_service import BatchAuditContext

        class MockAudit:
            def __init__(self):
                self.created = []
            def create(self, rec):
                rec.id = len(self.created) + 1
                self.created.append(rec)
                return rec.id
            def update(self, *args, **kwargs):
                return False

        audit = MockAudit()
        with BatchAuditContext(
            action='batch_create_users',
            object_type='user',
            audit_service=audit,
            user_context={'user_id': 1},
        ) as batch:
            batch.add_detail(object_id=101, outcome='success')
            batch.add_detail(object_id=102, outcome='success')
            batch.add_detail(object_id=103, outcome='failure', error_msg='duplicate')

        assert len(audit.created) == 1 + 3  # 1 header + 3 details

        # 验证 detail 关联
        details = audit.created[1:]
        assert details[0].parent_action_id == batch.header_id
        assert details[0].action_kind == 'instance'
        assert details[0].action == 'create_users'  # batch_ prefix 去掉
        assert details[0].object_id == 101
        assert details[0].outcome == 'success'

        assert details[2].outcome == 'failure'
        assert details[2].error_message == 'duplicate'

    def test_exception_updates_header_outcome(self):
        """batch 整体失败 → header outcome 改为 failure"""
        from meta.services.audit_service import BatchAuditContext

        class MockAudit:
            def __init__(self):
                self.created = []
                self.updates = []
            def create(self, rec):
                rec.id = len(self.created) + 1
                self.created.append(rec)
                return rec.id
            def update(self, id, **kwargs):
                self.updates.append((id, kwargs))
                return True

        audit = MockAudit()
        with pytest.raises(RuntimeError, match="batch_failed"):
            with BatchAuditContext(
                action='batch_create_users',
                object_type='user',
                audit_service=audit,
                user_context={'user_id': 1},
            ) as batch:
                raise RuntimeError("batch_failed")

        # header 被更新为 failure
        assert len(audit.updates) == 1
        update_id, update_kwargs = audit.updates[0]
        assert update_kwargs['outcome'] == 'failure'
        assert 'batch_failed' in update_kwargs['error_message']

    def test_header_create_failure_does_not_block_main(self):
        """header 创建失败不影响主流程"""
        from meta.services.audit_service import BatchAuditContext

        class FailingAudit:
            def create(self, rec):
                raise RuntimeError("DB down")
            def update(self, *args, **kwargs):
                return False

        audit = FailingAudit()
        # 即使 header 创建失败，with 块也应正常进入
        with BatchAuditContext(
            action='batch_op',
            object_type='user',
            audit_service=audit,
            user_context={'user_id': 1},
        ) as batch:
            # header_id 应为 None（创建失败）
            assert batch.header_id is None
            # add_detail 也应不抛错
            batch.add_detail(object_id=1, outcome='success')
            # batch.details_count 应为 1
            assert batch.details_count == 1

    def test_no_exception_keeps_header_outcome_success(self):
        """无异常时 header 保持 success"""
        from meta.services.audit_service import BatchAuditContext

        class MockAudit:
            def __init__(self):
                self.created = []
                self.updates = []
            def create(self, rec):
                rec.id = len(self.created) + 1
                self.created.append(rec)
                return rec.id
            def update(self, *args, **kwargs):
                self.updates.append((args, kwargs))
                return True

        audit = MockAudit()
        with BatchAuditContext(
            action='batch_op',
            object_type='user',
            audit_service=audit,
            user_context={'user_id': 1},
        ):
            pass

        # 没有异常 → 不调用 update
        assert len(audit.updates) == 0
        assert audit.created[0].outcome == 'success'


# ---------------------------------------------------------------------------
# test_audit_interceptor_whitelist.py — [TC-AUDIT-005]
# ---------------------------------------------------------------------------
# [REGRESSION 2026-06-12] _ASSOC_ACTIONS 白名单漏配 batch_assign/batch_unassign，
# 导致"多选删除用户组成员"路径不写审计日志。本组用例把白名单与新增 action
# 绑定为自动化校验。

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
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        from meta.core.action_context import ActionContext, ActionResult

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
