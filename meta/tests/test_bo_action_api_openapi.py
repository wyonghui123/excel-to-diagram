# -*- coding: utf-8 -*-
"""
COV-001: _generate_action_openapi 专项单元测试 (8 用例)

[NEW] v1.2 / FR-2.1: 测试 bo_action_api._generate_action_openapi 独立函数
- 验证 OpenAPI 3.0 规范结构
- 验证 paths / components.schemas / tags
- 验证 function 操作用 GET，action 操作用 POST
- 验证 admin_only 标记
- 验证 input_schema 缺省处理
- 验证 operationId 用 . → _ 替换
"""
import unittest
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.unit


class TestGenerateActionOpenAPI:
    """_generate_action_openapi 单元测试 (COV-001)"""

    def _make_meta(self, action_id='test.action', description='Test action',
                   input_schema=None, output_schema=None, operation_type='action',
                   category='business', requires_admin=False):
        m = MagicMock()
        m.action_id = action_id
        m.description = description
        m.input_schema = input_schema
        m.output_schema = output_schema
        m.operation_type = operation_type
        m.category = category
        m.requires_admin = requires_admin
        return m

    def test_returns_valid_openapi_3_structure(self):
        """返回结构含 openapi / info / paths / components / tags 五个顶层键"""
        with patch('meta.api.bo_action_api.bo_action_registry') as reg:
            reg.list_all.return_value = []
            from meta.api.bo_action_api import _generate_action_openapi
            spec = _generate_action_openapi('http://localhost:3010')
        assert spec['openapi'] == '3.0.0'
        assert 'info' in spec
        assert 'paths' in spec
        assert 'components' in spec
        assert 'schemas' in spec['components']
        assert 'tags' in spec

    def test_action_path_uses_get_for_function_type(self):
        """operation_type=function 的 Action 用 GET 方法"""
        meta = self._make_meta(
            action_id='function.lookup',
            operation_type='function',
            input_schema={'properties': {'id': {'type': 'string'}}, 'required': ['id']},
        )
        with patch('meta.api.bo_action_api.bo_action_registry') as reg:
            reg.list_all.return_value = [meta]
            from meta.api.bo_action_api import _generate_action_openapi
            spec = _generate_action_openapi('http://localhost:3010')
        path = '/api/v2/action/function.lookup'
        assert path in spec['paths']
        assert 'get' in spec['paths'][path]
        assert 'post' not in spec['paths'][path]

    def test_action_path_uses_post_for_action_type(self):
        """operation_type=action 的 Action 用 POST 方法"""
        meta = self._make_meta(
            action_id='business.create',
            operation_type='action',
            input_schema={'properties': {'name': {'type': 'string'}}, 'required': ['name']},
        )
        with patch('meta.api.bo_action_api.bo_action_registry') as reg:
            reg.list_all.return_value = [meta]
            from meta.api.bo_action_api import _generate_action_openapi
            spec = _generate_action_openapi('http://localhost:3010')
        path = '/api/v2/action/business.create'
        assert 'post' in spec['paths'][path]
        assert spec['paths'][path]['post']['operationId'] == 'business.create'

    def test_operation_id_dots_replaced_with_underscore(self):
        """schema 引用 safe_id 中 . 替换为 _"""
        meta = self._make_meta(
            action_id='a.b.c',
            operation_type='function',
            input_schema={'properties': {'x': {'type': 'string'}}},
        )
        with patch('meta.api.bo_action_api.bo_action_registry') as reg:
            reg.list_all.return_value = [meta]
            from meta.api.bo_action_api import _generate_action_openapi
            spec = _generate_action_openapi('http://localhost:3010')
        assert 'a_b_c_input' in spec['components']['schemas']
        assert 'a_b_c_output' in spec['components']['schemas']

    def test_admin_action_gets_admin_only_marker(self):
        """requires_admin=True 的 Action description 包含 (admin only)"""
        meta = self._make_meta(
            action_id='admin.reset',
            operation_type='action',
            input_schema={'properties': {}},
            requires_admin=True,
        )
        with patch('meta.api.bo_action_api.bo_action_registry') as reg:
            reg.list_all.return_value = [meta]
            from meta.api.bo_action_api import _generate_action_openapi
            spec = _generate_action_openapi('http://localhost:3010')
        desc = spec['paths']['/api/v2/action/admin.reset']['post'].get('description', '')
        assert '(admin only)' in desc

    def test_missing_input_schema_uses_additional_properties(self):
        """input_schema 为 None 时使用 additionalProperties: True 默认 schema"""
        meta = self._make_meta(
            action_id='legacy.action',
            operation_type='action',
            input_schema=None,
        )
        with patch('meta.api.bo_action_api.bo_action_registry') as reg:
            reg.list_all.return_value = [meta]
            from meta.api.bo_action_api import _generate_action_openapi
            spec = _generate_action_openapi('http://localhost:3010')
        schema = spec['components']['schemas']['legacy_action_input']
        assert schema == {'type': 'object', 'additionalProperties': True}

    def test_missing_output_schema_includes_default_envelope(self):
        """output_schema 为 None 时使用含 success/data/message 的默认 envelope"""
        meta = self._make_meta(
            action_id='legacy.q',
            operation_type='function',
            input_schema={'properties': {}},
            output_schema=None,
        )
        with patch('meta.api.bo_action_api.bo_action_registry') as reg:
            reg.list_all.return_value = [meta]
            from meta.api.bo_action_api import _generate_action_openapi
            spec = _generate_action_openapi('http://localhost:3010')
        out = spec['components']['schemas']['legacy_q_output']
        assert out['type'] == 'object'
        assert 'success' in out['properties']
        assert 'message' in out['properties']

    def test_function_action_summary_has_function_label(self):
        """operation_type=function 的 summary 加 [FUNCTION] 前缀"""
        meta = self._make_meta(
            action_id='func.lookup',
            description='Lookup things',
            operation_type='function',
            input_schema={'properties': {}},
        )
        with patch('meta.api.bo_action_api.bo_action_registry') as reg:
            reg.list_all.return_value = [meta]
            from meta.api.bo_action_api import _generate_action_openapi
            spec = _generate_action_openapi('http://localhost:3010')
        summary = spec['paths']['/api/v2/action/func.lookup']['get']['summary']
        assert summary.startswith('[FUNCTION]')

    def test_tags_grouped_by_category_and_operation_type(self):
        """tags 按 category/operation_type 组合分组"""
        meta1 = self._make_meta(action_id='a1', operation_type='function', category='admin')
        meta2 = self._make_meta(action_id='a2', operation_type='action', category='admin')
        with patch('meta.api.bo_action_api.bo_action_registry') as reg:
            reg.list_all.return_value = [meta1, meta2]
            from meta.api.bo_action_api import _generate_action_openapi
            spec = _generate_action_openapi('http://localhost:3010')
        # tags 是 list of dicts [{'name': 'xxx'}, ...] — 取 name 字段
        tag_names = {t.get('name') if isinstance(t, dict) else t for t in spec['tags']}
        assert 'admin/function' in tag_names
        assert 'admin/action' in tag_names
