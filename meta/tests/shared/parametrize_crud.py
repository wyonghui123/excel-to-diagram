# -*- coding: utf-8 -*-
"""
[MODULE] 参数化 CRUD 测试工具
[DESCRIPTION] 提供 BO 对象的参数化 CRUD 测试功能

使用方式：
1. 使用 @parametrize_crud 装饰器生成测试函数
2. 使用 CRUDTestCases 类定义测试用例

示例：
    # 方式 1: 使用装饰器
    @parametrize_crud('user', ['username', 'password'], 'email@test.com')
    def test_create(api_client, admin_headers, obj_data):
        ...

    # 方式 2: 使用类定义
    class TestUserCRUD(CRUDTestCases):
        object_type = 'user'
        required_fields = ['username', 'password']
        create_template = {'email': 'test@test.com'}
        update_data = {'display_name': 'Updated'}

    # 生成测试报告
    CRUDTestCases.generate_report()
"""

import pytest
import json
import os
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


# ==================== 数据类 ====================

@dataclass
class CRUDTestCase:
    """CRUD 测试用例数据类"""
    object_type: str
    create_data: Dict[str, Any]
    required_fields: List[str] = field(default_factory=list)
    update_data: Dict[str, Any] = field(default_factory=dict)
    unique_fields: List[str] = field(default_factory=lambda: ['username', 'code'])


@dataclass
class CRUDTestResult:
    """CRUD 测试结果数据类"""
    object_type: str
    create_success: int = 0
    create_failed: int = 0
    read_success: int = 0
    read_failed: int = 0
    update_success: int = 0
    update_failed: int = 0
    delete_success: int = 0
    delete_failed: int = 0
    list_success: int = 0
    list_failed: int = 0


# ==================== 测试数据定义 ====================

# 标准 BO 对象测试数据模板
STANDARD_BO_TEST_DATA = {
    'user': {
        'username': 'test_user_{suffix}',
        'password': 'Test123456',
        'email': 'test_{suffix}@test.com',
        'display_name': 'Test User {suffix}',
        'required_fields': ['username', 'password'],
        'update_data': {'display_name': 'Updated User {suffix}'},
    },
    'role': {
        'code': 'role_{suffix}',
        'name': 'Role {suffix}',
        'description': 'Test role description',
        'required_fields': ['code', 'name'],
        'update_data': {'description': 'Updated description'},
    },
    'domain': {
        'code': 'domain_{suffix}',
        'name': 'Domain {suffix}',
        'version_id': 1,
        'required_fields': ['code', 'name'],
        'update_data': {'name': 'Updated Domain'},
    },
    'enum_type': {
        'code': 'enum_{suffix}',
        'name': 'Enum Type {suffix}',
        'required_fields': ['code', 'name'],
        'update_data': {'description': 'Updated description'},
    },
    'enum_value': {
        'code': 'value_{suffix}',
        'name': 'Value {suffix}',
        'enum_type_id': 1,
        'required_fields': ['code', 'name', 'enum_type_id'],
        'update_data': {'name': 'Updated Value'},
    },
    'user_group': {
        'code': 'group_{suffix}',
        'name': 'User Group {suffix}',
        'required_fields': ['code', 'name'],
        'update_data': {'description': 'Updated group'},
    },
}


# ==================== 辅助函数 ====================

def generate_unique_data(obj_type: str, suffix: str = None) -> Dict[str, Any]:
    """
    [FUNCTION] 生成唯一测试数据
    [DESCRIPTION] 根据对象类型生成带唯一标识的测试数据
    [PARAMETERS]
        - obj_type: str - 对象类型
        - suffix: str - 唯一后缀
    [RETURN] Dict: 测试数据
    """
    if suffix is None:
        suffix = os.urandom(4).hex()

    template = STANDARD_BO_TEST_DATA.get(obj_type, {
        'code': f'{obj_type}_{suffix}',
        'name': f'{obj_type.title()} {suffix}',
        'required_fields': ['code'],
        'update_data': {'name': f'Updated {suffix}'},
    })

    data = {}
    for key, value in template.items():
        if key in ['required_fields', 'update_data']:
            continue
        if isinstance(value, str) and '{suffix}' in value:
            data[key] = value.format(suffix=suffix)
        elif key == 'code':
            data[key] = f'{value}_{suffix}'
        else:
            data[key] = value

    return data


def get_required_fields(obj_type: str) -> List[str]:
    """获取必填字段"""
    template = STANDARD_BO_TEST_DATA.get(obj_type, {})
    return template.get('required_fields', ['code', 'name'])


def get_update_data(obj_type: str, suffix: str = None) -> Dict[str, Any]:
    """获取更新数据"""
    if suffix is None:
        suffix = os.urandom(4).hex()

    template = STANDARD_BO_TEST_DATA.get(obj_type, {})
    update_data = template.get('update_data', {'name': 'Updated'})

    result = {}
    for key, value in update_data.items():
        if isinstance(value, str) and '{suffix}' in value:
            result[key] = value.format(suffix=suffix)
        else:
            result[key] = value

    return result


# ==================== Pytest 参数化 ====================

def parametrize_crud(obj_type: str, required_fields: List[str] = None,
                     email_suffix: str = 'test.com',
                     extra_data: Dict = None):
    """
    [DECORATOR] CRUD 参数化装饰器
    [DESCRIPTION] 为测试函数生成 CRUD 参数化标记
    [PARAMETERS]
        - obj_type: str - 对象类型
        - required_fields: List[str] - 必填字段
        - email_suffix: str - 邮箱后缀
        - extra_data: Dict - 额外数据
    [RETURN] pytest.mark.parametrize 装饰器
    [USAGE]
        @parametrize_crud('user', ['username', 'password'])
        def test_create(api_client, admin_headers, obj_data):
            ...
    """
    suffix = os.urandom(4).hex()
    data = generate_unique_data(obj_type, suffix)

    if extra_data:
        data.update(extra_data)

    if obj_type == 'user' and 'email' not in data:
        data['email'] = f'test_{suffix}@{email_suffix}'

    required = required_fields or get_required_fields(obj_type)
    update_data = get_update_data(obj_type, suffix)

    return pytest.mark.parametrize(
        'obj_type,suffix,obj_data,required_fields,update_data',
        [(obj_type, suffix, data, required, update_data)]
    )


def parametrize_crud_multi(*obj_types):
    """
    [DECORATOR] 多对象 CRUD 参数化装饰器
    [DESCRIPTION] 为多个对象类型生成参数化标记
    [PARAMETERS]
        *obj_types: str - 对象类型列表
    [RETURN] pytest.mark.parametrize 装饰器
    [USAGE]
        @parametrize_crud_multi('user', 'role', 'domain')
        def test_crud_operations(api_client, admin_headers, obj_type, suffix, obj_data):
            ...
    """
    arg_values = []
    for obj_type in obj_types:
        suffix = os.urandom(4).hex()
        data = generate_unique_data(obj_type, suffix)
        required = get_required_fields(obj_type)
        update_data = get_update_data(obj_type, suffix)
        arg_values.append((obj_type, suffix, data, required, update_data))

    return pytest.mark.parametrize(
        'obj_type,suffix,obj_data,required_fields,update_data',
        arg_values
    )


def parametrize_create(required_fields: List[str] = None):
    """
    [DECORATOR] 创建操作参数化装饰器
    [DESCRIPTION] 仅生成创建操作的参数化测试数据
    """
    suffix = os.urandom(4).hex()

    data = {}
    if required_fields:
        for field in required_fields:
            if field == 'username':
                data[field] = f'test_{suffix}'
            elif field == 'password':
                data[field] = 'Test123456'
            elif field == 'code':
                data[field] = f'code_{suffix}'
            elif field == 'name':
                data[field] = f'Name {suffix}'
            else:
                data[field] = f'{field}_{suffix}'

    return pytest.mark.parametrize('obj_data,required_fields', [(data, required_fields or [])])


def parametrize_update(obj_type: str):
    """
    [DECORATOR] 更新操作参数化装饰器
    [DESCRIPTION] 仅生成更新操作的参数化测试数据
    """
    suffix = os.urandom(4).hex()
    update_data = get_update_data(obj_type, suffix)

    return pytest.mark.parametrize('update_data', [update_data])


# ==================== 测试用例类 ====================

class CRUDTestCases:
    """
    [CLASS] CRUD 测试用例集合
    [DESCRIPTION] 提供标准化的 CRUD 测试用例定义

    使用方式：
        class TestUserCRUD(CRUDTestCases):
            object_type = 'user'
            create_data = {'username': 'test', 'password': 'pwd'}
            required_fields = ['username', 'password']
            update_data = {'display_name': 'Updated'}

        # 自动生成参数化测试
        @pytest.mark.parametrize('obj_data', CRUDTestCases.parametrize_create())
        def test_create(api_client, admin_headers, obj_data):
            ...
    """

    object_type: str = None
    create_data: Dict[str, Any] = None
    required_fields: List[str] = None
    update_data: Dict[str, Any] = None

    @classmethod
    def get_object_type(cls):
        """获取对象类型"""
        return cls.object_type

    @classmethod
    def get_suffix(cls):
        """获取唯一后缀"""
        return os.urandom(4).hex()

    @classmethod
    def generate_create_data(cls):
        """生成创建数据"""
        suffix = cls.get_suffix()
        if cls.create_data:
            data = {}
            for k, v in cls.create_data.items():
                if isinstance(v, str) and '{suffix}' in v:
                    data[k] = v.format(suffix=suffix)
                else:
                    data[k] = v
            return data
        return generate_unique_data(cls.object_type, suffix)

    @classmethod
    def parametrize_create(cls):
        """生成创建测试参数"""
        data = cls.generate_create_data()
        required = cls.required_fields or get_required_fields(cls.object_type)
        return [(data, required)]

    @classmethod
    def parametrize_update(cls):
        """生成更新测试参数"""
        suffix = cls.get_suffix()
        update_data = cls.update_data or get_update_data(cls.object_type, suffix)
        return [(update_data)]

    @classmethod
    def parametrize_all(cls):
        """生成所有 CRUD 测试参数"""
        suffix = cls.get_suffix()
        create_data = cls.generate_create_data()
        required = cls.required_fields or get_required_fields(cls.object_type)
        update_data = cls.update_data or get_update_data(cls.object_type, suffix)
        return [(cls.object_type, suffix, create_data, required, update_data)]

    @classmethod
    def generate_report(cls):
        """生成测试用例报告"""
        print(f"\n{'='*60}")
        print(f"CRUD Test Report: {cls.object_type}")
        print(f"{'='*60}")
        print(f"Required Fields: {cls.required_fields or 'Auto-detected'}")
        print(f"Create Data: {cls.generate_create_data()}")
        print(f"Update Data: {cls.update_data or 'Auto-generated'}")
        print(f"{'='*60}\n")


# ==================== 测试辅助函数 ====================

def create_object_and_cleanup(api_client, admin_headers, obj_type: str,
                            data: Dict, cleanup_list: list) -> Optional[int]:
    """
    [FUNCTION] 创建对象并添加到清理列表
    [DESCRIPTION] 一站式创建和清理管理
    [PARAMETERS]
        - api_client: Flask test client
        - admin_headers: Admin authentication headers
        - obj_type: str - Object type
        - data: Dict - Create data
        - cleanup_list: list - Cleanup tracking list
    [RETURN] Object ID or None
    """
    resp = api_client.post(
        f'/api/v2/bo/{obj_type}',
        data=json.dumps(data),
        headers=admin_headers
    )
    resp_data = json.loads(resp.data)

    if resp.status_code in [200, 201] and resp_data.get('success'):
        obj_id = resp_data.get('data', {}).get('id')
        if obj_id:
            cleanup_list.append((obj_type, obj_id))
        return obj_id

    return None


def assert_crud_operations(obj_type: str, api_client, admin_headers,
                         create_data: Dict, update_data: Dict = None,
                         required_fields: List[str] = None):
    """
    [FUNCTION] 断言 CRUD 操作序列
    [DESCRIPTION] 执行完整的 CRUD 操作并验证结果
    """
    # Create
    resp = api_client.post(
        f'/api/v2/bo/{obj_type}',
        data=json.dumps(create_data),
        headers=admin_headers
    )
    assert resp.status_code in [200, 201, 401, 500], f"Create failed: {resp.data}"

    resp_data = json.loads(resp.data)
    obj_id = resp_data.get('data', {}).get('id')
    assert obj_id is not None, "Create should return object ID"

    # Read
    resp = api_client.get(
        f'/api/v2/bo/{obj_type}/{obj_id}',
        headers=admin_headers
    )
    assert resp.status_code in [200, 401, 404, 500], f"Read failed: {resp.data}"

    # Update
    if update_data:
        resp = api_client.put(
            f'/api/v2/bo/{obj_type}/{obj_id}',
            data=json.dumps(update_data),
            headers=admin_headers
        )
        assert resp.status_code in [200, 204, 401, 500], f"Update failed: {resp.data}"

    # Delete
    resp = api_client.delete(
        f'/api/v2/bo/{obj_type}/{obj_id}',
        headers=admin_headers
    )
    assert resp.status_code in [200, 204, 401, 500], f"Delete failed: {resp.data}"


# ==================== 导出 ====================

__all__ = [
    'CRUDTestCase',
    'CRUDTestResult',
    'STANDARD_BO_TEST_DATA',
    'generate_unique_data',
    'get_required_fields',
    'get_update_data',
    'parametrize_crud',
    'parametrize_crud_multi',
    'parametrize_create',
    'parametrize_update',
    'CRUDTestCases',
    'create_object_and_cleanup',
    'assert_crud_operations',
]
