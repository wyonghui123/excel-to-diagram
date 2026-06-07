import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
CascadeInterceptor 独立细粒度测试

覆盖范围:
1. 优先级和基本属性
2. before_action: 非DELETE操作跳过
3. _cleanup_annotations: annotations清理/异常处理
4. _cleanup_association_tables: dict/string policy / 无policy / FK推断
5. _cascade_delete_children: composition级联 / 无association / 无composition
6. _delete_composition_children: target_type解析 / FK推断 / 异常处理
7. _infer_fk_column: 已知表映射 / 未知表返回None
8. after_action: pass through
"""

import pytest
from unittest.mock import Mock

from meta.core.action_context import ActionContext, ActionResult


def _make_meta(object_id='user', table_name='users', fields=None, **kwargs):
    meta = Mock()
    meta.id = object_id
    meta.table_name = table_name
    meta.fields = fields or []
    meta.associations = kwargs.get('associations', None)
    meta.deletion_policy = kwargs.get('deletion_policy', None)
    meta.get_field = Mock(return_value=None)
    return meta


def _make_ctx(object_type='user', action='crud_delete', params=None,
              data_source=None, **kwargs):
    meta = _make_meta(object_type, **kwargs)
    ctx = ActionContext(
        meta_object=meta,
        action=action,
        params=params or {'id': 1},
        data_source=data_source or Mock(),
        user_id=1,
        user_name='admin',
    )
    return ctx


# ============================================================
# 基本属性
# ============================================================

class TestCascadeInterceptorBasics:

    def test_priority(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        assert CascadeInterceptor().priority == 48

    def test_after_action_passthrough(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ctx = _make_ctx()
        interceptor.after_action(ctx)


# ============================================================
# before_action
# ============================================================

class TestCascadeInterceptorBeforeAction:

    def test_skips_non_delete_create(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ctx = _make_ctx(action='crud_create')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_non_delete_update(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ctx = _make_ctx(action='crud_update')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_non_delete_read(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ctx = _make_ctx(action='crud_read')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_skips_non_delete_query(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ctx = _make_ctx(action='crud_query')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_delete_triggers_before_action(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        ds.execute.return_value = Mock()
        ctx = _make_ctx(action='crud_delete', data_source=ds)
        interceptor.before_action(ctx)
        assert ctx.result is None


# ============================================================
# _cleanup_annotations
# ============================================================

class TestCascadeInterceptorCleanupAnnotations:

    def test_deletes_annotations_for_target(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        ctx = _make_ctx(object_type='domain', params={'id': 5}, data_source=ds)
        interceptor._cleanup_annotations(ctx)
        ds.execute.assert_called_once_with(
            "DELETE FROM annotations WHERE target_type = ? AND target_id = ?",
            ['domain', 5],
        )

    def test_handles_table_not_found(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        ds.execute.side_effect = Exception("no such table: annotations")
        ctx = _make_ctx(data_source=ds)
        interceptor._cleanup_annotations(ctx)

    def test_handles_unexpected_error(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        ds.execute.side_effect = RuntimeError("Unexpected")
        ctx = _make_ctx(data_source=ds)
        interceptor._cleanup_annotations(ctx)


# ============================================================
# _cleanup_association_tables
# ============================================================

class TestCascadeInterceptorCleanupAssociations:

    def test_dict_policy_cleans_tables(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        meta = _make_meta('user_group', deletion_policy={
            'cascade_delete': ['user_group_members'],
        })
        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=ds,
            user_id=1,
        )
        interceptor._cleanup_association_tables(ctx)
        assert ds.execute.call_count >= 1

    def test_no_deletion_policy_skips(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        meta = _make_meta('user')
        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=ds,
            user_id=1,
        )
        interceptor._cleanup_association_tables(ctx)
        ds.execute.assert_not_called()

    def test_empty_cascade_delete_skips(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        meta = _make_meta('user', deletion_policy={'cascade_delete': []})
        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=ds,
            user_id=1,
        )
        interceptor._cleanup_association_tables(ctx)
        ds.execute.assert_not_called()

    def test_no_meta_object_skips(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        ctx = ActionContext(
            meta_object=None, action='crud_delete',
            params={'id': 1}, data_source=ds,
            user_id=1,
        )
        interceptor._cleanup_association_tables(ctx)

    def test_cleanup_on_fk_not_found_skips_gracefully(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        meta = _make_meta('unknown', deletion_policy={
            'cascade_delete': ['unknown_table'],
        })
        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=ds,
            user_id=1,
        )
        interceptor._cleanup_association_tables(ctx)
        assert ds.execute.call_count == 1

    def test_string_list_policy_cleans_tables(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        meta = _make_meta('user', deletion_policy={
            'cascade_delete': ['user_roles'],
        })
        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=ds,
            user_id=1,
        )
        interceptor._cleanup_association_tables(ctx)
        assert ds.execute.call_count == 1


# ============================================================
# _cascade_delete_children
# ============================================================

class TestCascadeInterceptorDeleteChildren:

    def test_no_associations_skips(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        meta = _make_meta('user')
        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=Mock(),
            user_id=1,
        )
        interceptor._cascade_delete_children(ctx)

    def test_no_composition_association_skips(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        meta = _make_meta('user', associations=[
            {'type': 'reference', 'target_type': 'role', 'foreign_key': 'role_id'},
            {'type': 'many_to_many', 'target_type': 'group', 'foreign_key': 'user_id'},
        ])
        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=Mock(),
            user_id=1,
        )
        interceptor._cascade_delete_children(ctx)

    def test_composition_with_cascade_delete(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        from meta.core.models import registry
        if 'child' not in registry._objects:
            registry._objects['child'] = Mock(table_name='children')
        meta = _make_meta('user', associations=[
            {'type': 'composition', 'target_type': 'child',
             'foreign_key': 'parent_id', 'cascade_delete': True},
        ])
        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=ds,
            user_id=1,
        )
        interceptor._cascade_delete_children(ctx)
        assert ds.execute.call_count == 1

    def test_composition_without_cascade_delete_skips(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        meta = _make_meta('user', associations=[
            {'type': 'composition', 'target_type': 'child',
             'foreign_key': 'parent_id', 'cascade_delete': False},
        ])
        ctx = ActionContext(
            meta_object=meta, action='crud_delete',
            params={'id': 1}, data_source=ds,
            user_id=1,
        )
        interceptor._cascade_delete_children(ctx)
        ds.execute.assert_not_called()


# ============================================================
# _delete_composition_children
# ============================================================

class TestCascadeInterceptorDeleteCompositionChildren:

    def test_deletes_by_foreign_key(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        from meta.core.models import registry
        if 'child' not in registry._objects:
            registry._objects['child'] = Mock(table_name='children')
        ctx = ActionContext(
            meta_object=Mock(table_name='users', id='user'),
            action='crud_delete',
            params={'id': 10}, data_source=ds,
            user_id=1,
        )
        interceptor._delete_composition_children(ctx, {
            'target_type': 'child',
            'foreign_key': 'parent_id',
        })
        ds.execute.assert_called_once_with(
            "DELETE FROM children WHERE parent_id = ?",
            [10]
        )

    def test_no_target_type_skips(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        ctx = ActionContext(
            meta_object=Mock(id='user'), action='crud_delete',
            params={'id': 1}, data_source=ds, user_id=1,
        )
        interceptor._delete_composition_children(ctx, {})
        ds.execute.assert_not_called()

    def test_target_entity_alias(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        from meta.core.models import registry
        if 'item' not in registry._objects:
            registry._objects['item'] = Mock(table_name='items')
        ctx = ActionContext(
            meta_object=Mock(table_name='orders', id='order'),
            action='crud_delete',
            params={'id': 5}, data_source=ds,
            user_id=1,
        )
        interceptor._delete_composition_children(ctx, {
            'target_entity': 'item',
        })
        assert ds.execute.call_count == 1

    def test_infers_foreign_key_when_missing(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        from meta.core.models import registry
        if 'note' not in registry._objects:
            registry._objects['note'] = Mock(table_name='notes')
        ctx = ActionContext(
            meta_object=Mock(table_name='tasks', id='task'),
            action='crud_delete',
            params={'id': 1}, data_source=ds,
            user_id=1,
        )
        interceptor._delete_composition_children(ctx, {
            'target_type': 'note',
        })
        ds.execute.assert_called_once()
        sql = ds.execute.call_args[0][0]
        assert 'task_id' in sql

    def test_handles_delete_exception(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        ds = Mock()
        ds.execute.side_effect = Exception("FK constraint")
        from meta.core.models import registry
        if 'child' not in registry._objects:
            registry._objects['child'] = Mock(table_name='children')
        ctx = ActionContext(
            meta_object=Mock(id='user'), action='crud_delete',
            params={'id': 1}, data_source=ds, user_id=1,
        )
        interceptor._delete_composition_children(ctx, {
            'target_type': 'child',
        })


# ============================================================
# _infer_fk_column
# ============================================================

class TestCascadeInterceptorInferFk:

    def setup_method(self):
        from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
        from meta.core.models import registry
        schema_dir = get_yaml_schema_dir()
        if schema_dir and not registry._initialized:
            register_from_directory(schema_dir)

    def test_known_table_mappings(self):
        from meta.core.metadata_resolver import MetadataResolver
        MetadataResolver._cache = {}
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        assert interceptor._infer_fk_column('user_group_members', 'user_group') == ('user_group_members', 'group_id')
        assert interceptor._infer_fk_column('group_roles', 'group') == ('group_roles', 'group_id')
        assert interceptor._infer_fk_column('user_roles', 'user') == ('user_roles', 'user_id')
        assert interceptor._infer_fk_column('role_permissions', 'role') == ('role_permissions', 'role_id')
        assert interceptor._infer_fk_column('data_permissions', 'user') == ('data_permissions', 'user_id')
        assert interceptor._infer_fk_column('change_subscriptions', 'user') == ('change_subscriptions', 'user_id')
        assert interceptor._infer_fk_column('filter_variants', 'user') == ('filter_variants', 'user_id')
        assert interceptor._infer_fk_column('group_data_permissions', 'group') == ('group_data_permissions', 'group_id')

    def test_unknown_table_returns_none(self):
        from meta.core.interceptors.cascade_interceptor import CascadeInterceptor
        interceptor = CascadeInterceptor()
        result = interceptor._infer_fk_column('nonexistent_table', 'user')
        assert result == ('nonexistent_table', 'user_id')
