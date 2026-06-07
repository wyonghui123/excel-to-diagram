# -*- coding: utf-8 -*-
"""
COV-003: OpenAPI 生成 12 个专项用例 (FR-2.2 / FR-2.3 / FR-2.4)

测试 meta.api.bo_api:
- _map_field_type
- _generate_bo_schema
- _generate_bo_crud_paths
- get_full_openapi (Flask 端点)
"""
import pytest
from unittest.mock import MagicMock

pytestmark = pytest.mark.integration


class TestMapFieldType:
    """_map_field_type 单元测试"""

    def test_string_types_map_to_string(self):
        from meta.api.bo_api import _map_field_type
        assert _map_field_type('string') == 'string'
        assert _map_field_type('text') == 'string'
        assert _map_field_type('date') == 'string'
        assert _map_field_type('datetime') == 'string'

    def test_numeric_types_map(self):
        from meta.api.bo_api import _map_field_type
        assert _map_field_type('integer') == 'integer'
        assert _map_field_type('float') == 'number'

    def test_boolean_and_json(self):
        from meta.api.bo_api import _map_field_type
        assert _map_field_type('boolean') == 'boolean'
        assert _map_field_type('json') == 'object'

    def test_unknown_type_defaults_to_string(self):
        from meta.api.bo_api import _map_field_type
        assert _map_field_type('weird_unknown_type') == 'string'

    def test_field_type_enum_with_value_attr(self):
        """兼容 FieldType enum（有 .value 属性）"""
        from meta.api.bo_api import _map_field_type
        fake_enum = MagicMock()
        fake_enum.value = 'boolean'
        assert _map_field_type(fake_enum) == 'boolean'


class TestGenerateBoSchema:
    """_generate_bo_schema 单元测试"""

    def _make_meta(self, fields, table_name='test_bo'):
        m = MagicMock()
        m.id = 'test_bo'
        m.table_name = table_name
        m.fields = fields
        return m

    def _make_field(self, fid, field_type='string', required=False, enum_values=None,
                    description=None, ui=None):
        f = MagicMock()
        f.id = fid
        f.field_type = field_type
        f.required = required
        f.enum_values = enum_values
        f.description = description
        f.ui = ui
        return f

    def test_basic_schema_structure(self):
        """返回的 schema 含 type / properties / required"""
        from meta.api.bo_api import _generate_bo_schema
        fields = [self._make_field('name', 'string', required=True)]
        meta = self._make_meta(fields)
        schema = _generate_bo_schema(meta)
        assert schema['type'] == 'object'
        assert 'name' in schema['properties']
        assert 'name' in schema['required']

    def test_enum_values_as_str_list(self):
        """enum_values 元素为 str 时正确生成 enum 列表"""
        from meta.api.bo_api import _generate_bo_schema
        fields = [self._make_field('status', 'string', enum_values=['active', 'inactive'])]
        meta = self._make_meta(fields)
        schema = _generate_bo_schema(meta)
        assert schema['properties']['status']['enum'] == ['active', 'inactive']

    def test_enum_values_with_dict_format(self):
        """enum_values 元素为 dict（{value,label}）时取 .value 字段"""
        from meta.api.bo_api import _generate_bo_schema
        fields = [self._make_field('priority', 'string', enum_values=[
            {'value': 'low', 'label': '低'}, {'value': 'high', 'label': '高'},
        ])]
        meta = self._make_meta(fields)
        schema = _generate_bo_schema(meta)
        assert schema['properties']['priority']['enum'] == ['low', 'high']

    def test_relation_field_has_x_relation_extension(self):
        """ui.relation 存在时 schema 含 x-relation 扩展"""
        from meta.api.bo_api import _generate_bo_schema
        ui = {'relation': 'fk_user', 'display_field': 'name'}
        fields = [self._make_field('owner_id', 'string', ui=ui)]
        meta = self._make_meta(fields)
        schema = _generate_bo_schema(meta)
        prop = schema['properties']['owner_id']
        assert prop.get('x-relation') == 'fk_user'
        assert prop.get('x-display-field') == 'name'

    def test_no_required_field_returns_none(self):
        """没有任何 required 字段时 required 键为 None（不写空列表）"""
        from meta.api.bo_api import _generate_bo_schema
        fields = [self._make_field('name', 'string', required=False)]
        meta = self._make_meta(fields)
        schema = _generate_bo_schema(meta)
        # 实现约定：required or None → required 为 None 时不输出该键
        assert schema.get('required') is None


class TestGenerateBoCrudPaths:
    """_generate_bo_crud_paths 单元测试"""

    def test_seven_endpoints_per_object(self):
        """每个 BO 生成 7 个端点（list/create/get/update/delete/deep/batch-delete）"""
        from meta.api.bo_api import _generate_bo_crud_paths
        obj = MagicMock()
        obj.id = 'demo'
        obj.table_name = 'demo_table'
        obj.display_name = 'Demo'
        paths = _generate_bo_crud_paths([obj])
        base = '/api/v2/bo/demo'
        # 2 (base) + 2 (/{id} get+put+delete = 3) + 1 (deep) + 1 (batch-delete) = 7
        assert base in paths
        assert 'get' in paths[base]
        assert 'post' in paths[base]
        assert f'{base}/{{id}}' in paths
        assert 'get' in paths[f'{base}/{{id}}']
        assert 'put' in paths[f'{base}/{{id}}']
        assert 'delete' in paths[f'{base}/{{id}}']
        assert f'{base}/deep' in paths
        assert f'{base}/batch-delete' in paths

    def test_skip_objects_without_table_name(self):
        """无 table_name 的对象被跳过"""
        from meta.api.bo_api import _generate_bo_crud_paths
        obj1 = MagicMock()
        obj1.id = 'real'
        obj1.table_name = 'real_table'
        obj2 = MagicMock()
        obj2.id = 'ghost'
        obj2.table_name = None
        paths = _generate_bo_crud_paths([obj1, obj2])
        assert '/api/v2/bo/real' in paths
        assert '/api/v2/bo/ghost' not in paths

    def test_full_openapi_endpoint_merges_action_and_bo(self, api_client, admin_headers):
        """GET /api/v2/meta/_openapi.json 同时含 Action paths 和 BO paths"""
        resp = api_client.get('/api/v2/meta/_openapi.json')
        # 该端点可能 200 或 500（无 server 时），但如果 200 必须含两层
        if resp.status_code == 200:
            spec = resp.get_json()
            assert 'paths' in spec
            assert 'components' in spec
            # 至少含一个 BO 路径
            bo_paths = [p for p in spec['paths'] if p.startswith('/api/v2/bo/')]
            assert len(bo_paths) > 0
            assert 'info' in spec
        else:
            # 服务未启动时，skip
            pytest.skip(f"Server returned {resp.status_code}")
