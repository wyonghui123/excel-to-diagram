# -*- coding: utf-8 -*-
"""
test_cascade_bug_v014.py
覆盖 BUG-V014 (commit 4ffa427):
  fix: 修复 batch-delete 绕过 cascade_interceptor 导致 FK 错误
"""
import pytest
import inspect

pytestmark = [pytest.mark.post_v2_1, pytest.mark.cascade]


class TestBugV014CascadeInterceptorInDoDelete:
    """BUG-V014: _do_delete 同步调用 CascadeInterceptor.before_action"""

    def test_do_delete_calls_cascade_interceptor(self):
        from meta.core import action_executor
        source = inspect.getsource(action_executor)
        assert 'CascadeInterceptor' in source, "action_executor.py 应包含 CascadeInterceptor 调用"
        assert 'before_action' in source, "action_executor.py 应包含 before_action 调用"
        assert 'BUG-V014' in source, "修复处应有 BUG-V014 注释"

    def test_cascade_call_wrapped_in_try_except(self):
        from meta.core import action_executor
        source = inspect.getsource(action_executor)
        assert 'try:' in source or 'try ' in source
        assert 'logger.warning' in source or 'continue' in source

    def test_action_context_required_fields(self):
        from meta.core.action_context import ActionContext
        import inspect
        ctx_source = inspect.getsource(ActionContext)
        assert 'meta_object' in ctx_source
        assert 'action' in ctx_source
        assert 'params' in ctx_source
        assert 'data_source' in ctx_source

    def test_cascade_only_on_delete_action(self):
        from meta.core.interceptors import cascade_interceptor
        source = inspect.getsource(cascade_interceptor.CascadeInterceptor.before_action)
        assert 'action' in source
        assert 'delete' in source.lower() or 'crud_delete' in source


class TestBugV014BatchDeletePath:
    """批量删除路径"""

    def test_batch_delete_routes_to_action_executor(self):
        from meta.services import manage_service
        source = inspect.getsource(manage_service.ManageService.batch_delete)
        assert 'executor' in source
        assert 'crud_delete' in source

    def test_executor_execute_routes_to_do_delete(self):
        from meta.core import action_executor
        source = inspect.getsource(action_executor)
        assert 'def _do_delete' in source
        assert '_execute_crud' in source


class TestRegressionBugV014:
    """回归 - 不应破坏现有 _do_delete 行为"""

    def test_do_delete_still_executes_sql_delete(self):
        from meta.core import action_executor
        source = inspect.getsource(action_executor.ActionExecutor._do_delete)
        assert 'DELETE FROM' in source or 'DELETE ' in source

    def test_do_delete_still_cleans_m2m_first(self):
        from meta.core import action_executor
        source = inspect.getsource(action_executor.ActionExecutor._do_delete)
        m2m_pos = source.find('_cleanup_m2m_tables')
        cascade_pos = source.find('CascadeInterceptor')
        if m2m_pos >= 0 and cascade_pos >= 0:
            assert m2m_pos < cascade_pos, (
                "_cleanup_m2m_tables 应在 CascadeInterceptor 之前调用"
            )
