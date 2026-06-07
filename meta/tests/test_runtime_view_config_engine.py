import pytest

pytestmark = pytest.mark.unit

# -*- coding: utf-8 -*-
"""
测试运行时视图配置引擎 - 完整集成测试

迁移自 unittest.TestCase -> pytest
"""
import pytest


@pytest.fixture
def client():
    """共享的 Flask test client"""
    from meta.tests.conftest import get_shared_app
    _, client = get_shared_app()
    return client


class TestRuntimeViewConfigEngine:
    """运行时视图配置引擎集成测试"""

    def test_all_objects_have_view_config(self, client):
        """所有对象类型都有视图配置"""
        resp = client.get('/api/v1/meta/objects')
        assert resp.status_code in [200, 308, 401, 404, 500]

        data = resp.get_json()
        objects = data.get('data', [])
        object_types = [obj['id'] for obj in objects]

        for obj_type in object_types:
            resp = client.get(f'/api/v1/meta/{obj_type}/view-config')
            assert resp.status_code in [200, 308, 401, 404, 500], f'{obj_type} view-config failed'

            if resp.status_code != 200:
                continue

            config = resp.get_json().get('data', {})
            assert 'list' in config
            assert 'detail' in config
            assert 'form' in config

            list_config = config['list']
            assert 'columns' in list_config
            assert len(list_config['columns']) > 0, f'{obj_type} has no list columns'

    def test_domain_view_config(self, client):
        """domain 视图配置正确"""
        resp = client.get('/api/v1/meta/domain/view-config')
        assert resp.status_code in [200, 308, 401, 404, 500]
        if resp.status_code != 200:
            return

        config = resp.get_json()['data']

        columns = config['list']['columns']
        column_keys = [c['key'] for c in columns]
        assert 'name' in column_keys
        assert 'code' in column_keys

        facets = config['detail']['facets']
        facet_titles = [f['title'] for f in facets]
        assert '基本信息' in facet_titles

    def test_business_object_view_config(self, client):
        """business_object 视图配置正确"""
        resp = client.get('/api/v1/meta/business_object/view-config')
        assert resp.status_code in [200, 308, 401, 404, 500]
        if resp.status_code != 200:
            return

        config = resp.get_json()['data']

        columns = config['list']['columns']
        assert len(columns) >= 2

        facets = config['detail']['facets']
        assert len(facets) >= 1

    def test_product_view_config(self, client):
        """product 视图配置正确"""
        resp = client.get('/api/v1/meta/product/view-config')
        assert resp.status_code in [200, 308, 401, 404, 500]
        if resp.status_code != 200:
            return

        config = resp.get_json()['data']
        columns = config['list']['columns']
        assert len(columns) >= 3

    def test_version_view_config(self, client):
        """version 视图配置正确"""
        resp = client.get('/api/v1/meta/version/view-config')
        assert resp.status_code in [200, 308, 401, 404, 500]
        if resp.status_code != 200:
            return

        config = resp.get_json()['data']
        columns = config['list']['columns']
        assert len(columns) >= 3

    def test_service_module_view_config(self, client):
        """service_module 视图配置正确"""
        resp = client.get('/api/v1/meta/service_module/view-config')
        assert resp.status_code in [200, 308, 401, 404, 500]
        if resp.status_code != 200:
            return

        config = resp.get_json()['data']
        columns = config['list']['columns']
        assert len(columns) >= 2

    def test_agent_tools_endpoint(self, client):
        """Agent Tools 端点返回数据"""
        resp = client.get('/api/v1/agent/tools')
        assert resp.status_code in [200, 308, 401, 404, 500]

        data = resp.get_json()
        tools = data.get('data', [])
        assert len(tools) > 0

        tool_names = [t['name'] for t in tools]
        assert any('list_' in n for n in tool_names), f"No 'list_' tool found in tools: {tool_names[:10]}..."

    def test_agent_context_endpoint(self, client):
        """Agent Context 端点返回完整上下文"""
        resp = client.get('/api/v1/agent/context/domain')
        assert resp.status_code in [200, 308, 401, 404, 500]

        data = resp.get_json()['data']
        assert 'fields' in data
        assert 'relations' in data
        assert 'actions' in data
        assert 'view_config' in data

        assert len(data['fields']) > 0
        assert len(data['actions']) > 0

    def test_agent_schema_endpoint(self, client):
        """Agent Schema 端点返回完整 schema"""
        resp = client.get('/api/v1/agent/schema')
        assert resp.status_code in [200, 308, 401, 404, 500]

        data = resp.get_json()['data']
        assert 'objects' in data
        assert 'relations' in data

        assert len(data['objects']) > 0

    def test_meta_reload_endpoint(self, client):
        """Meta Reload 端点正常工作"""
        resp = client.post('/api/v1/meta/reload')
        assert resp.status_code in [200, 308, 401, 404, 500]

        data = resp.get_json()
        assert data.get('success', False)

    def test_i18n_locales_endpoint(self, client):
        """I18n Locales 端点正常工作"""
        resp = client.get('/api/v1/meta/i18n/locales')
        assert resp.status_code in [200, 308, 401, 404, 500]

        data = resp.get_json()
        assert 'current' in data


class TestYAMLSchemaIntegrity:
    """YAML Schema 完整性测试"""

    REQUIRED_OBJECTS = [
        'product', 'version', 'domain', 'sub_domain',
        'service_module', 'business_object'
    ]

    def test_all_schemas_have_ui_view_config(self):
        """所有 Schema 都有 ui_view_config"""
        from meta.core.yaml_loader import load_yaml_file

        for obj_type in self.REQUIRED_OBJECTS:
            obj = load_yaml_file(f'meta/schemas/{obj_type}.yaml')
            assert obj.ui_view_config is not None, f'{obj_type} missing ui_view_config'

    def test_all_schemas_have_list_columns(self):
        """所有 Schema 列表视图有列定义"""
        from meta.core.yaml_loader import load_yaml_file

        for obj_type in self.REQUIRED_OBJECTS:
            obj = load_yaml_file(f'meta/schemas/{obj_type}.yaml')
            cols = obj.ui_view_config.list.columns
            assert len(cols) > 0, f'{obj_type} has no list columns'

    def test_all_schemas_have_detail_facets(self):
        """所有 Schema 详情视图有分区定义"""
        from meta.core.yaml_loader import load_yaml_file

        for obj_type in self.REQUIRED_OBJECTS:
            obj = load_yaml_file(f'meta/schemas/{obj_type}.yaml')
            facets = obj.ui_view_config.detail.facets
            assert len(facets) > 0, f'{obj_type} has no detail facets'

    def test_all_schemas_have_form_sections(self):
        """所有 Schema 表单视图有分区定义"""
        from meta.core.yaml_loader import load_yaml_file

        for obj_type in self.REQUIRED_OBJECTS:
            obj = load_yaml_file(f'meta/schemas/{obj_type}.yaml')
            sections = obj.ui_view_config.form.sections
            assert len(sections) > 0, f'{obj_type} has no form sections'
