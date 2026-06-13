# -*- coding: utf-8 -*-
"""
测试 get_architecture_preview 的 ID 过滤下推优化 (FR-004 + FR-009)

策略：使用 __wrapped__ 绕过 login_required 装饰器
"""
import pytest
from unittest.mock import MagicMock, patch
from flask import Flask


def _unwrap(func):
    """递归解除装饰器"""
    while hasattr(func, '__wrapped__'):
        func = func.__wrapped__
    return func


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def make_bo_mock():
    """工厂：构造一个 mock BO 框架"""
    def _make(query_results=None):
        bo = MagicMock()

        def fake_query(object_type, filters=None, page=None, page_size=None):
            result = MagicMock()
            result.success = True
            id_filter = (filters or {}).get('id__in', [])
            if id_filter:
                all_data = query_results.get(object_type, []) if query_results else []
                result.data = [d for d in all_data if d.get('id') in id_filter]
            else:
                result.data = query_results.get(object_type, []) if query_results else []
            return result

        bo.query.side_effect = fake_query
        return bo
    return _make


def _patch_and_call(bo, url):
    """统一 patch 入口并执行原函数"""
    from meta.api import bo_api_preview
    # [FR-012] 函数已迁移到 bo_api_preview 模块，直接调用 impl
    orig_func = bo_api_preview.get_architecture_preview_impl
    # bo_framework 只在 bo_api 中 import，impl 函数直接接受 bo 参数
    with patch('meta.api.bo_api_preview.jsonify', lambda d: d):
        with _get_app().test_request_context(url):
            return orig_func(bo)


def _get_app():
    """获取或创建 flask app"""
    if not hasattr(_get_app, '_app'):
        app = Flask(__name__)
        app.config['TESTING'] = True
        _get_app._app = app
    return _get_app._app


class TestArchitecturePreviewIDPushdown:
    """测试 ID 列表过滤下推到 SQL"""

    def test_domain_id_in_filter_applied(self, make_bo_mock):
        """[FR-009] domain_ids 非空时，domain 查询应包含 id__in 过滤"""
        bo = make_bo_mock({
            'domain': [{'id': 1, 'name': 'A'}, {'id': 2, 'name': 'B'}, {'id': 3, 'name': 'C'}]
        })
        _patch_and_call(bo, '/api/v2/architecture/preview?domain_ids=1,3')

        domain_call = next((c for c in bo.query.call_args_list if c[0][0] == 'domain'), None)
        assert domain_call is not None
        filters = domain_call[0][1] or {}
        assert 'id__in' in filters
        assert set(filters['id__in']) == {1, 3}

    def test_page_size_reduced_with_id_filter(self, make_bo_mock):
        """[FR-009] 当有 id__in 过滤时，page_size 应降低"""
        bo = make_bo_mock({})
        _patch_and_call(bo, '/api/v2/architecture/preview?domain_ids=1,2,3,4,5')

        domain_call = next(c for c in bo.query.call_args_list if c[0][0] == 'domain')
        page_size = domain_call[1].get('page_size')
        # 5 ID × 2 = 10
        assert page_size is not None and page_size <= 10, f"page_size={page_size}"

    def test_no_filter_keeps_5000_page_size(self, make_bo_mock):
        """无 ID 过滤时，page_size 保持 5000（向后兼容）"""
        bo = make_bo_mock({})
        _patch_and_call(bo, '/api/v2/architecture/preview')

        domain_call = next(c for c in bo.query.call_args_list if c[0][0] == 'domain')
        page_size = domain_call[1].get('page_size')
        assert page_size == 5000

    def test_relationship_query_uses_bo_in_filter(self, make_bo_mock):
        """[FR-009] 关系表应使用 source_bo_id__in + target_bo_id__in"""
        bo = make_bo_mock({})
        _patch_and_call(bo, '/api/v2/architecture/preview?business_object_ids=10,20')

        rel_call = next(c for c in bo.query.call_args_list if c[0][0] == 'relationship')
        filters = rel_call[0][1] or {}
        assert 'source_bo_id__in' in filters
        assert 'target_bo_id__in' in filters
        assert set(filters['source_bo_id__in']) == {10, 20}
        assert set(filters['target_bo_id__in']) == {10, 20}

    def test_all_4_entities_get_id_filter(self, make_bo_mock):
        """[FR-009] 4 个实体都应下推 ID 过滤"""
        bo = make_bo_mock({})
        _patch_and_call(bo, '/api/v2/architecture/preview?domain_ids=1,2&sub_domain_ids=3,4&service_module_ids=5,6&business_object_ids=7,8')

        for entity, expected_ids in [
            ('domain', {1, 2}),
            ('sub_domain', {3, 4}),
            ('service_module', {5, 6}),
            ('business_object', {7, 8}),
        ]:
            call = next((c for c in bo.query.call_args_list if c[0][0] == entity), None)
            assert call is not None, f"{entity} 查询应存在"
            filters = call[0][1] or {}
            assert 'id__in' in filters, f"{entity} 应包含 id__in"
            assert set(filters['id__in']) == expected_ids

    def test_id_filter_does_not_affect_center_scope(self, make_bo_mock):
        """[FR-009] center_scope 仍基于请求的 bo_id_list 计算（不变）"""
        bo = make_bo_mock({
            'business_object': [
                {'id': 10, 'code': 'BO_A', 'service_module_id': 5},
                {'id': 20, 'code': 'BO_B', 'service_module_id': 5},
                {'id': 30, 'code': 'BO_C', 'service_module_id': 6},
            ]
        })
        result = _patch_and_call(bo, '/api/v2/architecture/preview?business_object_ids=10,20')

        if isinstance(result, tuple):
            result = result[0]
        assert isinstance(result, dict), f"result={type(result)}"
        # result 结构是 {'success': True, 'data': {...}}
        data = result.get('data', result)
        assert 'BO_A' in data.get('center_scope', []), f"center_scope={data.get('center_scope')}"
        assert 'BO_B' in data.get('center_scope', []), f"center_scope={data.get('center_scope')}"
        assert 'BO_C' not in data.get('center_scope', []), f"center_scope={data.get('center_scope')}"

    def test_empty_id_list_treated_as_no_filter(self, make_bo_mock):
        """空 ID 列表等同无过滤"""
        bo = make_bo_mock({})
        _patch_and_call(bo, '/api/v2/architecture/preview?domain_ids=&sub_domain_ids=')

        domain_call = next(c for c in bo.query.call_args_list if c[0][0] == 'domain')
        filters = domain_call[0][1] or {}
        assert 'id__in' not in filters

    def test_id_set_conversion_for_o1_lookup(self, make_bo_mock):
        """[FR-009] Python 端 fallback 过滤应使用 set（O(1) lookup）"""
        bo = make_bo_mock({
            'domain': [
                {'id': 1, 'name': 'A'},
                {'id': 2, 'name': 'B'},
                {'id': 999, 'name': 'OUTSIDER'},
            ]
        })
        result = _patch_and_call(bo, '/api/v2/architecture/preview?domain_ids=1,2')

        if isinstance(result, tuple):
            result = result[0]
        # result 结构是 {'success': True, 'data': {'domains': [...], ...}}
        data = result.get('data', result)
        domain_ids_returned = [d['id'] for d in data.get('domains', [])]
        assert 999 not in domain_ids_returned, f"domains={data.get('domains')}"
        assert 1 in domain_ids_returned, f"domains={data.get('domains')}"
        assert 2 in domain_ids_returned, f"domains={data.get('domains')}"
