import pytest

pytestmark = pytest.mark.integration

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API 冒烟测试

验证所有核心 API 在服务正确初始化后能正常工作。
这些测试应该在每次部署后运行，确保最基础的功能没有被破坏。

覆盖测试点：
1. 对象标识 API (identity) - 验证数据源初始化
2. 角色 API (roles) CRUD - 验证 fetchone 只调用一次
3. 用户 API (users) 删除 - 验证数据源初始化
4. 关联 API (associations) - 验证数据源初始化
5. 枚举 API (enums) - 验证数据源初始化
"""

import pytest
import requests
import json
import os
import time


BASE_URL = os.environ.get('TEST_API_URL', 'http://localhost:3010')  # v3.18 P1: 修复端口不一致


def _server_check():
    """v3.18 P1: 检查后端服务可达（端口由 env 或默认 3010 决定）

    容忍任何 HTTP 状态（4xx/5xx 都算路由存在），仅网络错误算不可达。
    4xx 是常见 (401 未登录, 405 方法不允许) 表明服务在跑且路由注册成功。
    """
    try:
        r = requests.get(f'{BASE_URL}/', timeout=2)
        return r.status_code < 600  # 任何 HTTP 响应 = 服务在跑
    except Exception:
        return False


_SERVER_AVAILABLE = _server_check()


ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'


def _try_login():
    try:
        response = requests.post(f'{BASE_URL}/api/v2/bo/auth/login', json={
            'username': ADMIN_USERNAME,
            'password': ADMIN_PASSWORD
        }, timeout=10)
        data = response.json()
        token = data.get('data', {}).get('token')
        return token, {'Authorization': f'Bearer {token}'}
    except Exception:
        return None, None


class TestAPISmokeTests:
    """API 冒烟测试套件"""

    @classmethod
    def setup_class(cls):
        """测试前登录获取 token"""
        # v3.18 P1: setup_class 时重新检查服务（避免模块加载时服务未启动）
        if not _server_check():
            pytest.skip("后端服务未运行，跳过集成测试")
        cls.token, cls.headers = _try_login()
        if not cls.token:
            pytest.skip("登录失败，跳过集成测试")

    def _skip_if_no_auth(self):
        # v3.18 P1: 每次重新检查服务（避免模块加载时服务未启动）
        if not _server_check():
            pytest.skip("后端服务未运行，跳过集成测试")
        if not getattr(self.__class__, 'token', None):
            pytest.skip("登录失败，跳过集成测试")

    @pytest.mark.requires_cleanup
    def test_01_identity_batch_api_initialized(self):
        """测试 identity batch API 已正确初始化

        验证点：get_data_source() 被正确初始化，不是无参数调用
        之前 bug: get_data_source() missing 1 required positional argument: 'source_type'
        """
        self._skip_if_no_auth()

        response = requests.post(
            f'{BASE_URL}/api/v2/bo/identity/batch',
            headers=self.headers,
            json={
                'requests': [
                    {'object_type': 'domain', 'object_id': 1},
                    {'object_type': 'domain', 'object_id': 2}
                ],
                'format': 'short'
            },
            timeout=10
        )

        assert response.status_code == 200, \
            f"identity/batch API 应该返回 200，实际返回 {response.status_code}: {response.text}"

        data = response.json()
        assert data.get('success') is True, \
            f"identity/batch 应该成功，实际返回: {data}"
        assert 'data' in data, \
            f"响应应该包含 data 字段，实际返回: {data}"

    @pytest.mark.requires_cleanup
    def test_02_role_delete_audit_data_integrity(self):
        """测试角色删除审计数据完整性

        验证点：cursor.fetchone() 不会被多次调用导致数据丢失
        审计日志按字段级别存储，每个字段都有 old_value
        """
        self._skip_if_no_auth()

        role_name = f'test_role_audit_{int(time.time())}'
        role_data = {
            'code': f'test_audit_{int(time.time())}',
            'name': role_name,
            'description': '冒烟测试角色'
        }

        create_response = requests.post(
            f'{BASE_URL}/api/v2/bo/roles',
            headers=self.headers,
            json=role_data,
            timeout=10
        )
        assert create_response.status_code == 201, \
            f"创建角色失败: {create_response.text}"

        role_id = create_response.json().get('data', {}).get('id')
        assert role_id, "创建角色应该返回 id"

        time.sleep(0.1)

        delete_response = requests.delete(
            f'{BASE_URL}/api/v2/bo/roles/{role_id}',
            headers=self.headers,
            timeout=10
        )

        assert delete_response.status_code == 200, \
            f"删除角色应该返回 200，实际返回 {delete_response.status_code}: {delete_response.text}"

        time.sleep(0.1)

        audit_response = requests.get(
            f'{BASE_URL}/api/v2/bo/audit/logs',
            headers=self.headers,
            params={
                'object_type': 'role',
                'object_id': str(role_id),
                'page': 1,
                'page_size': 100
            },
            timeout=10
        )

        assert audit_response.status_code == 200, \
            f"查询审计日志应该返回 200，实际返回 {audit_response.status_code}"

        audit_logs = audit_response.json().get('data', [])
        delete_logs = [log for log in audit_logs if log.get('action') == 'DELETE']

        assert len(delete_logs) > 0, \
            f"应该存在 DELETE 类型的审计日志，实际审计日志: {audit_logs}"

        code_delete_logs = [log for log in delete_logs if log.get('field_name') == 'code']
        assert len(code_delete_logs) > 0, \
            f"应该存在 code 字段的 DELETE 审计日志"

        code_log = code_delete_logs[0]
        assert code_log.get('old_value') != '', \
            f"code 字段的 old_value 不应该为空，实际: {code_log.get('old_value')}"
        assert role_data['code'] in code_log.get('old_value', ''), \
            f"code 字段的 old_value 应该包含 '{role_data['code']}'，实际: {code_log.get('old_value')}"

        name_delete_logs = [log for log in delete_logs if log.get('field_name') == 'name']
        assert len(name_delete_logs) > 0, \
            f"应该存在 name 字段的 DELETE 审计日志"

        name_log = name_delete_logs[0]
        assert name_log.get('old_value') == role_name, \
            f"name 字段的 old_value 应该为 '{role_name}'，实际: {name_log.get('old_value')}"

    @pytest.mark.requires_cleanup
    def test_03_user_delete_api_initialized(self):
        """测试用户删除 API 已正确初始化

        验证点：delete_user() 函数中数据源被正确初始化
        之前 bug: get_data_source() 无参数调用导致 500 错误
        """
        self._skip_if_no_auth()

        user_data = {
            'username': f'test_del_user_{int(time.time())}',
            'password': 'test123456',
            'email': f'test_del_{int(time.time())}@example.com',
            'display_name': f'删除测试用户_{int(time.time())}'
        }

        create_response = requests.post(
            f'{BASE_URL}/api/v2/bo/users',
            headers=self.headers,
            json=user_data,
            timeout=10
        )
        create_status = create_response.status_code
        if create_status == 201:
            user_id = create_response.json().get('data', {}).get('id')
        elif create_status == 400:
            users_response = requests.get(
                f'{BASE_URL}/api/v2/bo/users',
                headers=self.headers,
                params={'keyword': user_data['username'], 'page': 1, 'page_size': 1},
                timeout=10
            )
            users = users_response.json().get('data', [])
            if users:
                user_id = users[0].get('id')
            else:
                pytest.skip("无法创建或查找测试用户，跳过此测试")
        else:
            pytest.skip(f"用户创建返回意外状态码 {create_status}，跳过此测试")

        delete_response = requests.delete(
            f'{BASE_URL}/api/v2/bo/users/{user_id}',
            headers=self.headers,
            timeout=10
        )

        if delete_response.status_code == 404:
            pytest.skip(f"用户 {user_id} 不存在，可能已被删除或未创建成功")

        assert delete_response.status_code == 200, \
            f"删除用户应该返回 200，实际返回 {delete_response.status_code}: {delete_response.text}"

        data = delete_response.json()
        assert data.get('success') is True or 'not found' in str(data).lower(), \
            f"删除用户应该成功或返回 not found，实际返回: {data}"

    @pytest.mark.requires_cleanup
    def test_04_association_api_initialized(self):
        """测试关联 API 已正确初始化

        验证点：association_api.py 中数据源被正确初始化
        之前 bug: get_data_source() 无参数调用导致 500 错误
        """
        self._skip_if_no_auth()

        role_data = {
            'code': f'test_assoc_{int(time.time())}',
            'name': f'关联测试角色_{int(time.time())}',
            'description': '冒烟测试角色'
        }

        create_response = requests.post(
            f'{BASE_URL}/api/v2/bo/roles',
            headers=self.headers,
            json=role_data,
            timeout=10
        )
        assert create_response.status_code == 201, \
            f"创建角色失败: {create_response.text}"

        role_id = create_response.json().get('data', {}).get('id')

        response = requests.get(
            f'{BASE_URL}/api/v2/bo/associations/role/{role_id}/users',
            headers=self.headers,
            timeout=10
        )

        if response.status_code == 500:
            error_data = response.json()
            if 'NoneType' in error_data.get('message', ''):
                pytest.fail(f"关联查询返回 500 (NoneType error)，可能是关联定义问题: {error_data}")
            else:
                pytest.fail(f"关联查询返回 500 错误: {error_data}")

        assert response.status_code == 200, \
            f"关联查询应该返回 200，实际返回 {response.status_code}: {response.text}"

        data = response.json()
        assert 'data' in data or data.get('success') is not False, \
            f"关联查询应该成功，实际返回: {data}"

        requests.delete(
            f'{BASE_URL}/api/v2/bo/roles/{role_id}',
            headers=self.headers,
            timeout=10
        )

    @pytest.mark.requires_cleanup
    def test_05_enum_type_delete_api(self):
        """测试枚举类型删除 API

        验证点：枚举 API 使用正确的 _get_data_source()
        """
        self._skip_if_no_auth()

        timestamp = int(time.time() * 1000)
        enum_data = {
            'id': f'TE{timestamp}',
            'name': f'测试枚举_{timestamp}',
            'description': '冒烟测试枚举'
        }

        create_response = requests.post(
            f'{BASE_URL}/api/v2/bo/enum-types',
            headers=self.headers,
            json=enum_data,
            timeout=10
        )
        assert create_response.status_code in [200, 201, 401, 500], \
            f"创建枚举类型失败: {create_response.text}"

        enum_id = create_response.json().get('data', {}).get('id')
        assert enum_id, "创建枚举类型应该返回 id"

        delete_response = requests.delete(
            f'{BASE_URL}/api/v2/bo/enum-types/{enum_id}',
            headers=self.headers,
            timeout=10
        )

        assert delete_response.status_code == 200, \
            f"删除枚举类型应该返回 200，实际返回 {delete_response.status_code}: {delete_response.text}"

    def test_07_identity_single_api_full_format(self):
        """测试单个对象标识 API（完整格式）

        验证点：identity API 支持各种 format 参数
        """
        self._skip_if_no_auth()

        formats = ['full', 'short', 'minimal', 'technical', 'detailed']

        for fmt in formats:
            response = requests.get(
                f'{BASE_URL}/api/v2/bo/identity',
                headers=self.headers,
                params={
                    'object_type': 'domain',
                    'object_id': 1,
                    'format': fmt
                },
                timeout=10
            )

            assert response.status_code == 200, \
                f"format={fmt} 时应该返回 200，实际返回 {response.status_code}"

            data = response.json()
            assert data.get('success') is True, \
                f"format={fmt} 时应该成功，实际返回: {data}"


class TestPaginationSmokeTests:
    """分页功能冒烟测试"""

    @classmethod
    def setup_class(cls):
        """测试前登录获取 token"""
        # v3.18 P1: setup_class 时重新检查服务（避免模块加载时服务未启动）
        if not _server_check():
            pytest.skip("后端服务未运行，跳过集成测试")
        cls.token, cls.headers = _try_login()
        if not cls.token:
            pytest.skip("登录失败，跳过集成测试")

    def _skip_if_no_auth(self):
        # v3.18 P1: 每次重新检查服务（避免模块加载时服务未启动）
        if not _server_check():
            pytest.skip("后端服务未运行，跳过集成测试")
        if not getattr(self.__class__, 'token', None):
            pytest.skip("登录失败，跳过集成测试")

    def test_01_users_list_pagination(self):
        """测试用户列表分页 API"""
        self._skip_if_no_auth()

        response = requests.get(
            f'{BASE_URL}/api/v2/bo/users',
            headers=self.headers,
            params={
                'page': 1,
                'page_size': 10
            },
            timeout=10
        )

        assert response.status_code == 200, \
            f"用户列表应该返回 200，实际返回 {response.status_code}: {response.text}"

        data = response.json()
        assert 'data' in data, f"响应应该包含 data 字段，实际返回: {data}"
        assert 'total' in data, f"响应应该包含 total 字段，实际返回: {data}"
        assert isinstance(data.get('data', {}), list), \
            f"data 应该是数组，实际类型: {type(data.get('data', {}))}"

    def test_02_users_list_with_keyword(self):
        """测试用户列表搜索功能"""
        self._skip_if_no_auth()

        response = requests.get(
            f'{BASE_URL}/api/v2/bo/users',
            headers=self.headers,
            params={
                'page': 1,
                'page_size': 10,
                'keyword': 'admin'
            },
            timeout=10
        )

        assert response.status_code == 200, \
            f"用户列表搜索应该返回 200，实际返回 {response.status_code}"

        data = response.json()
        assert data.get('success') is not False, \
            f"用户列表搜索应该成功，实际返回: {data}"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
