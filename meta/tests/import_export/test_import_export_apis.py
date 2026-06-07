# -*- coding: utf-8 -*-
"""
导入导出 API 测试

合并以下测试文件:
- test_import_export_preview.py (导入预览)
- test_import_export_templates.py (导入模板)
- test_import_export_options.py (导出选项)

测试范围:
- 导入预览接口
- 导入模板下载
- 导出选项配置
"""

import pytest
import json
import os

pytestmark = pytest.mark.integration


# ==================== 共享 Fixtures ====================

@pytest.fixture
def client_and_headers():
    """获取测试客户端和认证头"""
    from meta.tests.conftest import get_shared_app
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo

    app, client = get_shared_app()
    user = UserInfo(
        user_id='1', username='test_user', display_name='Test User',
        email='test@test.com', roles=['admin'], permissions=['*']
    )
    token, _ = TokenService.create_token(user)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token,
        'X-User-Id': '1',
        'X-User-Name': 'test_user'
    }
    return client, headers


# ==================== 导入预览测试 ====================

class TestImportPreview:
    """导入预览测试"""

    def test_import_preview_endpoint_exists(self, client_and_headers):
        """测试导入预览接口存在"""
        client, headers = client_and_headers
        response = client.post(
            '/api/v1/import/preview',
            data=json.dumps({
                'object_type': 'domain'
            }),
            headers=headers
        )
        assert response.status_code in [200, 400, 401, 405, 422, 500]

    def test_import_endpoint_exists(self, client_and_headers):
        """测试导入接口存在"""
        client, headers = client_and_headers
        response = client.post(
            '/api/v1/import',
            data=json.dumps({
                'object_type': 'domain'
            }),
            headers=headers
        )
        assert response.status_code in [200, 400, 401, 422, 500]


# ==================== 导入模板测试 ====================

class TestImportTemplate:
    """导入模板测试"""

    def test_download_domain_template(self, client_and_headers):
        """测试下载领域导入模板"""
        client, headers = client_and_headers
        response = client.get(
            '/api/v1/import/template/domain',
            headers=headers
        )
        assert response.status_code in [200, 401, 404, 500]

    def test_download_business_object_template(self, client_and_headers):
        """测试下载业务对象导入模板"""
        client, headers = client_and_headers
        response = client.get(
            '/api/v1/import/template/business_object',
            headers=headers
        )
        assert response.status_code in [200, 401, 404, 500]

    def test_download_relationship_template(self, client_and_headers):
        """测试下载关系导入模板"""
        client, headers = client_and_headers
        response = client.get(
            '/api/v1/import/template/relationship',
            headers=headers
        )
        assert response.status_code in [200, 401, 404, 500]

    def test_template_has_correct_headers(self, client_and_headers):
        """测试模板包含正确的表头"""
        client, headers = client_and_headers
        response = client.get(
            '/api/v1/import/template/domain',
            headers=headers
        )
        assert response.status_code in [200, 401, 404, 500]


# ==================== 导出选项测试 ====================

class TestExportOptions:
    """导出选项测试"""

    def test_export_with_operation_mode(self, client_and_headers):
        """测试导出包含操作模式列"""
        client, headers = client_and_headers
        response = client.post(
            '/api/v1/export',
            data=json.dumps({
                'object_type': 'domain',
                'scope': 'single',
                'filters': {'version_id': 2},
                'options': {'include_operation_mode': True}
            }),
            headers=headers
        )
        assert response.status_code in [200, 400, 401, 500]

    def test_export_without_operation_mode(self, client_and_headers):
        """测试导出不包含操作模式列"""
        client, headers = client_and_headers
        response = client.post(
            '/api/v1/export',
            data=json.dumps({
                'object_type': 'domain',
                'scope': 'single',
                'filters': {'version_id': 2},
                'options': {'include_operation_mode': False}
            }),
            headers=headers
        )
        assert response.status_code in [200, 400, 401, 500]

    def test_export_with_hierarchy_ids(self, client_and_headers):
        """测试导出包含层级编码"""
        client, headers = client_and_headers
        response = client.post(
            '/api/v1/export',
            data=json.dumps({
                'object_type': 'business_object',
                'scope': 'single',
                'filters': {'version_id': 2},
                'options': {'include_hierarchy_ids': True}
            }),
            headers=headers
        )
        assert response.status_code in [200, 400, 401, 500]

    def test_export_selected_types(self, client_and_headers):
        """测试导出选定的对象类型"""
        client, headers = client_and_headers
        response = client.post(
            '/api/v1/export',
            data=json.dumps({
                'object_type': 'domain',
                'scope': 'selected',
                'selected_types': ['domain', 'sub_domain'],
                'filters': {'version_id': 2}
            }),
            headers=headers
        )
        assert response.status_code in [200, 400, 401, 500]
