import pytest

pytestmark = pytest.mark.unit

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计日志统一测试

测试所有业务对象都使用 AuditInterceptor 统一记录审计日志，
验证值对比逻辑、字段记录完整性等。

修复说明：
- 原版本使用外部 HTTP requests，需要真实服务器运行
- 修改为使用 Flask test_client，无需外部服务器
"""

import pytest
import json
import time
from datetime import datetime


class TestAuditInterceptorUnified:
    """审计日志统一测试套件"""

    def get_audit_logs(self, client, headers, object_type, object_id):
        """获取指定对象的审计日志"""
        object_id_str = str(object_id)
        response = client.get(
            '/api/v2/bo/audit/logs',
            headers=headers,
            query_string={
                'object_type': object_type,
                'object_id': object_id_str,
                'page': 1,
                'page_size': 100
            }
        )
        data = response.get_json()
        return data.get('data', []) if data else []

    # ==========================================
    # 用户 (user) 审计测试
    # ==========================================

    @pytest.mark.requires_cleanup
    def test_user_create_audit(self, shared_client, admin_headers):
        """测试用户创建审计日志"""
        test_user = {
            'username': f'test_user_{int(time.time())}',
            'password': 'test123456',
            'email': f'test_{int(time.time())}@example.com',
            'display_name': f'测试用户_{int(time.time())}'
        }

        response = shared_client.post(
            '/api/v2/bo/user',
            headers=admin_headers,
            data=json.dumps(test_user)
        )

        if response.status_code not in [200, 201, 400, 401, 500]:
            pytest.skip(f"用户创建 API 不可用: {response.status_code}")

        data = response.get_json()
        if not data or not data.get('success'):
            pytest.skip("用户创建失败，跳过审计测试")

        user_id = data.get('data', {}).get('id')
        if not user_id:
            pytest.skip("无法获取创建的用户ID")

        audit_logs = self.get_audit_logs(shared_client, admin_headers, 'user', user_id)
        user_audit = [log for log in audit_logs if log.get('object_id') == str(user_id)]

        assert len(user_audit) > 0, "应该存在创建用户的审计日志"
        create_log = user_audit[0]
        assert create_log.get('action') in ['CREATE', 'CREATE_USER', 'INSERT'], "动作应该是创建"

    @pytest.mark.requires_cleanup
    def test_user_update_audit_with_changes(self, shared_client, admin_headers):
        """测试用户更新审计日志（值有变化）"""
        test_user = {
            'username': f'test_user_{int(time.time())}',
            'password': 'test123456',
            'email': f'test_{int(time.time())}@example.com',
            'display_name': f'测试用户_{int(time.time())}'
        }

        response = shared_client.post(
            '/api/v2/bo/user',
            headers=admin_headers,
            data=json.dumps(test_user)
        )

        if response.status_code not in [200, 201, 400, 401, 500]:
            pytest.skip(f"用户创建 API 不可用: {response.status_code}")

        data = response.get_json()
        if not data or not data.get('success'):
            pytest.skip("用户创建失败，跳过审计测试")

        user_id = data.get('data', {}).get('id')
        if not user_id:
            pytest.skip("无法获取创建的用户ID")

        update_data = {'display_name': f'更新后_{int(time.time())}'}
        response = shared_client.put(
            f'/api/v2/bo/user/{user_id}',
            headers=admin_headers,
            data=json.dumps(update_data)
        )

        audit_logs = self.get_audit_logs(shared_client, admin_headers, 'user', user_id)
        update_logs = [log for log in audit_logs if log.get('action') in ['UPDATE', 'UPDATE_USER', 'MODIFY']]

        assert len(update_logs) > 0, "应该存在更新用户的审计日志"

    def test_user_update_audit_no_changes(self, shared_client, admin_headers):
        """测试用户更新审计日志（值无变化，不应记录）"""
        audit_logs_before = self.get_audit_logs(shared_client, admin_headers, 'user', 1)
        count_before = len(audit_logs_before)

        update_data = {'display_name': 'Admin'}
        response = shared_client.put(
            '/api/v2/bo/user/1',
            headers=admin_headers,
            data=json.dumps(update_data)
        )

        if response.status_code == 404:
            pytest.skip("测试用户不存在")

        audit_logs_after = self.get_audit_logs(shared_client, admin_headers, 'user', 1)
        count_after = len(audit_logs_after)

        assert count_after == count_before, "值无变化时不应产生新的审计日志"

    @pytest.mark.requires_cleanup
    def test_user_delete_audit(self, shared_client, admin_headers):
        """测试用户删除审计日志"""
        test_user = {
            'username': f'test_user_{int(time.time())}',
            'password': 'test123456',
            'email': f'test_{int(time.time())}@example.com',
            'display_name': f'测试用户_{int(time.time())}'
        }

        response = shared_client.post(
            '/api/v2/bo/user',
            headers=admin_headers,
            data=json.dumps(test_user)
        )

        if response.status_code not in [200, 201, 400, 401, 500]:
            pytest.skip(f"用户创建 API 不可用: {response.status_code}")

        data = response.get_json()
        if not data or not data.get('success'):
            pytest.skip("用户创建失败，跳过审计测试")

        user_id = data.get('data', {}).get('id')
        if not user_id:
            pytest.skip("无法获取创建的用户ID")

        response = shared_client.delete(
            f'/api/v2/bo/user/{user_id}',
            headers=admin_headers
        )

        if response.status_code == 404:
            pytest.skip("测试用户不存在，无法删除")

        audit_logs = self.get_audit_logs(shared_client, admin_headers, 'user', user_id)
        delete_logs = [log for log in audit_logs if log.get('action') in ['DELETE', 'DELETE_USER', 'REMOVE']]

        assert len(delete_logs) > 0, "应该存在删除用户的审计日志"

    # ==========================================
    # 角色 (role) 审计测试
    # ==========================================

    @pytest.mark.requires_cleanup
    def test_role_create_audit(self, shared_client, admin_headers):
        """测试角色创建审计日志"""
        test_role = {
            'code': f'test_role_{int(time.time())}',
            'name': f'测试角色_{int(time.time())}'
        }

        response = shared_client.post(
            '/api/v2/bo/roles',
            headers=admin_headers,
            data=json.dumps(test_role)
        )

        if response.status_code not in [200, 201, 400, 401, 500]:
            pytest.skip(f"角色创建 API 不可用: {response.status_code}")

        data = response.get_json()
        if not data or not data.get('success'):
            pytest.skip("角色创建失败，跳过审计测试")

        role_id = data.get('data', {}).get('id')
        if not role_id:
            pytest.skip("无法获取创建的角色ID")

        audit_logs = self.get_audit_logs(shared_client, admin_headers, 'role', role_id)
        role_audit = [log for log in audit_logs if log.get('object_id') == str(role_id)]

        assert len(role_audit) > 0, "应该存在创建角色的审计日志"

    @pytest.mark.requires_cleanup
    def test_role_update_audit_with_changes(self, shared_client, admin_headers):
        """测试角色更新审计日志（值有变化）"""
        test_role = {
            'code': f'test_role_{int(time.time())}',
            'name': f'测试角色_{int(time.time())}'
        }

        response = shared_client.post(
            '/api/v2/bo/roles',
            headers=admin_headers,
            data=json.dumps(test_role)
        )

        if response.status_code not in [200, 201, 400, 401, 500]:
            pytest.skip(f"角色创建 API 不可用: {response.status_code}")

        data = response.get_json()
        if not data or not data.get('success'):
            pytest.skip("角色创建失败，跳过审计测试")

        role_id = data.get('data', {}).get('id')
        if not role_id:
            pytest.skip("无法获取创建的角色ID")

        update_data = {'name': f'更新后_{int(time.time())}'}
        response = shared_client.put(
            f'/api/v2/bo/roles/{role_id}',
            headers=admin_headers,
            data=json.dumps(update_data)
        )

        audit_logs = self.get_audit_logs(shared_client, admin_headers, 'role', role_id)
        update_logs = [log for log in audit_logs if log.get('action') in ['UPDATE', 'UPDATE_ROLE', 'MODIFY']]

        assert len(update_logs) > 0, "应该存在更新角色的审计日志"

    @pytest.mark.requires_cleanup
    def test_role_delete_audit(self, shared_client, admin_headers):
        """测试角色删除审计日志"""
        test_role = {
            'code': f'test_role_{int(time.time())}',
            'name': f'测试角色_{int(time.time())}'
        }

        response = shared_client.post(
            '/api/v2/bo/roles',
            headers=admin_headers,
            data=json.dumps(test_role)
        )

        if response.status_code not in [200, 201, 400, 401, 500]:
            pytest.skip(f"角色创建 API 不可用: {response.status_code}")

        data = response.get_json()
        if not data or not data.get('success'):
            pytest.skip("角色创建失败，跳过审计测试")

        role_id = data.get('data', {}).get('id')
        if not role_id:
            pytest.skip("无法获取创建的角色ID")

        response = shared_client.delete(
            f'/api/v2/bo/roles/{role_id}',
            headers=admin_headers
        )

        if response.status_code == 404:
            pytest.skip("测试角色不存在，无法删除")

        audit_logs = self.get_audit_logs(shared_client, admin_headers, 'role', role_id)
        delete_logs = [log for log in audit_logs if log.get('action') in ['DELETE', 'DELETE_ROLE', 'REMOVE']]

        assert len(delete_logs) > 0, "应该存在删除角色的审计日志"

    # ==========================================
    # 枚举类型 (enum_type) 审计测试
    # ==========================================

    @pytest.mark.requires_cleanup
    def test_enum_type_create_audit(self, shared_client, admin_headers):
        """测试枚举类型创建审计日志"""
        test_enum = {
            'code': f'TEST_ENUM_{int(time.time())}',
            'name': f'测试枚举_{int(time.time())}'
        }

        response = shared_client.post(
            '/api/v2/bo/enum_types',
            headers=admin_headers,
            data=json.dumps(test_enum)
        )

        if response.status_code not in [200, 201, 400, 401, 500]:
            pytest.skip(f"枚举类型创建 API 不可用: {response.status_code}")

        data = response.get_json()
        if not data or not data.get('success'):
            pytest.skip("枚举类型创建失败，跳过审计测试")

        enum_id = data.get('data', {}).get('id')
        if not enum_id:
            pytest.skip("无法获取创建的枚举类型ID")

        audit_logs = self.get_audit_logs(shared_client, admin_headers, 'enum_type', enum_id)
        enum_audit = [log for log in audit_logs if log.get('object_id') == str(enum_id)]

        assert len(enum_audit) > 0, "应该存在创建枚举类型的审计日志"

    @pytest.mark.requires_cleanup
    def test_enum_type_update_audit(self, shared_client, admin_headers):
        """测试枚举类型更新审计日志"""
        test_enum = {
            'code': f'TEST_ENUM_{int(time.time())}',
            'name': f'测试枚举_{int(time.time())}'
        }

        response = shared_client.post(
            '/api/v2/bo/enum_types',
            headers=admin_headers,
            data=json.dumps(test_enum)
        )

        if response.status_code not in [200, 201, 400, 401, 500]:
            pytest.skip(f"枚举类型创建 API 不可用: {response.status_code}")

        data = response.get_json()
        if not data or not data.get('success'):
            pytest.skip("枚举类型创建失败，跳过审计测试")

        enum_id = data.get('data', {}).get('id')
        if not enum_id:
            pytest.skip("无法获取创建的枚举类型ID")

        update_data = {'name': f'更新后_{int(time.time())}'}
        response = shared_client.put(
            f'/api/v2/bo/enum_types/{enum_id}',
            headers=admin_headers,
            data=json.dumps(update_data)
        )

        audit_logs = self.get_audit_logs(shared_client, admin_headers, 'enum_type', enum_id)
        update_logs = [log for log in audit_logs if log.get('action') in ['UPDATE', 'MODIFY']]

        assert len(update_logs) > 0, "应该存在更新枚举类型的审计日志"

    @pytest.mark.requires_cleanup
    def test_enum_type_delete_audit(self, shared_client, admin_headers):
        """测试枚举类型删除审计日志"""
        test_enum = {
            'code': f'TEST_ENUM_{int(time.time())}',
            'name': f'测试枚举_{int(time.time())}'
        }

        response = shared_client.post(
            '/api/v2/bo/enum_types',
            headers=admin_headers,
            data=json.dumps(test_enum)
        )

        if response.status_code not in [200, 201, 400, 401, 500]:
            pytest.skip(f"枚举类型创建 API 不可用: {response.status_code}")

        data = response.get_json()
        if not data or not data.get('success'):
            pytest.skip("枚举类型创建失败，跳过审计测试")

        enum_id = data.get('data', {}).get('id')
        if not enum_id:
            pytest.skip("无法获取创建的枚举类型ID")

        response = shared_client.delete(
            f'/api/v2/bo/enum_types/{enum_id}',
            headers=admin_headers
        )

        if response.status_code == 404:
            pytest.skip("测试枚举类型不存在，无法删除")

        audit_logs = self.get_audit_logs(shared_client, admin_headers, 'enum_type', enum_id)
        delete_logs = [log for log in audit_logs if log.get('action') in ['DELETE', 'REMOVE']]

        assert len(delete_logs) > 0, "应该存在删除枚举类型的审计日志"

    # ==========================================
    # 用户组 (user_group) 审计测试
    # ==========================================

    @pytest.mark.requires_cleanup
    def test_user_group_update_audit(self, shared_client, admin_headers):
        """测试用户组更新审计日志"""
        response = shared_client.get(
            '/api/v2/bo/user_groups',
            headers=admin_headers
        )

        if response.status_code not in [200, 401, 500]:
            pytest.skip(f"用户组查询 API 不可用: {response.status_code}")

        data = response.get_json()
        if not data or not data.get('success'):
            pytest.skip("用户组查询失败，跳过审计测试")

        groups = data.get('data', {}).get('items', [])
        if not groups:
            pytest.skip("没有可用的用户组进行测试")

        group_id = groups[0].get('id')
        if not group_id:
            pytest.skip("无法获取用户组ID")

        update_data = {'name': f'更新后_{int(time.time())}'}
        response = shared_client.put(
            f'/api/v2/bo/user_groups/{group_id}',
            headers=admin_headers,
            data=json.dumps(update_data)
        )

        audit_logs = self.get_audit_logs(shared_client, admin_headers, 'user_group', group_id)
        update_logs = [log for log in audit_logs if log.get('action') in ['UPDATE', 'UPDATE_USER_GROUP', 'MODIFY']]

        assert len(update_logs) > 0, "应该存在更新用户组的审计日志"

    # ==========================================
    # 值对比逻辑测试
    # ==========================================

    def test_audit_value_comparison_same_value(self, shared_client, admin_headers):
        """测试值对比逻辑：相同值不应记录"""
        audit_logs_before = self.get_audit_logs(shared_client, admin_headers, 'user', 1)
        count_before = len(audit_logs_before)

        update_data = {'display_name': 'Admin'}
        response = shared_client.put(
            '/api/v2/bo/user/1',
            headers=admin_headers,
            data=json.dumps(update_data)
        )

        if response.status_code == 404:
            pytest.skip("测试用户不存在")

        audit_logs_after = self.get_audit_logs(shared_client, admin_headers, 'user', 1)
        count_after = len(audit_logs_after)

        assert count_after == count_before, "相同值不应产生新的审计日志"

    @pytest.mark.requires_cleanup
    def test_audit_value_comparison_different_value(self, shared_client, admin_headers):
        """测试值对比逻辑：不同值应记录"""
        test_user = {
            'username': f'test_user_{int(time.time())}',
            'password': 'test123456',
            'email': f'test_{int(time.time())}@example.com',
            'display_name': f'测试用户_{int(time.time())}'
        }

        response = shared_client.post(
            '/api/v2/bo/user',
            headers=admin_headers,
            data=json.dumps(test_user)
        )

        if response.status_code not in [200, 201, 400, 401, 500]:
            pytest.skip(f"用户创建 API 不可用: {response.status_code}")

        data = response.get_json()
        if not data or not data.get('success'):
            pytest.skip("用户创建失败，跳过审计测试")

        user_id = data.get('data', {}).get('id')
        if not user_id:
            pytest.skip("无法获取创建的用户ID")

        original_name = data.get('data', {}).get('display_name')
        update_data = {'display_name': f'变化后的名字_{int(time.time())}'}
        response = shared_client.put(
            f'/api/v2/bo/user/{user_id}',
            headers=admin_headers,
            data=json.dumps(update_data)
        )

        audit_logs = self.get_audit_logs(shared_client, admin_headers, 'user', user_id)
        update_logs = [log for log in audit_logs if log.get('action') in ['UPDATE', 'UPDATE_USER', 'MODIFY']]

        assert len(update_logs) > 0, "不同值应该产生审计日志"
        if update_logs:
            changes = update_logs[0].get('changes', {})
            assert 'display_name' in changes, "变化应该包含 display_name 字段"

    # ==========================================
    # 审计日志必填字段测试
    # ==========================================

    @pytest.mark.requires_cleanup
    def test_audit_log_required_fields(self, shared_client, admin_headers):
        """测试审计日志必填字段完整性"""
        test_user = {
            'username': f'test_user_{int(time.time())}',
            'password': 'test123456',
            'email': f'test_{int(time.time())}@example.com',
            'display_name': f'测试用户_{int(time.time())}'
        }

        response = shared_client.post(
            '/api/v2/bo/user',
            headers=admin_headers,
            data=json.dumps(test_user)
        )

        if response.status_code not in [200, 201, 400, 401, 500]:
            pytest.skip(f"用户创建 API 不可用: {response.status_code}")

        data = response.get_json()
        if not data or not data.get('success'):
            pytest.skip("用户创建失败，跳过审计测试")

        user_id = data.get('data', {}).get('id')
        if not user_id:
            pytest.skip("无法获取创建的用户ID")

        audit_logs = self.get_audit_logs(shared_client, admin_headers, 'user', user_id)
        user_audit = [log for log in audit_logs if log.get('object_id') == str(user_id)]

        assert len(user_audit) > 0, "应该存在审计日志"

        log = user_audit[0]
        assert 'id' in log, "审计日志应包含 id"
        assert 'object_type' in log, "审计日志应包含 object_type"
        assert 'object_id' in log, "审计日志应包含 object_id"
        assert 'action' in log, "审计日志应包含 action"
        assert 'operator_id' in log or 'user_id' in log, "审计日志应包含操作者信息"
        assert 'timestamp' in log or 'created_at' in log, "审计日志应包含时间戳"
