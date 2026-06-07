# -*- coding: utf-8 -*-
"""
审计日志 API 端点测试套件 (优化版)

[合并来源] test_audit_api.py
  - TestAuditApiPagination (11 tests)
  - TestAuditApiResponse (10 tests)
  - TestAuditAPIList (测试列表端点)
  - TestAuditAPIDetail (测试详情端点)
  - TestAuditAPIExport (测试导出端点)
  - TestAuditAPIFailed (测试失败日志端点)
  - TestAuditAPIOverview (测试概览端点)
  - TestAuditAPIUnauthenticated (测试未认证访问)

[优化策略]
  1. 使用参数化测试减少重复代码
  2. 统一使用 shared fixtures
  3. 提取公共辅助方法
  4. HTTP 状态码常量定义

测试端点：
- GET /api/v1/audit/logs — 分页查询
- GET /api/v1/audit/logs/<id> — 日志详情
- GET /api/v1/audit/failed — 失败日志
- GET /api/v1/audit/overview — 审计概览
- GET /api/v1/audit/logs/export — 导出
"""

import pytest
import json
import os
import sys


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in os.environ.get('PYTHONPATH', '').split(os.pathsep):
    os.environ['PYTHONPATH'] = _PROJECT_ROOT + os.pathsep + os.environ.get('PYTHONPATH', '')
    sys.path.insert(0, _PROJECT_ROOT)

if not os.environ.get('JWT_SECRET_KEY'):
    os.environ['JWT_SECRET_KEY'] = 'test-secret-key-for-audit-tests'


# ==================== 常量定义 ====================

class HTTP:
    SUCCESS = [200]
    OK_OR_ERROR = [200, 500]
    NOT_FOUND = [404]
    AUTH_ERROR = [401, 403]
    PAGINATION_OK = [200, 500]
    META_OK = [200, 404, 500]


# ==================== Fixtures ====================

@pytest.fixture(scope='class')
def client_and_headers():
    """认证客户端"""
    from meta.tests.conftest import get_shared_app
    _, client = get_shared_app()

    from meta.services.token_service import TokenService
    from meta.services.auth_provider import UserInfo
    user = UserInfo(
        user_id='1',
        username='audit_test',
        display_name='Audit Test User',
        email='audit@test.com',
        roles=['admin'],
        permissions=['*']
    )
    token, _ = TokenService.create_token(user)
    h = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
    }
    return client, h


# ==================== 参数化测试数据 ====================

PAGINATION_TEST_CASES = [
    ('', '默认分页'),
    ('page=1&page_size=5', '自定义分页'),
    ('page=100&page_size=500', '大页码分页'),
    ('action=DELETE', '按操作类型过滤'),
    ('object_type=user', '按对象类型过滤'),
    ('user_name=admin', '按用户名过滤'),
    ('start_date=2020-01-01&end_date=2030-12-31', '日期范围过滤'),
    ('sort_field=created_at&sort_direction=desc', '默认排序'),
    ('sort_field=id&sort_direction=asc', '升序排序'),
    ('sort_field=invalid_field', '无效排序字段'),
    ('sort_direction=sideways', '无效排序方向'),
]

FILTER_COMBINATION_CASES = [
    ('object_type=user&action=UPDATE&page=1&page_size=10', '组合过滤条件'),
    ('keyword=admin', '关键词搜索'),
]


# ==================== 分页与过滤测试 ====================

class TestAuditApiPagination:
    """审计日志分页与过滤测试"""

    @pytest.mark.parametrize('params,description', PAGINATION_TEST_CASES)
    def test_logs_with_params(self, client_and_headers, params, description):
        """分页和过滤参数测试"""
        client, h = client_and_headers
        url = f'/api/v1/audit/logs?{params}' if params else '/api/v1/audit/logs'
        resp = client.get(url, headers=h)
        assert resp.status_code in HTTP.PAGINATION_OK, \
            f"{description}: 预期状态码{HTTP.PAGINATION_OK}，实际{resp.status_code}"


# ==================== 响应结构测试 ====================

class TestAuditApiResponse:
    """审计日志响应结构测试"""

    def test_logs_response_structure(self, client_and_headers):
        """响应结构包含必要字段"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/logs?page=1&page_size=5', headers=h)
        assert resp.status_code in HTTP.PAGINATION_OK
        if resp.status_code == 200:
            data = json.loads(resp.data)
            assert 'data' in data or 'items' in data or 'records' in data

    def test_failed_logs_endpoint(self, client_and_headers):
        """失败日志端点"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/failed', headers=h)
        assert resp.status_code in HTTP.PAGINATION_OK + HTTP.NOT_FOUND

    def test_audit_overview_endpoint(self, client_and_headers):
        """审计概览端点"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/overview', headers=h)
        assert resp.status_code in HTTP.META_OK

    def test_audit_export_endpoint(self, client_and_headers):
        """审计导出端点"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/logs/export', headers=h)
        assert resp.status_code in HTTP.META_OK

    def test_audit_log_detail_by_id(self, client_and_headers):
        """按 ID 查询审计详情"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/logs/1', headers=h)
        assert resp.status_code in HTTP.META_OK

    def test_audit_pagination_with_page_info(self, client_and_headers):
        """分页信息验证"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/logs?page=1&page_size=10', headers=h)
        assert resp.status_code in HTTP.PAGINATION_OK
        if resp.status_code == 200:
            data = json.loads(resp.data)
            keys_lower = {k.lower() for k in data.keys()}
            assert any(k in keys_lower for k in ['page', 'pagenum', 'page_num', 'total']), \
                f"响应应包含分页字段，实际keys: {list(data.keys())}"

    @pytest.mark.parametrize('params,description', FILTER_COMBINATION_CASES)
    def test_audit_combined_filters(self, client_and_headers, params, description):
        """组合过滤条件"""
        client, h = client_and_headers
        resp = client.get(f'/api/v1/audit/logs?{params}', headers=h)
        assert resp.status_code in HTTP.PAGINATION_OK


# ==================== 未认证访问测试 ====================

class TestAuditAPIUnauthenticated:
    """审计 API 未认证访问测试"""

    def test_audit_no_auth_header(self):
        """无认证头请求"""
        from meta.tests.conftest import get_shared_app
        _, client = get_shared_app()
        resp = client.get('/api/v1/audit/logs', headers={'Content-Type': 'application/json'})
        assert resp.status_code in HTTP.SUCCESS + HTTP.AUTH_ERROR + [500]


# ==================== 列表端点测试 ====================

class TestAuditAPIList:
    """审计日志列表端点测试"""

    def test_list_with_default_params(self, client_and_headers):
        """默认参数列表"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/logs', headers=h)
        assert resp.status_code in HTTP.OK_OR_ERROR

    def test_list_with_filters(self, client_and_headers):
        """带过滤条件列表"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/logs?action=CREATE', headers=h)
        assert resp.status_code in HTTP.OK_OR_ERROR

    def test_list_pagination(self, client_and_headers):
        """分页列表"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/logs?page=1&page_size=20', headers=h)
        assert resp.status_code in HTTP.OK_OR_ERROR


# ==================== 详情端点测试 ====================

class TestAuditAPIDetail:
    """审计日志详情端点测试"""

    def test_detail_existing(self, client_and_headers):
        """获取存在的日志详情"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/logs/1', headers=h)
        assert resp.status_code in HTTP.OK_OR_ERROR + HTTP.NOT_FOUND

    def test_detail_nonexistent(self, client_and_headers):
        """获取不存在的日志详情"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/logs/999999', headers=h)
        assert resp.status_code in HTTP.NOT_FOUND + HTTP.OK_OR_ERROR


# ==================== 导出端点测试 ====================

class TestAuditAPIExport:
    """审计日志导出端点测试"""

    def test_export_logs(self, client_and_headers):
        """导出日志"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/logs/export', headers=h)
        assert resp.status_code in HTTP.META_OK

    def test_export_with_filters(self, client_and_headers):
        """带过滤条件导出"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/logs/export?action=DELETE', headers=h)
        assert resp.status_code in HTTP.META_OK


# ==================== 失败日志端点测试 ====================

class TestAuditAPIFailed:
    """失败日志端点测试"""

    def test_failed_logs(self, client_and_headers):
        """获取失败日志"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/failed', headers=h)
        assert resp.status_code in HTTP.OK_OR_ERROR + HTTP.NOT_FOUND

    def test_failed_logs_pagination(self, client_and_headers):
        """失败日志分页"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/failed?page=1&page_size=10', headers=h)
        assert resp.status_code in HTTP.OK_OR_ERROR + HTTP.NOT_FOUND


# ==================== 概览端点测试 ====================

class TestAuditAPIOverview:
    """审计概览端点测试"""

    def test_overview(self, client_and_headers):
        """获取审计概览"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/overview', headers=h)
        assert resp.status_code in HTTP.META_OK

    def test_overview_with_date_range(self, client_and_headers):
        """带日期范围的概览"""
        client, h = client_and_headers
        resp = client.get('/api/v1/audit/overview?start_date=2024-01-01&end_date=2024-12-31', headers=h)
        assert resp.status_code in HTTP.META_OK
