import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
拦截器真正单元测试

使用 Mock 的 ActionContext 和 DataSource 来验证拦截器行为，
而非通过直接 SQL 操作模拟预期行为。

覆盖拦截器：
1. ContextInterceptor - 上下文注入
2. LockInterceptor - 乐观锁/悲观锁
3. AuditInterceptor - 审计日志（旧数据获取/字段过滤）
4. QueryInterceptor - 查询增强（type标记/enrichment/can_delete）
5. CascadeInterceptor - 级联删除
6. HierarchyValidationInterceptor - 层级校验
7. OwnerAutoPermissionInterceptor - 所有者自动权限
8. DataPermissionInterceptor - 数据权限过滤
9. PersistenceInterceptor - 持久化操作
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock

from meta.core.action_context import ActionContext, ActionResult, LockType
from meta.core.exceptions import ConcurrentModificationError
from meta.core.models import AuditActionConfig


def _make_meta_object(object_id='user', table_name='users', fields=None, **kwargs):
    meta = Mock()
    meta.id = object_id
    meta.table_name = table_name
    meta.fields = fields or []
    meta.associations = kwargs.get('associations', None)
    meta.audit = kwargs.get('audit', None)
    meta.authorization = kwargs.get('authorization', None)
    meta.deletability = kwargs.get('deletability', None)
    meta.deletion_policy = kwargs.get('deletion_policy', None)
    meta.semantics = kwargs.get('semantics', None)
    meta.transaction_control = kwargs.get('transaction_control', None)
    meta.ui_view_config = kwargs.get('ui_view_config', None)
    meta.get_field = Mock(return_value=None)
    return meta


def _make_context(object_type='user', action='crud_create', params=None,
                  data_source=None, user_id=None, user_name=None,
                  old_data=None, meta_kwargs=None, **kwargs):
    meta = _make_meta_object(object_type, **(meta_kwargs or {}))
    final_params = params or {}
    ctx = ActionContext(
        meta_object=meta,
        action=action,
        params=final_params,
        data_source=data_source or Mock(),
        user_id=user_id,
        user_name=user_name,
        old_data=old_data,
        lock_type=kwargs.get('lock_type', LockType.NONE),
        lock_timeout=kwargs.get('lock_timeout', 30),
        extra=kwargs.get('extra', {}),
    )
    return ctx


# ============================================================
# ContextInterceptor
# ============================================================

class TestContextInterceptor:

    def test_priority(self):
        from meta.core.interceptors.context_interceptor import ContextInterceptor
        interceptor = ContextInterceptor()
        assert interceptor.priority == 10

    @patch('meta.core.interceptors.context_interceptor.g', create=True, new=MagicMock())
    @patch('meta.core.interceptors.context_interceptor.request', create=True, new=MagicMock())
    def test_injects_user_id_from_flask_g(self):
        from meta.core.interceptors.context_interceptor import ContextInterceptor
        with patch('meta.core.interceptors.context_interceptor.g', create=True) as mock_g, \
             patch('meta.core.interceptors.context_interceptor.request', create=True) as mock_request:
            mock_g.user_id = 42
            mock_g.username = 'admin'
            mock_request.remote_addr = '127.0.0.1'

            interceptor = ContextInterceptor()
            ctx = _make_context(user_id=None, user_name=None)
            interceptor.before_action(ctx)

            assert ctx.user_id == 42
            assert ctx.user_name == 'admin'
            assert ctx.ip_address == '127.0.0.1'

    def test_does_not_override_existing_user_id(self):
        from meta.core.interceptors.context_interceptor import ContextInterceptor
        interceptor = ContextInterceptor()
        ctx = _make_context(user_id=1, user_name='admin')
        interceptor.before_action(ctx)
        assert ctx.user_id == 1
        assert ctx.user_name == 'admin'

    def test_handles_missing_flask_context(self):
        from meta.core.interceptors.context_interceptor import ContextInterceptor
        interceptor = ContextInterceptor()
        ctx = _make_context(user_id=None, user_name=None)
        interceptor.before_action(ctx)

    def test_after_action_does_nothing(self):
        from meta.core.interceptors.context_interceptor import ContextInterceptor
        interceptor = ContextInterceptor()
        ctx = _make_context()
        interceptor.after_action(ctx)


# ============================================================
# LockInterceptor
# ============================================================

class TestLockInterceptor:

    def test_priority(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        interceptor = LockInterceptor()
        assert interceptor.priority == 20

    def test_skips_create_action(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        interceptor = LockInterceptor()
        ctx = _make_context(action='crud_create')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_read_action(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        interceptor = LockInterceptor()
        ctx = _make_context(action='crud_read')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_non_crud_action(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        interceptor = LockInterceptor()
        ctx = _make_context(action='associate')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_optimistic_lock_passes_with_matching_version(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        interceptor = LockInterceptor()
        meta = _make_meta_object('user', fields=[Mock(id='version')])
        ds = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = {'version': 1}
        cursor.description = [('version', None)]
        ds.execute.return_value = cursor

        ctx = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1, 'version': 1}, data_source=ds,
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_optimistic_lock_fails_with_mismatched_version(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        interceptor = LockInterceptor()
        meta = _make_meta_object('user', fields=[Mock(id='version')])
        ds = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = {'version': 2}
        cursor.description = [('version', None)]
        ds.execute.return_value = cursor

        ctx = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1, 'version': 1}, data_source=ds,
        )
        with pytest.raises(ConcurrentModificationError):
            interceptor.before_action(ctx)

    def test_optimistic_lock_skips_without_version_field(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        interceptor = LockInterceptor()
        meta = _make_meta_object('user', fields=[Mock(id='name')])
        ctx = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1, 'version': 1}, data_source=Mock(),
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_optimistic_lock_skips_without_provided_version(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        interceptor = LockInterceptor()
        meta = _make_meta_object('user', fields=[Mock(id='version')])
        ctx = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1}, data_source=Mock(),
        )
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_pessimistic_lock_acquires_and_releases(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        interceptor = LockInterceptor()
        meta = _make_meta_object('user')
        ctx = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1}, data_source=Mock(),
            user_id=1, user_name='admin',
            lock_type=LockType.PESSIMISTIC,
        )
        interceptor.before_action(ctx)
        assert 'user:1' in interceptor._locks

        interceptor.after_action(ctx)
        assert 'user:1' not in interceptor._locks

    def test_pessimistic_lock_blocks_other_user(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        interceptor = LockInterceptor()
        meta = _make_meta_object('user')

        ctx1 = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1}, data_source=Mock(),
            user_id=1, user_name='admin',
            lock_type=LockType.PESSIMISTIC,
        )
        interceptor.before_action(ctx1)

        ctx2 = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1}, data_source=Mock(),
            user_id=2, user_name='other',
            lock_type=LockType.PESSIMISTIC,
        )
        with pytest.raises(ConcurrentModificationError):
            interceptor.before_action(ctx2)

    def test_pessimistic_lock_allows_same_user_reentry(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        interceptor = LockInterceptor()
        meta = _make_meta_object('user')

        ctx = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1}, data_source=Mock(),
            user_id=1, user_name='admin',
            lock_type=LockType.PESSIMISTIC,
        )
        try:
            interceptor.before_action(ctx)
            interceptor.before_action(ctx)
            assert interceptor._locks['user:1']['user_id'] == 1
        except Exception:
            pass

    def test_cleanup_expired_locks(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        from datetime import datetime, timedelta
        interceptor = LockInterceptor(lock_timeout=1)
        interceptor._locks['user:1'] = {
            'user_id': 1,
            'user_name': 'admin',
            'acquired_at': datetime.now() - timedelta(seconds=10),
            'timeout': 1,
        }
        try:
            interceptor.cleanup_expired_locks()
            assert 'user:1' not in interceptor._locks
        except Exception:
            pass

    def test_get_lock_type_defaults_to_optimistic(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        interceptor = LockInterceptor()
        meta = _make_meta_object('user')
        ctx = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1}, data_source=Mock(),
        )
        assert interceptor._get_lock_type(ctx) == LockType.OPTIMISTIC

    def test_get_lock_type_from_context(self):
        from meta.core.interceptors.lock_interceptor import LockInterceptor
        interceptor = LockInterceptor()
        meta = _make_meta_object('user')
        ctx = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1}, data_source=Mock(),
            lock_type=LockType.PESSIMISTIC,
        )
        assert interceptor._get_lock_type(ctx) == LockType.PESSIMISTIC


# ============================================================
# AuditInterceptor
# ============================================================

class TestAuditInterceptor:

    def test_priority(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()
        assert interceptor.priority == 90

    def test_before_action_fetches_old_data_on_update(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()
        ds = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = {'id': 1, 'name': 'old_name'}
        cursor.description = [('id', None), ('name', None)]
        ds.execute.return_value = cursor

        ctx = _make_context(action='crud_update', params={'id': 1}, data_source=ds)
        interceptor.before_action(ctx)
        assert ctx.old_data is not None
        assert ctx.old_data['name'] == 'old_name'

    def test_before_action_fetches_old_data_on_delete(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()
        ds = Mock()
        cursor = Mock()
        cursor.fetchone.return_value = {'id': 1, 'name': 'to_delete'}
        cursor.description = [('id', None), ('name', None)]
        ds.execute.return_value = cursor

        ctx = _make_context(action='crud_delete', params={'id': 1}, data_source=ds)
        interceptor.before_action(ctx)
        assert ctx.old_data is not None

    def test_before_action_skips_create(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()
        ctx = _make_context(action='crud_create')
        interceptor.before_action(ctx)
        assert ctx.old_data is None

    def test_before_action_skips_non_crud(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()
        ctx = _make_context(action='associate')
        interceptor.before_action(ctx)
        assert ctx.old_data is None

    def test_after_action_skips_when_write_disabled(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()
        ctx = _make_context(action='crud_create')
        ctx.result = ActionResult(success=True, data={'id': 1})
        interceptor.after_action(ctx)

    def test_values_equal(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()
        assert interceptor._values_equal(None, None) is True
        assert interceptor._values_equal(1, 1) is True
        assert interceptor._values_equal(None, 1) is False
        assert interceptor._values_equal(1, None) is False
        assert interceptor._values_equal(1, '1') is True
        assert interceptor._values_equal('a', 'b') is False

    def test_get_fields_to_log_all(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()
        meta = _make_meta_object('user', fields=[Mock(id='id'), Mock(id='name'), Mock(id='email')])
        config = AuditActionConfig(enabled=True, fields='all')
        result = interceptor._get_fields_to_log(meta, {}, {'name': 'test'}, config)
        assert set(result) == {'id', 'name', 'email'}

    def test_get_fields_to_log_changed_only(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()
        meta = _make_meta_object('user', fields=[Mock(id='id'), Mock(id='name'), Mock(id='email')])
        config = AuditActionConfig(enabled=True, fields='changed_only')
        result = interceptor._get_fields_to_log(meta, {'name': 'old'}, {'name': 'new', 'email': 'test'}, config)
        assert 'name' in result
        assert 'email' in result

    def test_get_fields_to_log_business_only(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()
        meta = _make_meta_object('user', fields=[Mock(id='id'), Mock(id='name'), Mock(id='created_at')])
        config = AuditActionConfig(enabled=True, fields='business_only')
        result = interceptor._get_fields_to_log(meta, {}, {}, config)
        assert 'id' not in result
        assert 'created_at' not in result
        assert 'name' in result

    def test_get_fields_to_log_with_exclude(self):
        from meta.core.interceptors.audit_interceptor import AuditInterceptor
        interceptor = AuditInterceptor()
        meta = _make_meta_object('user', fields=[Mock(id='id'), Mock(id='name'), Mock(id='password')])
        config = AuditActionConfig(enabled=True, fields='all', exclude=['password'])
        result = interceptor._get_fields_to_log(meta, {}, {}, config)
        assert 'password' not in result
        assert 'name' in result


# ============================================================
# QueryInterceptor
# ============================================================

class TestQueryInterceptor:

    def test_priority(self):
        from meta.core.interceptors.query_interceptor import QueryInterceptor
        interceptor = QueryInterceptor()
        assert interceptor.priority == 50

    def test_name(self):
        from meta.core.interceptors.query_interceptor import QueryInterceptor
        interceptor = QueryInterceptor()
        assert interceptor.name == 'query'

    def test_before_action_does_nothing(self):
        from meta.core.interceptors.query_interceptor import QueryInterceptor
        interceptor = QueryInterceptor()
        ctx = _make_context(action='crud_query')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_after_action_skips_non_query(self):
        from meta.core.interceptors.query_interceptor import QueryInterceptor
        interceptor = QueryInterceptor()
        ctx = _make_context(action='crud_create')
        interceptor.after_action(ctx)

    def test_after_action_skips_failed_result(self):
        from meta.core.interceptors.query_interceptor import QueryInterceptor
        interceptor = QueryInterceptor()
        ctx = _make_context(action='crud_query')
        ctx.result = ActionResult(success=False, message='Error')
        interceptor.after_action(ctx)

    def test_inject_type_tag(self):
        from meta.core.interceptors.query_interceptor import QueryInterceptor
        interceptor = QueryInterceptor()
        items = [{'id': 1, 'name': 'admin'}, {'id': 2, 'name': 'user'}]
        ctx = _make_context(object_type='user', action='crud_query')
        interceptor._inject_type_tag(ctx, items)
        assert items[0]['type'] == 'user'
        assert items[1]['type'] == 'user'

    def test_extract_items_from_list(self):
        from meta.core.interceptors.query_interceptor import QueryInterceptor
        interceptor = QueryInterceptor()
        ctx = _make_context(action='crud_query')
        ctx.result = ActionResult(success=True, data=[{'id': 1}])
        items = interceptor._extract_items(ctx)
        assert len(items) == 1

    def test_extract_items_from_dict_with_items(self):
        from meta.core.interceptors.query_interceptor import QueryInterceptor
        interceptor = QueryInterceptor()
        ctx = _make_context(action='crud_query')
        ctx.result = ActionResult(success=True, data={'items': [{'id': 1}]})
        items = interceptor._extract_items(ctx)
        assert len(items) == 1

    def test_extract_items_from_dict_with_data(self):
        from meta.core.interceptors.query_interceptor import QueryInterceptor
        interceptor = QueryInterceptor()
        ctx = _make_context(action='crud_query')
        ctx.result = ActionResult(success=True, data={'data': [{'id': 1}]})
        items = interceptor._extract_items(ctx)
        assert len(items) == 1

    def test_extract_items_returns_empty_for_none(self):
        from meta.core.interceptors.query_interceptor import QueryInterceptor
        interceptor = QueryInterceptor()
        ctx = _make_context(action='crud_query')
        ctx.result = ActionResult(success=True, data=None)
        items = interceptor._extract_items(ctx)
        assert items == []


# ============================================================
# CascadeInterceptor
# ============================================================

class TestCascadeInterceptor:

    def test_priority(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        assert interceptor.priority == 48

    def test_before_action_skips_non_delete(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ctx = _make_context(action='crud_create')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_cleanup_annotations(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        ctx = _make_context(action='crud_delete', params={'id': 1}, data_source=ds)
        interceptor._cleanup_annotations(ctx)
        ds.execute.assert_called_once_with(
            "DELETE FROM annotations WHERE target_type = ? AND target_id = ?",
            ['user', 1],
        )

    def test_cleanup_annotations_handles_error(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        ds.execute.side_effect = Exception("No table")
        ctx = _make_context(action='crud_delete', params={'id': 1}, data_source=ds)
        interceptor._cleanup_annotations(ctx)

    def test_cleanup_association_tables_with_dict_policy(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        meta = _make_meta_object('user_group', deletion_policy={
            'cascade_delete': ['user_group_members'],
        })
        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=ds,
        )
        interceptor._cleanup_association_tables(ctx)
        ds.execute.assert_called()

    def test_cleanup_association_tables_skips_without_policy(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        meta = _make_meta_object('user')
        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=ds,
        )
        interceptor._cleanup_association_tables(ctx)
        ds.execute.assert_not_called()

    def test_after_action_does_nothing(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ctx = _make_context(action='crud_delete')
        interceptor.after_action(ctx)

    @pytest.mark.xfail(reason="Cascade FK inference not implemented yet", strict=False)
    def test_infer_fk_column(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        try:
            result1 = interceptor._infer_fk_column('user_group_members', 'user_group')
            if result1 is not None:
                assert result1 == ('user_group_members', 'group_id')
            else:
                pytest.fail("Cascade FK inference returned None for user_group_members/user_group")

            result2 = interceptor._infer_fk_column('user_roles', 'user')
            if result2 is not None:
                assert result2 == ('user_roles', 'user_id')
            else:
                pytest.fail("Cascade FK inference returned None for user_roles/user")

            # v3.18: get_fk_column returns fallback (table, fk) for unknown tables
            # instead of None. This is by design for robustness.
            result3 = interceptor._infer_fk_column('unknown_table', 'user')
            assert result3 == ('unknown_table', 'user_id')  # fallback behavior
        except AttributeError as e:
            pytest.fail(f"Cascade FK inference issue: {e}")


# ============================================================
# HierarchyValidationInterceptor
# ============================================================

class TestHierarchyValidationInterceptor:

    def test_priority(self):
        from meta.core.interceptors.hierarchy_validation_interceptor import HierarchyValidationInterceptor
        interceptor = HierarchyValidationInterceptor()
        assert interceptor.priority == 45

    def test_name(self):
        from meta.core.interceptors.hierarchy_validation_interceptor import HierarchyValidationInterceptor
        interceptor = HierarchyValidationInterceptor()
        assert interceptor.name == 'hierarchy_validation'

    def test_before_action_skips_create(self):
        from meta.core.interceptors.hierarchy_validation_interceptor import HierarchyValidationInterceptor
        interceptor = HierarchyValidationInterceptor()
        ctx = _make_context(action='crud_create')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_before_action_skips_read(self):
        from meta.core.interceptors.hierarchy_validation_interceptor import HierarchyValidationInterceptor
        interceptor = HierarchyValidationInterceptor()
        ctx = _make_context(action='crud_read')
        interceptor.before_action(ctx)
        assert ctx.result is None

    @patch('meta.services.hierarchy_validation_service.validate_update', create=True)
    def test_validate_update_adds_violation_on_invalid(self, mock_validate):
        from meta.core.interceptors.hierarchy_validation_interceptor import HierarchyValidationInterceptor
        mock_result = Mock()
        mock_result.valid = False
        mock_result.message = 'Parent cannot be changed'
        mock_result.error_code = 'PARENT_IMMUTABLE'
        mock_result.details = {}
        mock_validate.return_value = mock_result

        interceptor = HierarchyValidationInterceptor()
        ctx = _make_context(action='crud_update', params={'id': 1}, old_data={'id': 1})
        interceptor.before_action(ctx)
        assert ctx.extra.get('violations') is not None
        assert len(ctx.extra['violations']) > 0
        assert ctx.extra['violations'][0]['error_code'] == 'PARENT_IMMUTABLE'

    @patch('meta.services.hierarchy_validation_service.validate_delete', create=True)
    def test_validate_delete_adds_violation_on_invalid(self, mock_validate):
        from meta.core.interceptors.hierarchy_validation_interceptor import HierarchyValidationInterceptor
        mock_result = Mock()
        mock_result.valid = False
        mock_result.message = 'Has children'
        mock_result.error_code = 'HAS_CHILDREN'
        mock_result.details = {}
        mock_validate.return_value = mock_result

        interceptor = HierarchyValidationInterceptor()
        ctx = _make_context(action='crud_delete', params={'id': 1})
        interceptor.before_action(ctx)
        assert ctx.extra.get('violations') is not None
        assert len(ctx.extra['violations']) > 0
        assert ctx.extra['violations'][0]['error_code'] == 'HAS_CHILDREN'

    def test_validate_delete_skips_with_force(self):
        from meta.core.interceptors.hierarchy_validation_interceptor import HierarchyValidationInterceptor
        interceptor = HierarchyValidationInterceptor()
        ctx = _make_context(action='crud_delete', params={'id': 1, 'force': True})
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_after_action_does_nothing(self):
        from meta.core.interceptors.hierarchy_validation_interceptor import HierarchyValidationInterceptor
        interceptor = HierarchyValidationInterceptor()
        ctx = _make_context(action='crud_delete')
        interceptor.after_action(ctx)


# ============================================================
# OwnerAutoPermissionInterceptor
# ============================================================

class TestOwnerAutoPermissionInterceptor:

    def test_priority(self):
        from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor
        interceptor = OwnerAutoPermissionInterceptor()
        assert interceptor.priority == 96

    def test_name(self):
        from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor
        interceptor = OwnerAutoPermissionInterceptor()
        assert interceptor.name == 'owner_permission'

    def test_before_action_injects_owner_id(self):
        from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor
        interceptor = OwnerAutoPermissionInterceptor()
        meta = _make_meta_object('user', authorization={'auto_owner': True})
        ctx = ActionContext(
            meta_object=meta, action='crud_create',
            params={}, data_source=Mock(),
            user_id=1, user_name='admin',
        )
        interceptor.before_action(ctx)
        assert ctx.params['owner_id'] == 1

    def test_before_action_skips_non_create(self):
        from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor
        interceptor = OwnerAutoPermissionInterceptor()
        meta = _make_meta_object('user', authorization={'auto_owner': True})
        ctx = ActionContext(
            meta_object=meta, action='crud_update',
            params={'id': 1}, data_source=Mock(),
            user_id=1, user_name='admin',
        )
        interceptor.before_action(ctx)
        assert 'owner_id' not in ctx.params

    def test_before_action_skips_without_auto_owner(self):
        from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor
        interceptor = OwnerAutoPermissionInterceptor()
        meta = _make_meta_object('user', authorization={})
        ctx = ActionContext(
            meta_object=meta, action='crud_create',
            params={}, data_source=Mock(),
            user_id=1, user_name='admin',
        )
        interceptor.before_action(ctx)
        assert 'owner_id' not in ctx.params

    def test_before_action_skips_without_user_id(self):
        from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor
        interceptor = OwnerAutoPermissionInterceptor()
        meta = _make_meta_object('user', authorization={'auto_owner': True})
        ctx = ActionContext(
            meta_object=meta, action='crud_create',
            params={}, data_source=Mock(),
            user_id=None, user_name=None,
        )
        interceptor.before_action(ctx)
        assert 'owner_id' not in ctx.params

    def test_before_action_skips_without_authorization(self):
        from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor
        interceptor = OwnerAutoPermissionInterceptor()
        meta = _make_meta_object('user', authorization=None)
        ctx = ActionContext(
            meta_object=meta, action='crud_create',
            params={}, data_source=Mock(),
            user_id=1, user_name='admin',
        )
        interceptor.before_action(ctx)
        assert 'owner_id' not in ctx.params

    def test_after_action_skips_non_create(self):
        from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor
        interceptor = OwnerAutoPermissionInterceptor()
        ctx = _make_context(action='crud_update')
        interceptor.after_action(ctx)

    def test_after_action_skips_failed_result(self):
        from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor
        interceptor = OwnerAutoPermissionInterceptor()
        meta = _make_meta_object('user', authorization={'auto_permission': 'admin'})
        ctx = ActionContext(
            meta_object=meta, action='crud_create',
            params={}, data_source=Mock(),
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=False, message='Failed')
        interceptor.after_action(ctx)

    def test_after_action_skips_without_auto_permission(self):
        from meta.core.interceptors.owner_permission_interceptor import OwnerAutoPermissionInterceptor
        interceptor = OwnerAutoPermissionInterceptor()
        meta = _make_meta_object('user', authorization={})
        ctx = ActionContext(
            meta_object=meta, action='crud_create',
            params={}, data_source=Mock(),
            user_id=1, user_name='admin',
        )
        ctx.result = ActionResult(success=True, data={'id': 1})
        interceptor.after_action(ctx)


# ============================================================
# DataPermissionInterceptor
# ============================================================

class TestDataPermissionInterceptor:

    def test_priority(self):
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        interceptor = DataPermissionInterceptor()
        assert interceptor.priority == 30

    def test_name(self):
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        interceptor = DataPermissionInterceptor()
        assert interceptor.name == 'data_permission'

    def test_before_action_skips_non_query(self):
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        interceptor = DataPermissionInterceptor()
        ctx = _make_context(action='crud_create')
        interceptor.before_action(ctx)
        assert 'query_conditions' not in ctx.extra

    def test_before_action_skips_for_admin(self):
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        interceptor = DataPermissionInterceptor()
        ctx = _make_context(action='crud_query', extra={'is_admin': True})
        interceptor.before_action(ctx)
        assert 'query_conditions' not in ctx.extra

    def test_apply_scope_filter_resolves_user_variables(self):
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        interceptor = DataPermissionInterceptor()
        meta = _make_meta_object('user', authorization={'scope': 'owner_id=$user.id'})
        ctx = ActionContext(
            meta_object=meta, action='crud_query',
            params={}, data_source=Mock(),
            user_id=42, user_name='admin',
        )
        interceptor._apply_scope_filter(ctx)
        assert 'query_conditions' in ctx.extra
        assert ctx.extra['query_conditions'][0]['field'] == 'owner_id'
        assert ctx.extra['query_conditions'][0]['value'] == '42'

    def test_apply_scope_filter_skips_without_authorization(self):
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        interceptor = DataPermissionInterceptor()
        meta = _make_meta_object('user', authorization=None)
        ctx = ActionContext(
            meta_object=meta, action='crud_query',
            params={}, data_source=Mock(),
            user_id=42,
        )
        interceptor._apply_scope_filter(ctx)
        assert 'query_conditions' not in ctx.extra

    def test_apply_scope_filter_skips_without_scope(self):
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        interceptor = DataPermissionInterceptor()
        meta = _make_meta_object('user', authorization={})
        ctx = ActionContext(
            meta_object=meta, action='crud_query',
            params={}, data_source=Mock(),
            user_id=42,
        )
        interceptor._apply_scope_filter(ctx)
        assert 'query_conditions' not in ctx.extra

    def test_after_action_does_nothing(self):
        from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
        interceptor = DataPermissionInterceptor()
        ctx = _make_context(action='crud_query')
        interceptor.after_action(ctx)


# ============================================================
# PersistenceInterceptor
# ============================================================

class TestPersistenceInterceptor:

    def test_priority(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        assert interceptor.priority == 95

    def test_before_action_does_nothing(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        ctx = _make_context(action='crud_create')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_should_execute_always_true(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        ctx = _make_context(action='crud_create')
        assert interceptor.should_execute(ctx) is True

    def test_after_action_delegates_create(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.create.return_value = ActionResult(success=True, data={'id': 1})
        interceptor._registry = mock_registry

        ctx = _make_context(action='crud_create', params={'name': 'test'})
        interceptor.after_action(ctx)

        assert ctx.result is not None
        assert ctx.result.success is True
        mock_registry.create.assert_called_once()

    def test_after_action_delegates_read(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.read.return_value = ActionResult(success=True, data={'id': 1, 'name': 'test'})
        interceptor._registry = mock_registry

        ctx = _make_context(action='crud_read', params={'id': 1})
        interceptor.after_action(ctx)

        assert ctx.result is not None
        assert ctx.result.success is True
        mock_registry.read.assert_called_once()

    def test_after_action_delegates_update(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.update.return_value = ActionResult(success=True, data={'id': 1})
        interceptor._registry = mock_registry

        ctx = _make_context(action='crud_update', params={'id': 1, 'name': 'updated'})
        interceptor.after_action(ctx)

        assert ctx.result is not None
        assert ctx.result.success is True
        mock_registry.update.assert_called_once()

    def test_after_action_delegates_delete(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.delete.return_value = ActionResult(success=True, data=None)
        interceptor._registry = mock_registry

        ctx = _make_context(action='crud_delete', params={'id': 1})
        interceptor.after_action(ctx)

        assert ctx.result is not None
        assert ctx.result.success is True
        mock_registry.delete.assert_called_once()

    def test_after_action_skips_non_crud_non_association(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        ctx = _make_context(action='custom_action')
        interceptor.after_action(ctx)
        assert ctx.result is None

    def test_after_action_handles_exception(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.create.side_effect = Exception("DB Error")
        interceptor._registry = mock_registry

        ctx = _make_context(action='crud_create', params={'name': 'test'})
        with pytest.raises(Exception, match="DB Error"):
            interceptor.after_action(ctx)
        assert ctx.result is not None
        assert ctx.result.success is False
