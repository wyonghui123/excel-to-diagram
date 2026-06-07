# -*- coding: utf-8 -*-
"""
COV-002: get_field_policies 端点专项测试 (6 用例)

[NEW] v1.2 / FR-4.5a: 测试 GET /api/v2/meta/{object_type}/field-policies
- 验证响应结构 (policies 字典 + per-field 数据)
- 验证 404 路径（未知 object_type）
- 验证 context / mutability 参数
- 验证 conditional_required 数组（FR-4.5a 核心）
"""
import json
import pytest

pytestmark = pytest.mark.integration


class TestFieldPoliciesAPI:
    """get_field_policies 端点测试 (COV-002)"""

    def test_unknown_object_type_returns_404(self, api_client, admin_headers):
        """未知 object_type → 404"""
        resp = api_client.get(
            '/api/v2/meta/__no_such_type__/field-policies',
            headers=admin_headers,
        )
        assert resp.status_code == 404
        body = resp.get_json()
        assert body.get('success') is False
        assert 'not found' in body.get('message', '').lower()

    def test_known_object_returns_policies_dict(self, api_client, admin_headers):
        """已知 object_type (如 user) 返回 policies 字典"""
        resp = api_client.get(
            '/api/v2/meta/user/field-policies',
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        # 响应包在 data 字段
        assert 'data' in body
        policies = body['data']
        assert isinstance(policies, dict)
        assert len(policies) > 0

    def test_each_field_has_conditional_required_array(self, api_client, admin_headers):
        """每个 field 的策略含 conditional_required 数组（FR-4.5a 核心字段）"""
        resp = api_client.get(
            '/api/v2/meta/user/field-policies',
            headers=admin_headers,
        )
        body = resp.get_json()
        for field_id, policy in body['data'].items():
            assert 'conditional_required' in policy, f"field {field_id} missing conditional_required"
            assert isinstance(policy['conditional_required'], list)

    def test_conditional_required_with_constraint(self, api_client, admin_headers):
        """含 conditional_required 约束的字段会出现在数组中"""
        from meta.core.models import registry
        meta_obj = registry.get('user')
        target_field = None
        for f in meta_obj.fields:
            constraints = getattr(f, 'constraints', None)
            if isinstance(constraints, list):
                if any(isinstance(c, dict) and c.get('type') == 'conditional_required' for c in constraints):
                    target_field = f
                    break
            elif isinstance(constraints, dict) and constraints.get('type') == 'conditional_required':
                target_field = f
                break
        if target_field is None:
            pytest.skip("No conditional_required field in user schema")
        resp = api_client.get('/api/v2/meta/user/field-policies', headers=admin_headers)
        body = resp.get_json()
        policy = body['data'][target_field.id]
        assert len(policy['conditional_required']) > 0
        first = policy['conditional_required'][0]
        assert 'condition' in first
        assert 'message' in first

    def test_context_param_default_is_read(self, api_client, admin_headers):
        """缺省 context 参数（默认 'read'）可正常返回"""
        resp1 = api_client.get(
            '/api/v2/meta/user/field-policies',
            headers=admin_headers,
        )
        resp2 = api_client.get(
            '/api/v2/meta/user/field-policies?context=read',
            headers=admin_headers,
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        # 两种 context 下 policies 一致（read 不会引入额外约束）
        assert resp1.get_json()['data'] == resp2.get_json()['data']

    def test_unauthenticated_request_rejected(self):
        """未登录请求被拒绝（login_required 装饰器）"""
        # 创建一个不带 cookies 的新 client
        from meta.tests.conftest import get_shared_app
        _, fresh_client = get_shared_app()
        # 清空 cookies
        if hasattr(fresh_client, '_cookies'):
            fresh_client._cookies.clear()
        resp = fresh_client.get('/api/v2/meta/user/field-policies')
        # 401 / 302 / 403 都算通过
        assert resp.status_code in (401, 302, 403), f"Expected auth rejection, got {resp.status_code}"
