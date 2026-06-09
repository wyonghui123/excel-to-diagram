import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
运维操作日志拦截器测试

迁移自 unittest.TestCase -> pytest
"""
import pytest
from unittest.mock import MagicMock

from meta.core.interceptors.operation_log_interceptor import OperationLogInterceptor
from meta.core.action_context import ActionContext, ActionResult


@pytest.fixture
def mock_logger():
    """Mock logger fixture"""
    return MagicMock()


@pytest.fixture
def interceptor(mock_logger):
    """OperationLogInterceptor with mock logger.
    
    注意: 原始 DISABLED=True 是因为写入 audit_logs 会产生噪音 (object_type=_unknown 等).
    测试时临时改为 False 以验证逻辑正确性; 生产代码保持 DISABLED=True.
    """
    i = OperationLogInterceptor(structured_logger=mock_logger)
    i.DISABLED = False  # 测试时启用, 验证逻辑
    return i


def make_context(action, object_type='domain', success=True,
                 object_id=1, result_message=None):
    """Helper to create ActionContext"""
    meta_obj = MagicMock()
    meta_obj.id = object_type
    result = ActionResult(
        success=success,
        data={'id': object_id} if success else None,
        message=result_message
    )
    return ActionContext(
        meta_object=meta_obj,
        action=action,
        params={'id': object_id},
        data_source=MagicMock(),
        user_id=1,
        user_name='admin',
        ip_address='192.168.1.1',
        trace_id='ops-trace',
        result=result,
    )


class TestOperationLogInterceptor:

    def test_priority(self, interceptor):
        assert interceptor.priority == 97

    def test_before_action_does_not_raise(self, interceptor):
        ctx = make_context('crud_create')
        interceptor.before_action(ctx)

    def test_create_action_logs_operation(self, interceptor, mock_logger):
        ctx = make_context('crud_create')
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'CREATE_OBJECT'
        assert kwargs['level'] == 'INFO'

    def test_update_action_logs_operation(self, interceptor, mock_logger):
        ctx = make_context('crud_update')
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'UPDATE_OBJECT'

    def test_delete_action_logs_operation(self, interceptor, mock_logger):
        ctx = make_context('crud_delete')
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'DELETE_OBJECT'

    def test_read_action_logs_operation(self, interceptor, mock_logger):
        ctx = make_context('crud_read')
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'READ_OBJECT'

    def test_associate_action_logs_operation(self, interceptor, mock_logger):
        ctx = make_context('associate')
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'ASSOCIATE_OBJECT'

    def test_dissociate_action_logs_operation(self, interceptor, mock_logger):
        ctx = make_context('dissociate')
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['operation'] == 'DISSOCIATE_OBJECT'

    def test_failed_action_logs_error(self, interceptor, mock_logger):
        ctx = make_context('crud_create', success=False, result_message='Database error')
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['level'] == 'ERROR'
        assert kwargs['error'] == 'Database error'

    def test_failed_action_default_error_message(self, interceptor, mock_logger):
        ctx = make_context('crud_create', success=False, result_message=None)
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['level'] == 'ERROR'
        assert kwargs['error'] == 'Operation failed'

    def test_unknown_action_skipped(self, interceptor, mock_logger):
        ctx = make_context('unknown_action')
        interceptor.after_action(ctx)
        mock_logger.log_operation.assert_not_called()

    def test_object_type_in_message(self, interceptor, mock_logger):
        ctx = make_context('crud_create', object_type='business_object')
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert 'business_object' in kwargs['message']

    def test_object_id_in_message(self, interceptor, mock_logger):
        ctx = make_context('crud_create', object_id=42)
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert '#42' in kwargs['message']

    def test_no_object_id_in_message(self, interceptor, mock_logger):
        ctx = make_context('crud_create', object_id=None)
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert '#' not in kwargs['message']

    def test_trace_id_passed(self, interceptor, mock_logger):
        ctx = make_context('crud_create')
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['trace_id'] == 'ops-trace'

    def test_user_info_passed(self, interceptor, mock_logger):
        ctx = make_context('crud_create')
        interceptor.after_action(ctx)
        kwargs = mock_logger.log_operation.call_args[1]
        assert kwargs['user_id'] == 1
        assert kwargs['user_name'] == 'admin'
        assert kwargs['ip_address'] == '192.168.1.1'

    def test_default_logger_created_when_none(self):
        interceptor = OperationLogInterceptor(structured_logger=None)
        assert interceptor._structured_logger is not None
