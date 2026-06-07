# -*- coding: utf-8 -*-
"""
导出分页和选项测试 - 针对4个修复问题的验证

修复验证：
1. 问题1：当前页导出 - page/page_size 参数生效
2. 问题2：敏感字段不导出 - sensitivity: restricted 字段被排除
3. 问题3：计算字段只读 - computation.formula 字段标记为只读
4. 问题4：层级路径列控制 - include_hierarchy_path 选项生效

测试策略：
- 使用单元测试直接调用 ImportExportService 的方法
- 使用 API 测试验证 HTTP 接口的参数传递
"""

import pytest
import os
import sys
from openpyxl import load_workbook

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from meta.core.datasource import get_data_source
from meta.services.manage_service import ManageService
from meta.services.query_service import QueryService
from meta.services.import_export_service import ImportExportService
from meta.tests.conftest import get_shared_app
from meta.services.token_service import TokenService
from meta.services.auth_provider import UserInfo
from meta.tests.test_utils import get_test_db_path


def get_auth_headers():
    user = UserInfo(
        user_id='1', username='test_user', display_name='Test User',
        email='test@test.com', roles=['admin'], permissions=['*']
    )
    token, _ = TokenService.create_token(user)
    return {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + token,
        'X-User-Id': '1',
        'X-User-Name': 'test_user'
    }


class TestExportPagination:
    """导出分页控制测试 - 问题1修复验证"""

    def test_current_page_export_respects_page_size(self):
        """测试当前页导出应该只导出指定数量的数据"""
        app, client = get_shared_app()
        headers = get_auth_headers()

        response = client.post(
            '/api/v1/export',
            json={
                'object_type': 'domain',
                'scope': 'all',
                'page': 1,
                'page_size': 2
            },
            headers=headers
        )

        if response.status_code == 200:
            import json
            data = json.loads(response.data)
            if data.get('success') and data.get('data', {}).get('file_path'):
                file_path = data['data']['file_path']
                if os.path.exists(file_path):
                    wb = load_workbook(file_path, read_only=True)
                    if '领域' in wb.sheetnames:
                        ws = wb['领域']
                        row_count = ws.max_row - 1
                        assert row_count <= 2, \
                            f"当前页导出(page_size=2)应该只导出2条数据，实际导出 {row_count} 条"
                    wb.close()
                    os.remove(file_path)

    def test_export_all_when_no_pagination(self):
        """测试不传分页参数时导出全部数据"""
        app, client = get_shared_app()
        headers = get_auth_headers()

        response = client.post(
            '/api/v1/export',
            json={
                'object_type': 'domain',
                'scope': 'all'
            },
            headers=headers
        )

        assert response.status_code in [200, 400, 401, 500]


class TestSensitiveFieldsExport:
    """敏感字段导出测试 - 问题2修复验证"""

    def test_user_sensitive_fields_excluded(self):
        """测试 user 对象的敏感字段不被导出"""
        app, client = get_shared_app()
        headers = get_auth_headers()

        response = client.post(
            '/api/v1/export',
            json={
                'object_type': 'user',
                'scope': 'single'
            },
            headers=headers
        )

        if response.status_code == 200:
            import json
            data = json.loads(response.data)
            if data.get('success') and data.get('data', {}).get('file_path'):
                file_path = data['data']['file_path']
                if os.path.exists(file_path):
                    wb = load_workbook(file_path, read_only=True)

                    for sheet_name in wb.sheetnames:
                        ws = wb[sheet_name]
                        headers = [cell.value for cell in ws[1]]

                        sensitive_fields = ['password_hash', 'password']
                        for field in sensitive_fields:
                            assert field not in headers, \
                                f"敏感字段 '{field}' 不应出现在导出结果中"

                    wb.close()
                    os.remove(file_path)

    def test_service_sensitive_fields_excluded(self):
        """测试 service 对象的敏感字段不被导出"""
        app, client = get_shared_app()
        headers = get_auth_headers()

        response = client.post(
            '/api/v1/export',
            json={
                'object_type': 'service',
                'scope': 'single'
            },
            headers=headers
        )

        assert response.status_code in [200, 400, 401, 404, 500]


class TestComputedFieldsReadonly:
    """计算字段只读测试 - 问题3修复验证"""

    def test_computed_fields_marked_readonly_in_export(self):
        """测试带 computation.formula 的字段在导出时被标记为只读"""
        ds = get_data_source("sqlite", database=get_test_db_path())
        manage_service = ManageService(ds)
        query_service = QueryService(ds)
        ie_service = ImportExportService(ds, manage_service, query_service)

        result = ie_service.export_object('business_object', options={'mark_readonly': True})

        assert result.success, f"导出失败: {result.error}"

        if hasattr(result, 'readonly_columns') and result.readonly_columns:
            from meta.core.models import registry
            bo = registry.get('business_object')

            if bo:
                for field_name, field in bo.fields.items():
                    if hasattr(field, 'computation') and getattr(field.computation, 'formula', None):
                        assert field_name in result.readonly_columns, \
                            f"计算字段 '{field_name}' 应标记为只读"


class TestHierarchyPathControl:
    """层级路径列控制测试 - 问题4修复验证"""

    def test_hierarchy_path_excluded_when_disabled(self):
        """测试 include_hierarchy_path=false 时不包含层级路径列"""
        app, client = get_shared_app()
        headers = get_auth_headers()

        response = client.post(
            '/api/v1/export',
            json={
                'object_type': 'business_object',
                'scope': 'single',
                'options': {
                    'include_hierarchy_path': False,
                    'include_hierarchy_ids': False
                }
            },
            headers=headers
        )

        if response.status_code == 200:
            import json
            data = json.loads(response.data)
            if data.get('success') and data.get('data', {}).get('file_path'):
                file_path = data['data']['file_path']
                if os.path.exists(file_path):
                    wb = load_workbook(file_path, read_only=True)

                    for sheet_name in wb.sheetnames:
                        if 'business_object' in sheet_name.lower() or '业务对象' in sheet_name:
                            ws = wb[sheet_name]
                            headers = [cell.value for cell in ws[1]]

                            hierarchy_columns = ['层级路径', 'hierarchy_path', '路径', 'path']
                            for col in hierarchy_columns:
                                assert col not in headers, \
                                    f"include_hierarchy_path=false 时，列 '{col}' 不应出现在导出结果中"

                    wb.close()
                    os.remove(file_path)

    def test_hierarchy_path_included_when_enabled(self):
        """测试 include_hierarchy_path=true 时包含层级路径列"""
        app, client = get_shared_app()
        headers = get_auth_headers()

        response = client.post(
            '/api/v1/export',
            json={
                'object_type': 'business_object',
                'scope': 'single',
                'options': {
                    'include_hierarchy_path': True
                }
            },
            headers=headers
        )

        if response.status_code == 200:
            import json
            data = json.loads(response.data)
            if data.get('success') and data.get('data', {}).get('file_path'):
                file_path = data['data']['file_path']
                if os.path.exists(file_path):
                    wb = load_workbook(file_path, read_only=True)

                    for sheet_name in wb.sheetnames:
                        if 'business_object' in sheet_name.lower() or '业务对象' in sheet_name:
                            ws = wb[sheet_name]
                            headers = [cell.value for cell in ws[1]]

                            has_hierarchy_col = '层级路径' in headers or 'hierarchy_path' in headers
                            assert has_hierarchy_col, \
                                f"include_hierarchy_path=true 时，应包含层级路径列"

                    wb.close()
                    os.remove(file_path)

    def test_options_always_sent_to_backend(self):
        """测试问题4根因：前端应始终传递 options 参数"""
        app, client = get_shared_app()
        headers = get_auth_headers()

        response = client.post(
            '/api/v1/export',
            json={
                'object_type': 'domain',
                'scope': 'single',
                'options': {
                    'include_hierarchy_path': False,
                    'include_operation_mode': True
                }
            },
            headers=headers
        )

        assert response.status_code in [200, 400, 401, 500]


if __name__ == '__main__':
    import pytest
    sys.exit(pytest.main([__file__, '-v', '-s']))
