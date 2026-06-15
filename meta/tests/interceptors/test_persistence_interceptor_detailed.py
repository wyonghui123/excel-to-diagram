import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
PersistenceInterceptor 独立细粒度测试

覆盖范围:
1. 优先级和基本属性
2. before_action: pass through
3. should_execute: 始终返回 True
4. after_action: CRUD委托 / 非CRUD跳过 / 异常处理
5. _do_create: registry.create委托 / 成功/失败路径
6. _do_read: registry.read委托 / 不存在
7. _do_update: registry.update委托 / 成功/失败路径
8. _do_delete: registry.delete委托
9. _do_list: 过滤 / 搜索 / 排序 / 分页
10. association_action: associate/dissociate/query_associations委托
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from meta.core.action_context import ActionContext, ActionResult


def _make_meta(object_id='user', table_name='users', fields=None, **kwargs):
    meta = Mock()
    meta.id = object_id
    meta.table_name = table_name
    meta.fields = fields or []
    meta.associations = kwargs.get('associations', None)
    meta.deletion_policy = kwargs.get('deletion_policy', None)
    meta.analytical_model = kwargs.get('analytical_model', None)
    meta.get_field = Mock(return_value=None)
    meta.dimension_fields = []
    meta.searchable_fields = []
    meta.display_name_field = 'name'
    return meta


def _make_ctx(object_type='user', action='crud_create', params=None,
              data_source=None, **kwargs):
    meta = _make_meta(object_type, **kwargs)
    ctx = ActionContext(
        meta_object=meta,
        action=action,
        params=params or {},
        data_source=data_source or Mock(),
        user_id=1,
        user_name='admin',
    )
    return ctx


# ============================================================
# 基本属性
# ============================================================

class TestPersistenceInterceptorBasics:

    def test_priority(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        assert PersistenceInterceptor().priority == 95

    def test_before_action_passthrough(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        ctx = _make_ctx(action='crud_create')
        interceptor.before_action(ctx)
        assert ctx.result is None

    def test_should_execute_always_true(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        ctx = _make_ctx(action='crud_create')
        assert interceptor.should_execute(ctx) is True


# ============================================================
# after_action: action routing
# ============================================================

class TestPersistenceInterceptorAfterAction:

    def test_skips_non_crud_non_association_action(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        ctx = _make_ctx(action='custom_action')
        interceptor.after_action(ctx)
        assert ctx.result is None

    def test_routes_create_to_do_create(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.create.return_value = ActionResult(success=True, data={'id': 1, 'name': 'test'})
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_create', params={'name': 'test'})
        interceptor.after_action(ctx)

        assert ctx.result.success is True
        assert ctx.result.data['id'] == 1
        mock_registry.create.assert_called_once()

    def test_routes_read_to_do_read(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.read.return_value = ActionResult(success=True, data={'id': 1, 'name': 'test'})
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_read', params={'id': 1})
        interceptor.after_action(ctx)

        assert ctx.result.success is True
        mock_registry.read.assert_called_once()

    def test_routes_update_to_do_update(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.update.return_value = ActionResult(success=True, data={'id': 1, 'name': 'updated'})
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_update', params={'id': 1, 'name': 'updated'})
        interceptor.after_action(ctx)

        assert ctx.result.success is True
        mock_registry.update.assert_called_once()

    def test_routes_delete_to_do_delete(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.delete.return_value = ActionResult(success=True, data=None)
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_delete', params={'id': 1})
        interceptor.after_action(ctx)

        assert ctx.result.success is True
        mock_registry.delete.assert_called_once()

    def test_routes_crud_list_to_do_list(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()

        ds = Mock()
        ds._build_conditions = Mock(return_value=([], []))
        cursor = Mock()
        cursor.fetchone.return_value = {'count': 0}
        cursor.fetchall.return_value = []
        cursor.description = [('id', None), ('name', None)]
        ds.execute.return_value = cursor
        mock_registry.ds = ds
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_list', params={}, data_source=ds)
        interceptor.after_action(ctx)

        assert ctx.result.success is True
        assert ctx.result.data == []

    def test_routes_associate_to_association_engine(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_engine = Mock()
        mock_engine.associate.return_value = ActionResult(success=True)
        interceptor._association_engine = mock_engine
        interceptor._registry = Mock()

        ctx = _make_ctx(action='associate', params={'association_name': 'user_roles', 'target_id': 2})
        interceptor.after_action(ctx)

        assert ctx.result.success is True
        mock_engine.associate.assert_called_once()

    def test_routes_dissociate_to_association_engine(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_engine = Mock()
        mock_engine.dissociate.return_value = ActionResult(success=True)
        interceptor._association_engine = mock_engine
        interceptor._registry = Mock()

        ctx = _make_ctx(action='dissociate', params={'association_name': 'user_roles', 'target_id': 2})
        interceptor.after_action(ctx)

        assert ctx.result.success is True
        mock_engine.dissociate.assert_called_once()

    def test_routes_query_associations_to_engine(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_engine = Mock()
        mock_engine.query_associations.return_value = ActionResult(success=True, data=[])
        interceptor._association_engine = mock_engine
        interceptor._registry = Mock()

        ctx = _make_ctx(action='query_associations', params={'association_name': 'user_roles'})
        interceptor.after_action(ctx)

        assert ctx.result.success is True
        mock_engine.query_associations.assert_called_once()

    def test_handles_registry_exception(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.create.side_effect = Exception("DB connection lost")
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_create', params={'name': 'test'})
        with pytest.raises(Exception, match="DB connection lost"):
            interceptor.after_action(ctx)

        assert ctx.result is not None
        assert ctx.result.success is False


# ============================================================
# _do_create
# ============================================================

class TestPersistenceInterceptorDoCreate:

    def test_success_sets_context_params_id(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.create.return_value = ActionResult(success=True, data={'id': 42, 'name': 'test'})
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_create', params={'name': 'test'})
        result = interceptor._do_create(ctx, mock_registry)

        assert result.success is True
        assert result.data['id'] == 42
        assert ctx.params['id'] == 42

    def test_failure_returns_errors(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.create.return_value = ActionResult(
            success=False, message='Name required', errors=['Name required']
        )
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_create', params={})
        result = interceptor._do_create(ctx, mock_registry)

        assert result.success is False
        assert len(result.errors) >= 0


# ============================================================
# _do_read
# ============================================================

class TestPersistenceInterceptorDoRead:

    def test_success_returns_data(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.read.return_value = ActionResult(success=True, data={'id': 1, 'name': 'admin'})
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_read', params={'id': 1})
        result = interceptor._do_read(ctx, mock_registry)

        assert result.success is True
        assert result.data['name'] == 'admin'

    def test_not_found_returns_failure(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.read.return_value = ActionResult(success=False, message='记录不存在')
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_read', params={'id': 999})
        result = interceptor._do_read(ctx, mock_registry)

        assert result.success is False

    def test_enriches_virtual_redundancy_fields(self):
        """[FIX 2026-06-14] BUG-V008 详情页修复: _do_read 必须先 enrich_one
        填充虚拟冗余字段 (e.g. domain_id 从 service_module_id 推导),
        再 enrich_fk_display_names 注入 {field}_display。
        """
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()

        # 模拟 business_object 单条记录: DB 只有 service_module_id, 没有 domain_id/sub_domain_id
        mock_registry = Mock()
        mock_registry.read.return_value = ActionResult(
            success=True,
            data={'id': 1, 'code': 'BO_REQ', 'name': '采购申请', 'service_module_id': 2}
        )
        interceptor._registry = mock_registry

        # Patch EnrichmentEngine.for_data_source to return a stub that records calls
        with patch(
            'meta.core.interceptors.persistence_interceptor.EnrichmentEngine.for_data_source'
        ) as mock_engine_factory:
            stub_engine = Mock()
            # enrich_one 必须把 domain_id 从 None 推导为 1
            stub_engine.enrich_one.return_value = {
                'id': 1, 'code': 'BO_REQ', 'name': '采购申请',
                'service_module_id': 2, 'domain_id': 1, 'sub_domain_id': 1,
                'domain_name': '采购管理', 'sub_domain_name': '采购需求',
            }
            # enrich_fk_display_names 必须基于已有 FK 值注入 display 字段
            stub_engine.enrich_fk_display_names.return_value = {
                'id': 1, 'code': 'BO_REQ', 'name': '采购申请',
                'service_module_id': 2, 'domain_id': 1, 'sub_domain_id': 1,
                'domain_name': '采购管理', 'sub_domain_name': '采购需求',
                'domain_id_display': '采购管理', 'sub_domain_id_display': '采购需求',
                'service_module_id_display': '供应商管理',
            }
            mock_engine_factory.return_value = stub_engine

            ctx = _make_ctx(
                object_type='business_object', action='crud_read', params={'id': 1}
            )
            result = interceptor._do_read(ctx, mock_registry)

        assert result.success is True
        # 验证 enrich_one 被调用
        stub_engine.enrich_one.assert_called_once()
        # 验证 enrich_fk_display_names 被调用
        stub_engine.enrich_fk_display_names.assert_called_once()
        # 验证 call 顺序: enrich_one 必须先于 enrich_fk_display_names
        call_order = [c[0] for c in stub_engine.method_calls]
        assert call_order.index('enrich_one') < call_order.index('enrich_fk_display_names'), \
            f"enrich_one should be called before enrich_fk_display_names, got order: {call_order}"
        # 验证最终数据中包含 domain_id
        assert result.data.get('domain_id') == 1
        assert result.data.get('domain_id_display') == '采购管理'


# ============================================================
# _do_update
# ============================================================

class TestPersistenceInterceptorDoUpdate:

    def test_success_returns_updated_data(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.update.return_value = ActionResult(success=True, data={'id': 1, 'name': 'updated'})
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_update', params={'id': 1, 'name': 'updated'})
        result = interceptor._do_update(ctx, mock_registry)

        assert result.success is True
        assert result.data['name'] == 'updated'

    def test_failure_returns_errors(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.update.return_value = ActionResult(success=False, message='Not found')
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_update', params={'id': 999})
        result = interceptor._do_update(ctx, mock_registry)

        assert result.success is False


# ============================================================
# _do_delete
# ============================================================

class TestPersistenceInterceptorDoDelete:

    def test_success_returns_null_data(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.delete.return_value = ActionResult(success=True, data=None)
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_delete', params={'id': 1})
        result = interceptor._do_delete(ctx, mock_registry)

        assert result.success is True
        assert result.data is None

    def test_failure_returns_errors(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        mock_registry = Mock()
        mock_registry.delete.return_value = ActionResult(success=False, message='FK constraint')
        interceptor._registry = mock_registry

        ctx = _make_ctx(action='crud_delete', params={'id': 1})
        result = interceptor._do_delete(ctx, mock_registry)

        assert result.success is False


# ============================================================
# _do_list
# ============================================================

class TestPersistenceInterceptorDoList:

    def _make_list_meta_and_registry(self, table_name='users'):
        meta = _make_meta('user', table_name=table_name)
        ds = Mock()
        ds._build_conditions = Mock(return_value=([], []))
        # [FIX 2026-06-07] 添加 _get_table_columns mock，返回包含 name 的列
        # 否则拦截器会因为 name 不在 columns 中而跳过 ORDER BY
        ds._get_table_columns = Mock(return_value=['id', 'name', 'code'])
        cursor = Mock()
        cursor.fetchone.return_value = {'count': 0}
        cursor.fetchall.return_value = []
        cursor.description = [('id', None), ('name', None)]
        ds.execute.return_value = cursor
        mock_registry = Mock()
        mock_registry.ds = ds
        return meta, mock_registry, ds

    def test_list_returns_success_with_empty_data(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        meta, mock_registry, _ = self._make_list_meta_and_registry()

        ctx = ActionContext(
            meta_object=meta, action='crud_list',
            params={}, data_source=mock_registry.ds, user_id=1,
        )
        result = interceptor._do_list(ctx, mock_registry)

        assert result.success is True
        assert result.data == []

    def test_pagination_calculates_offset(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        meta, mock_registry, ds = self._make_list_meta_and_registry()

        ctx = ActionContext(
            meta_object=meta, action='crud_list',
            params={'page': '2', 'page_size': '10'},
            data_source=ds, user_id=1,
        )

        def capture_sql(sql, params=None):
            captured = Mock()
            captured.fetchone.return_value = {'count': 7}
            captured.description = [('id', None), ('name', None)]
            captured.fetchall.return_value = []
            ds._last_sql = sql
            ds._last_params = params
            return captured

        ds.execute.side_effect = capture_sql
        result = interceptor._do_list(ctx, mock_registry)

        assert result.success is True
        assert list(ds._last_params[-2:]) == [10, 10]

    def test_limit_ceiling_at_500(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        meta, mock_registry, ds = self._make_list_meta_and_registry()

        ctx = ActionContext(
            meta_object=meta, action='crud_list',
            params={'_limit': '2000'},
            data_source=ds, user_id=1,
        )

        def capture_sql(sql, params=None):
            captured = Mock()
            captured.fetchone.return_value = {'count': 0}
            captured.description = [('id', None), ('name', None)]
            captured.fetchall.return_value = []
            ds._last_sql = sql
            ds._last_params = params
            return captured

        ds.execute.side_effect = capture_sql
        result = interceptor._do_list(ctx, mock_registry)

        assert result.success is True
        assert ds._last_params[0] == 500

    def test_invalid_limit_defaults_to_20(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        meta, mock_registry, ds = self._make_list_meta_and_registry()

        ctx = ActionContext(
            meta_object=meta, action='crud_list',
            params={'_limit': 'invalid'},
            data_source=ds, user_id=1,
        )

        def capture_sql(sql, params=None):
            captured = Mock()
            captured.fetchone.return_value = {'count': 0}
            captured.description = [('id', None), ('name', None)]
            captured.fetchall.return_value = []
            ds._last_sql = sql
            ds._last_params = params
            return captured

        ds.execute.side_effect = capture_sql
        result = interceptor._do_list(ctx, mock_registry)

        assert result.success is True
        assert ds._last_params[0] == 20

    def test_ordering_param_resolved(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        meta, mock_registry, ds = self._make_list_meta_and_registry()

        # v3.18 fix: ordering需要name字段存在于meta_object.fields中
        # 之前的测试是Mock字段，导致_get_table_columns返回Mock对象，跳过排序
        # 这里我们mock _get_table_columns返回包含id和name的frozenset
        ds._get_table_columns = Mock(return_value=frozenset(['id', 'name']))

        # 创建一个简单的name field mock
        name_field = Mock()
        name_field.storage = None  # 非VIRTUAL
        name_field.db_column = 'name'
        meta.get_field = Mock(side_effect=lambda f: name_field if f == 'name' else None)

        ctx = ActionContext(
            meta_object=meta, action='crud_list',
            params={'ordering': '-name'},
            data_source=ds, user_id=1,
        )

        def capture_sql(sql, params=None):
            captured = Mock()
            captured.fetchone.return_value = {'count': 0}
            captured.description = [('id', None), ('name', None)]
            captured.fetchall.return_value = []
            ds._last_sql = sql
            return captured

        ds.execute.side_effect = capture_sql
        result = interceptor._do_list(ctx, mock_registry)

        assert result.success is True
        assert 'name DESC' in ds._last_sql

    def test_filters_param_supported(self):
        from meta.core.interceptors.persistence_interceptor import PersistenceInterceptor
        interceptor = PersistenceInterceptor()
        meta, mock_registry, ds = self._make_list_meta_and_registry()

        ctx = ActionContext(
            meta_object=meta, action='crud_list',
            params={'filters': {'status': 'active'}},
            data_source=ds, user_id=1,
        )

        def capture_sql(sql, params=None):
            captured = Mock()
            captured.fetchone.return_value = {'count': 0}
            captured.description = [('id', None), ('name', None)]
            captured.fetchall.return_value = []
            ds._last_sql = sql
            ds._last_params = params
            return captured

        ds.execute.side_effect = capture_sql
        result = interceptor._do_list(ctx, mock_registry)

        assert result.success is True
