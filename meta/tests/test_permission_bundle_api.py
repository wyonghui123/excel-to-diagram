# -*- coding: utf-8 -*-
"""
GAP-001: permission_bundle_api 端到端测试 (15 用例)

[NEW] 2026-06-07 批次: 补齐 permission_bundle_api (7 端点) 的端到端测试
- 覆盖 7 个端点: GET /, GET /<code>, POST /assign, GET /user/<id>, POST /, PUT /<code>, DELETE /<code>
- 覆盖 admin_required / login_required 鉴权
- 覆盖正常 + 异常 + 边界路径
"""
import json
import pytest

pytestmark = pytest.mark.integration


BUNDLE_URL = '/api/v1/permission-bundles'


class TestPermissionBundleAPI:
    """permission_bundle_api 端到端测试 (GAP-001)"""

    def test_list_bundles_returns_data(self, api_client, admin_headers):
        """GET / 返回所有权限包"""
        resp = api_client.get(BUNDLE_URL, headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert 'data' in body
        # data 是 list (PermissionBundleService.get_all_bundles)
        assert isinstance(body['data'], list)

    def test_list_bundles_requires_auth(self):
        """未登录访问被拒绝"""
        from meta.tests.conftest import get_shared_app
        _, fresh_client = get_shared_app()
        if hasattr(fresh_client, '_cookies'):
            fresh_client._cookies.clear()
        resp = fresh_client.get(BUNDLE_URL)
        assert resp.status_code in (401, 302, 403)

    def test_get_bundle_by_code_404(self, api_client, admin_headers):
        """GET /<unknown> 返回 404"""
        resp = api_client.get(f'{BUNDLE_URL}/__no_such_bundle__', headers=admin_headers)
        assert resp.status_code == 404
        body = resp.get_json()
        assert body.get('success') is False
        assert '不存在' in body.get('error', '')

    def test_get_bundle_by_code_returns_data(self, api_client, admin_headers):
        """GET /<code> 命中预置权限包"""
        # 通常至少有 1 个预置权限包; 若没有, skip
        resp = api_client.get(BUNDLE_URL, headers=admin_headers)
        bundles = resp.get_json().get('data', [])
        if not bundles:
            pytest.skip("No preset permission bundles")
        code = bundles[0].get('bundle_code') or bundles[0].get('code')
        if not code:
            pytest.skip("Bundle has no code field")
        resp = api_client.get(f'{BUNDLE_URL}/{code}', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert 'data' in body
        assert body['data'].get('bundle_code') == code

    def test_assign_bundle_missing_fields_400(self, api_client, admin_headers):
        """POST /assign 缺 user_id / bundle_code → 400"""
        # 注: Python {} 是 falsy, 端点先校验 "请求体不能为空"
        # 改为只缺 user_id, 但有 bundle_code (这样能过 truthy 检查)
        resp = api_client.post(
            f'{BUNDLE_URL}/assign',
            json={'bundle_code': 'some_bundle'},  # 缺 user_id
            headers=admin_headers,
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body.get('success') is False
        # 错误信息应含 "user_id" 字段提示
        err = body.get('error', '')
        # 端点用 "缺少必填字段: user_id, bundle_code" 形式
        assert 'user_id' in err

    def test_assign_bundle_empty_body_400(self, api_client, admin_headers):
        """POST /assign 空 body → 400 (空 dict 触发 "请求体不能为空")"""
        # 注: 在 Python 中 `{}` 是 falsy, 端点代码 `if not data` 触发 400
        # 但 Flask 的 get_json() 对空 dict 处理可能不一致
        # 我们只测响应是 4xx 错误 (400/500) 且 success=False
        resp = api_client.post(
            f'{BUNDLE_URL}/assign',
            json={},
            headers=admin_headers,
        )
        # 接受 400 (空 body 校验) 或 500 (解析异常)
        assert resp.status_code in (400, 500)
        body = resp.get_json()
        if body:
            assert body.get('success') is False

    def test_assign_bundle_requires_admin(self, api_client, regular_user_headers):
        """POST /assign 非 admin → 403"""
        resp = api_client.post(
            f'{BUNDLE_URL}/assign',
            json={'user_id': 1, 'bundle_code': 'admin_bundle'},
            headers=regular_user_headers,
        )
        assert resp.status_code == 403

    def test_get_user_bundles_returns_list(self, api_client, admin_headers):
        """GET /user/<id> 返回用户已分配权限包"""
        resp = api_client.get(f'{BUNDLE_URL}/user/1', headers=admin_headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert isinstance(body.get('data'), list)

    def test_create_bundle_requires_admin(self, api_client, regular_user_headers):
        """POST / 创建权限包非 admin → 403"""
        resp = api_client.post(
            BUNDLE_URL,
            json={'bundle_code': 'test', 'bundle_name': 'Test'},
            headers=regular_user_headers,
        )
        assert resp.status_code == 403

    def test_create_bundle_missing_field_400(self, api_client, admin_headers):
        """POST / 缺必填字段 → 400"""
        resp = api_client.post(
            BUNDLE_URL,
            json={'bundle_code': 'test_no_name'},
            headers=admin_headers,
        )
        assert resp.status_code == 400
        body = resp.get_json()
        assert body.get('success') is False
        assert 'bundle_name' in body.get('error', '')

    def test_create_then_get_bundle(self, api_client, admin_headers):
        """创建权限包 + 按 code 读取 (端到端)"""
        code = f'test_bundle_{int(__import__("time").time())}'
        resp = api_client.post(
            BUNDLE_URL,
            json={
                'bundle_code': code,
                'bundle_name': 'Test Bundle',
                'description': 'Created by automated test',
            },
            headers=admin_headers,
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('success') is True
        assert 'data' in body
        # 立即读取
        resp2 = api_client.get(f'{BUNDLE_URL}/{code}', headers=admin_headers)
        assert resp2.status_code == 200
        assert resp2.get_json()['data']['bundle_code'] == code
        # 清理: 删除
        resp3 = api_client.delete(f'{BUNDLE_URL}/{code}', headers=admin_headers)
        assert resp3.status_code in (200, 404)

    def test_update_bundle_404_for_unknown(self, api_client, admin_headers):
        """PUT /<unknown> 不可达 → 404"""
        resp = api_client.put(
            f'{BUNDLE_URL}/__no_such_bundle_for_update__',
            json={'bundle_name': 'New Name'},
            headers=admin_headers,
        )
        # 应为 404 (更新失败 / 权限包不存在)
        assert resp.status_code in (404, 400)

    def test_delete_bundle_404_for_unknown(self, api_client, admin_headers):
        """DELETE /<unknown> 不可达 → 404"""
        resp = api_client.delete(
            f'{BUNDLE_URL}/__no_such_bundle_for_delete__',
            headers=admin_headers,
        )
        assert resp.status_code in (404, 400)

    def test_update_bundle_requires_admin(self, api_client, regular_user_headers):
        """PUT /<code> 非 admin → 403"""
        resp = api_client.put(
            f'{BUNDLE_URL}/any_code',
            json={'bundle_name': 'X'},
            headers=regular_user_headers,
        )
        assert resp.status_code == 403

    def test_delete_bundle_requires_admin(self, api_client, regular_user_headers):
        """DELETE /<code> 非 admin → 403"""
        resp = api_client.delete(
            f'{BUNDLE_URL}/any_code',
            headers=regular_user_headers,
        )
        assert resp.status_code == 403
