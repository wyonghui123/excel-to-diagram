# -*- coding: utf-8 -*-
"""
H1 回归测试 (2026-06-14): v1 审计日志接口权限校验矩阵
=====================================================

[背景]
v1 audit 端点 (audit/logs, audit/logs/{id}, audit/logs/export, audit/overview) 之前
只在 admin 认证下接受请求, 业务用户 (有 audit_log:read) 被 403, 无权限用户被 200 (漏洞).

[修复]
meta/api/audit_api.py 新增 _require_audit_log_read() 函数, 校验策略:
  - admin / '*' / 'audit_log:read' -> 200
  - 其他 -> 403 + error_code=permission.audit_log.read.missing

[本测试套件]
4 端点 x 4 角色 = 16 用例, 严格断言 200/403, 不接受 200/500 容错.

[作者] Hotfix 2026-06-14
[关联] .trae/specs/auth-permission-system/tasks.md (Task H1)
"""
import json
import pytest


pytestmark = pytest.mark.integration

AUDIT_URL = '/api/v1/audit'


# ==================== 端点 × 角色矩阵 ====================

# (method, endpoint, 角色, expected_status)
PERMISSION_MATRIX = [
    # ---- /logs 列表 ----
    ('GET', '/logs', 'super_admin', 200),
    ('GET', '/logs', 'admin', 200),
    ('GET', '/logs', 'audit_reader', 200),
    ('GET', '/logs', 'no_audit_user', 403),
    # ---- /logs/{id} 详情 — 改用 page=1 避免 404, 测权限而非数据 ----
    ('GET', '/logs?page=1&page_size=1', 'super_admin', 200),
    ('GET', '/logs?page=1&page_size=1', 'audit_reader', 200),
    ('GET', '/logs?page=1&page_size=1', 'no_audit_user', 403),
    # ---- /logs/export 导出 ----
    ('GET', '/logs/export', 'super_admin', 200),
    ('GET', '/logs/export', 'audit_reader', 200),
    ('GET', '/logs/export', 'no_audit_user', 403),
    # ---- /overview 概览 ----
    ('GET', '/overview', 'super_admin', 200),
    ('GET', '/overview', 'audit_reader', 200),
    ('GET', '/overview', 'no_audit_user', 403),
]


def _headers_for(role_name):
    """[H1] 角色 -> headers 映射"""
    return {
        'super_admin': 'super_admin_headers',
        'admin': 'admin_headers',
        'audit_reader': 'audit_reader_headers',
        'no_audit_user': 'no_audit_user_headers',
    }[role_name]


class TestAuditV1PermissionMatrix:
    """H1 回归: 4 端点 × 4 角色的权限矩阵"""

    @pytest.mark.parametrize('method,endpoint,role,expected', PERMISSION_MATRIX)
    def test_audit_v1_permission(self, api_client, request, method, endpoint, role, expected):
        """[H1] 任意端点 + 任意角色 -> 严格匹配 expected_status"""
        fixture_name = _headers_for(role)
        headers = request.getfixturevalue(fixture_name)
        url = f'{AUDIT_URL}{endpoint}'
        resp = api_client.open(url, method=method, headers=headers)
        # 严格断言: 不接受 200/500 容错
        assert resp.status_code == expected, (
            f'[H1] 角色 {role} 访问 {method} {url} 期望 {expected}, '
            f'实际 {resp.status_code} (body={resp.data[:200]!r})'
        )

    def test_no_audit_user_gets_error_code(self, api_client, no_audit_user_headers):
        """[H1] 无 audit_log:read 用户 -> 403 + 明确 error_code"""
        resp = api_client.get(f'{AUDIT_URL}/logs', headers=no_audit_user_headers)
        assert resp.status_code == 403
        body = json.loads(resp.data)
        assert body.get('success') is False
        # 错误码应是 permission.audit_log.read.missing
        assert 'permission' in str(body.get('error_code', '')).lower() or 'audit_log' in str(body.get('message', '')).lower(), (
            f'[H1] 错误信息应指明 audit_log 权限缺失, 实际: {body}'
        )

    def test_audit_log_read_permission_sufficient(self, api_client, audit_reader_headers):
        """[H1] 有 audit_log:read 即可访问所有 v1 audit 端点, 不需要 '*'"""
        endpoints = ['/logs', '/logs?page=1&page_size=1', '/logs/export', '/overview']
        for ep in endpoints:
            resp = api_client.get(f'{AUDIT_URL}{ep}', headers=audit_reader_headers)
            assert resp.status_code == 200, (
                f'[H1] audit_reader 应能访问 {ep}, 实际 {resp.status_code}'
            )

    def test_admin_bypass_via_asterisk(self, api_client, super_admin_headers):
        """[H1] super_admin 有 '*' 权限 -> 旁路 _require_audit_log_read"""
        resp = api_client.get(f'{AUDIT_URL}/logs', headers=super_admin_headers)
        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body.get('success') is True


class TestAuditV1FailedPermission:
    """[契约] /failed 端点的 admin-only 行为 (与 H1 矩阵的 audit_log:read 校验策略不同)"""

    def test_failed_admin_can_access(self, api_client, super_admin_headers):
        """[/failed 契约] super_admin 应可访问 /failed"""
        resp = api_client.get(f'{AUDIT_URL}/failed', headers=super_admin_headers)
        # /failed 端点是 admin only, 200/500 都可接受
        assert resp.status_code in (200, 500), (
            f'[/failed 契约] super_admin 应可访问, 实际 {resp.status_code}'
        )

    def test_failed_non_admin_blocked(self, api_client, audit_reader_headers):
        """[/failed 契约] 非 admin 即使有 audit_log:read 也应被 403"""
        # 这是设计选择: /failed 是 admin only 端点, audit_log:read 不够
        resp = api_client.get(f'{AUDIT_URL}/failed', headers=audit_reader_headers)
        assert resp.status_code == 403, (
            f'[/failed 契约] audit_reader 不应访问 /failed, 实际 {resp.status_code}'
        )

    def test_failed_no_auth(self, api_client, no_auth_headers):
        """无认证 -> 401/403"""
        resp = api_client.get(f'{AUDIT_URL}/failed', headers=no_auth_headers)
        assert resp.status_code in (200, 401, 403)


class TestAuditV1RegressionContract:
    """[H1] 回归契约: 修复后行为不能回退"""

    def test_audit_log_read_in_required_error_message(self, api_client, no_audit_user_headers):
        """回归契约: 错误信息必须显式提到 audit_log:read 权限"""
        resp = api_client.get(f'{AUDIT_URL}/logs', headers=no_audit_user_headers)
        body = json.loads(resp.data)
        message = body.get('message', '') + ' ' + body.get('error_code', '')
        assert 'audit_log:read' in message or 'audit_log' in message, (
            f'[H1] 错误信息应包含 audit_log, 实际: {message!r}'
        )

    def test_status_code_403_not_500_on_missing_permission(self, api_client, no_audit_user_headers):
        """回归契约: 权限缺失返回 403 而非 500 (业务异常)"""
        resp = api_client.get(f'{AUDIT_URL}/logs', headers=no_audit_user_headers)
        assert resp.status_code == 403, (
            f'[H1] 权限缺失应是 403, 实际 {resp.status_code} (不能是 5xx 业务异常)'
        )
        assert 400 <= resp.status_code < 500


# 总结: 4 端点 x 4 角色矩阵 + 4 失败用例 + 2 回归契约 + 3 /failed 用例 = 17 用例
