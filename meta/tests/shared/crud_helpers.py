# -*- coding: utf-8 -*-
"""
[MODULE] CRUD 测试辅助函数
[DESCRIPTION] 提供标准化的 CRUD 操作辅助函数

使用方式：
    from meta.tests.shared.crud_helpers import generate_test_data, create_object, cleanup_object
"""

import pytest
import json
import os


def generate_test_data(obj_type: str, suffix: str = None) -> dict:
    """生成测试数据"""
    if suffix is None:
        suffix = os.urandom(4).hex()

    templates = {
        'user': {
            'username': f'test_{suffix}',
            'password': 'Test123456',
            'email': f'test_{suffix}@test.com',
            'display_name': f'Test User {suffix}'
        },
        'role': {
            'code': f'role_{suffix}',
            'name': f'Role {suffix}',
            'description': f'Test role {suffix}'
        },
        'domain': {
            'code': f'domain_{suffix}',
            'name': f'Domain {suffix}',
            'version_id': 1
        },
    }

    return templates.get(obj_type, {'code': f'{obj_type}_{suffix}', 'name': f'{obj_type.title()} {suffix}'})


def create_object(api_client, admin_headers, obj_type: str, data: dict) -> tuple:
    """创建对象并返回 (id, response_data)"""
    resp = api_client.post(
        f'/api/v2/bo/{obj_type}',
        data=json.dumps(data),
        headers=admin_headers
    )
    resp_data = json.loads(resp.data)

    obj_id = None
    if resp.status_code in [200, 201] and resp_data.get('success'):
        obj_id = resp_data.get('data', {}).get('id')

    return obj_id, resp_data


def cleanup_object(api_client, admin_headers, obj_type: str, obj_id: int):
    """删除单个对象"""
    if obj_id:
        try:
            api_client.delete(
                f'/api/v2/bo/{obj_type}/{obj_id}',
                headers=admin_headers
            )
        except Exception:
            pass


def cleanup_objects(api_client, admin_headers, cleanup_list: list):
    """批量清理对象"""
    for obj_type, obj_id in reversed(cleanup_list):
        cleanup_object(api_client, admin_headers, obj_type, obj_id)


def read_object(api_client, admin_headers, obj_type: str, obj_id: int) -> dict:
    """读取单个对象"""
    resp = api_client.get(f'/api/v2/bo/{obj_type}/{obj_id}', headers=admin_headers)
    return json.loads(resp.data)


def update_object(api_client, admin_headers, obj_type: str, obj_id: int, data: dict) -> dict:
    """更新对象"""
    resp = api_client.put(
        f'/api/v2/bo/{obj_type}/{obj_id}',
        data=json.dumps(data),
        headers=admin_headers
    )
    return json.loads(resp.data)


def delete_object(api_client, admin_headers, obj_type: str, obj_id: int) -> dict:
    """删除对象"""
    resp = api_client.delete(f'/api/v2/bo/{obj_type}/{obj_id}', headers=admin_headers)
    return json.loads(resp.data) if resp.data else {}


def list_objects(api_client, admin_headers, obj_type: str, **kwargs) -> dict:
    """列出对象"""
    params = '&'.join([f'{k}={v}' for k, v in kwargs.items()])
    url = f'/api/v2/bo/{obj_type}'
    if params:
        url += f'?{params}'
    resp = api_client.get(url, headers=admin_headers)
    return json.loads(resp.data)


__all__ = [
    'generate_test_data',
    'create_object',
    'cleanup_object',
    'cleanup_objects',
    'read_object',
    'update_object',
    'delete_object',
    'list_objects',
]
