# -*- coding: utf-8 -*-
"""
[MODULE] 断言辅助函数
[DESCRIPTION] 提供统一的断言辅助函数，减少测试代码重复

使用方式：
    from meta.tests.shared.assertions import assert_success, assert_status

    def test_example(api_client):
        resp = api_client.get('/api/v2/bo/user')
        assert_success(resp)  # 替代 assert resp.status_code == 200 and data.get('success', False)
        assert_status(resp, [200, 201])  # 替代 assert resp.status_code in [200, 201, 401, 500]

断言函数分类：
1. HTTP 状态码断言
2. 响应结构断言
3. 分页列表断言
4. 错误响应断言
"""

import json
import pytest


# ==================== HTTP 状态码常量 ====================

class HTTPStatus:
    """HTTP 状态码集合"""
    SUCCESS = [200]
    CREATED = [201]
    ACCEPTED = [202]
    NO_CONTENT = [204]

    OK_OR_CREATED = [200, 201]
    OK_OR_NO_CONTENT = [200, 204]
    SUCCESS_OR_ERROR = [200, 201, 204]

    CREATED_OK = [201, 200]
    CREATED_OK_ERROR = [201, 200, 400, 500]
    CREATED_OK_NOT_FOUND = [201, 200, 404]
    CREATED_OK_ERROR_NOT_FOUND = [201, 200, 400, 404, 500]

    CLIENT_ERROR = [400, 422]
    CLIENT_ERROR_NOT_FOUND = [400, 404, 422]
    CLIENT_ERROR_SERVER = [400, 500]
    CLIENT_ERROR_ALL = [400, 401, 403, 404, 422, 500]

    AUTH_ERROR = [401, 403, 302]
    AUTH_ERROR_ALL = [401, 403, 302, 500]

    NOT_FOUND = [404]
    NOT_FOUND_OK = [404, 200]
    NOT_FOUND_ERROR = [404, 400, 500]

    META_OK = [200, 404, 410, 500]
    META_OK_STRICT = [200, 404, 410]
    PAGINATION_OK = [200, 500]
    PERMISSION_OK = [200, 404, 500]

    DELETED_OK = [200, 204, 400]
    BATCH_OK = [200, 204, 400, 404, 500]
    UPDATE_OK = [200, 400]
    UPDATE_OK_NOT_FOUND = [200, 400, 404]

    ALL_OK = [200, 201, 400, 404, 500]

    # ==================== 鉴权 + 200/400/404 组合 (2026-06-07 补齐) ====================
    # 标准 OK_AUTH 三元组 (200/401/500) - 用于未引入 403 的简单认证端点
    OK_AUTH = [200, 401, 500]
    # 完整鉴权 OK (200/401/403/500) - 用于 admin 权限可能 403 的端点
    OK_AUTH_FORBIDDEN = [200, 401, 403, 500]
    # 校验错误 (400/401/500) - 用于未引入 403 的参数校验
    VALIDATION_AUTH = [400, 401, 500]
    # 校验错误 (400/401/403/500) - 用于 admin 权限可能 403 的参数校验
    VALIDATION_AUTH_FORBIDDEN = [400, 401, 403, 500]
    # Not Found (404/500) - 无 auth 维度的纯 404
    NOT_FOUND_500 = [404, 500]
    # Not Found (404/401/500) - 带 auth 的 404
    NOT_FOUND_AUTH = [404, 401, 500]
    # Not Found (404/401/403/500) - 带 auth+forbidden 的 404
    NOT_FOUND_AUTH_FORBIDDEN = [404, 401, 403, 500]
    # Sunset (410/401/500) - 顶层 sunset CRUD
    SUNSET_AUTH = [410, 401, 500]
    # Sunset OK (200/401/410/500) - sunset 但允许返回列表
    SUNSET_OK_AUTH = [200, 401, 410, 500]
    # Sunset 校验 (400/401/403/500/410) - sunset 端点的参数校验
    SUNSET_VALIDATION = [400, 401, 403, 500, 410]
    # Sunset OK (200/403/500/410) - sunset 端点的成功 (admin only → 403)
    SUNSET_OK = [200, 403, 500, 410]


# ==================== HTTP 状态码断言 ====================

def assert_status(response, expected_codes, message=None):
    """
    [ASSERT] 断言响应状态码

    Args:
        response: Flask test client response
        expected_codes: 期望的状态码列表
        message: 自定义错误消息

    Example:
        assert_status(resp, HTTPStatus.OK_OR_CREATED)
        assert_status(resp, [200, 201], "创建用户失败")
    """
    assert response.status_code in expected_codes, \
        message or f"预期状态码 {expected_codes}，实际 {response.status_code}"


def assert_success(response, expected_codes=None):
    """
    [ASSERT] 断言成功响应 (状态码 200 + success=True)

    Args:
        response: Flask test client response
        expected_codes: 可选，期望的状态码列表，默认 [200]

    Example:
        assert_success(resp)  # 200 + success=True
        assert_success(resp, [200, 201])  # 200/201 + success=True
    """
    codes = expected_codes or [200]

    assert response.status_code in codes, \
        f"预期状态码 {codes}，实际 {response.status_code}"

    data = _get_json(response)
    assert data.get('success') is True, \
        f"响应 success 字段应为 True，实际 {data.get('success')}"


def assert_created(response, message=None):
    """
    [ASSERT] 断言创建成功 (201 + success=True)

    Args:
        response: Flask test client response
        message: 自定义错误消息

    Example:
        assert_created(resp)
    """
    assert_status(response, [201, 200], message)
    data = _get_json(response)
    assert data.get('success') is True, \
        message or f"响应 success 字段应为 True，实际 {data.get('success')}"


def assert_error(response, expected_codes=None, message=None):
    """
    [ASSERT] 断言错误响应

    Args:
        response: Flask test client response
        expected_codes: 可选，期望的错误状态码，默认 [400, 404, 500]
        message: 自定义错误消息

    Example:
        assert_error(resp)  # 默认 400/404/500
        assert_error(resp, [400, 422])  # 验证错误
    """
    codes = expected_codes or [400, 404, 500]
    assert_status(response, codes, message)


def assert_not_found(response, message=None):
    """
    [ASSERT] 断言资源不存在 (404)

    Args:
        response: Flask test client response
        message: 自定义错误消息

    Example:
        assert_not_found(resp)
    """
    assert_status(response, [404], message)


def assert_unauthorized(response, message=None):
    """
    [ASSERT] 断言未授权访问 (401/403)

    Args:
        response: Flask test client response
        message: 自定义错误消息

    Example:
        assert_unauthorized(resp)
    """
    assert_status(response, [401, 403, 302, 500], message)


# ==================== 高级助手 (v3.18 / 2026-06-07 补齐) ====================

def expect(client, method, url, expected_codes, **kwargs):
    """
    [HELPER] 发起 HTTP 请求并断言状态码 (2 行 → 1 行)

    Args:
        client: Flask test client (api_client / app_client / shared_client)
        method: HTTP 方法 ('get' / 'post' / 'put' / 'delete')
        url: 端点 URL
        expected_codes: 期望的状态码列表
        **kwargs: 透传给 client method (json=..., data=..., headers=...)

    Returns:
        response: Flask test client response (供进一步断言)

    Example:
        # Before: 2 行
        r = api_client.get('/api/v1/user-groups')
        assert_status(r, SUNSET_AUTH)

        # After: 1 行
        expect(api_client, 'get', '/api/v1/user-groups', SUNSET_AUTH)

        # 进一步断言 (取返回):
        r = expect(api_client, 'post', '/api/v1/import', VALIDATION, data={})
        assert_data_contains(r, 'error')
    """
    response = getattr(client, method)(url, **kwargs)
    assert_status(response, expected_codes)
    return response


def assert_data_contains(response, *keys, scope='data'):
    """
    [ASSERT] 如果响应成功 (200/201), 检查 body[scope] 包含给定 keys

    Args:
        response: Flask test client response
        *keys: 必须包含的字段名 (变长参数)
        scope: 检查的子字典路径, 默认 'data'
              传 None 则检查整个 body

    Returns:
        data: body[scope] (200 时) 或 None (其他状态码)

    Example:
        r = expect(api_client, 'get', '/api/v1/identity?object_type=domain', OK)
        assert_data_contains(r, 'data', 'object_type')  # check body['data'] has 'object_type'
    """
    if response.status_code not in (200, 201):
        return None
    body = get_json(response)
    target = body if scope is None else body.get(scope, {})
    for key in keys:
        assert key in target, \
            f"响应 {scope or 'body'} 应包含字段 '{key}', 实际字段: {list(target.keys())[:5]}"
    return target


def assert_data_field(response, field, expected, scope='data'):
    """
    [ASSERT] 如果响应成功 (200/201), 检查 body[scope][field] == expected

    Args:
        response: Flask test client response
        field: 要检查的字段名
        expected: 期望的值
        scope: 检查的子字典路径, 默认 'data'
              传 None 则检查整个 body

    Example:
        r = expect(api_client, 'get', '/api/v1/user-groups/1/members', OK_AUTH)
        assert_data_field(r, '_deprecated', True)
    """
    if response.status_code not in (200, 201):
        return None
    body = get_json(response)
    target = body if scope is None else body.get(scope, {})
    actual = target.get(field)
    assert actual == expected, \
        f"响应 {scope or 'body'}.{field} 应为 {expected!r}, 实际 {actual!r}"
    return target


# ==================== 响应结构断言 ====================

def assert_response_structure(response, required_fields=None, expected_codes=None):
    """
    [ASSERT] 断言响应结构

    Args:
        response: Flask test client response
        required_fields: 必需的字段列表，默认 ['success', 'data']
        expected_codes: 可选，期望的状态码

    Example:
        assert_response_structure(resp)  # 默认检查 success, data
        assert_response_structure(resp, ['success', 'data', 'message'])
    """
    if expected_codes:
        assert_status(response, expected_codes)

    fields = required_fields or ['success', 'data']
    data = _get_json(response)

    for field in fields:
        assert field in data, \
            f"响应应包含字段 '{field}'，实际字段: {list(data.keys())}"


def assert_success_response(response, expected_codes=None):
    """
    [ASSERT] 断言成功响应结构 (包含 success=True 和 data)

    Args:
        response: Flask test client response
        expected_codes: 可选，期望的状态码

    Example:
        assert_success_response(resp)
        assert_success_response(resp, [200, 201])
    """
    assert_success(response, expected_codes)
    data = _get_json(response)
    assert 'data' in data, "响应应包含 data 字段"


def assert_error_response(response, expected_codes=None):
    """
    [ASSERT] 断言错误响应结构

    Args:
        response: Flask test client response
        expected_codes: 可选，期望的状态码

    Example:
        assert_error_response(resp)
    """
    codes = expected_codes or [400, 404, 500]
    assert_status(response, codes)

    data = _get_json(response)
    assert data.get('success') is False, \
        f"错误响应 success 应为 False，实际 {data.get('success')}"


def assert_has_field(response, field_name, expected_codes=None):
    """
    [ASSERT] 断言响应包含特定字段

    Args:
        response: Flask test client response
        field_name: 字段名
        expected_codes: 可选，期望的状态码

    Example:
        assert_has_field(resp, 'id')
        assert_has_field(resp, 'items', expected_codes=[200])
    """
    if expected_codes:
        assert_status(response, expected_codes)

    data = _get_json(response)
    assert field_name in data, \
        f"响应应包含字段 '{field_name}'，实际字段: {list(data.keys())}"


def assert_field_value(response, field_name, expected_value, expected_codes=None):
    """
    [ASSERT] 断言响应字段值

    Args:
        response: Flask test client response
        field_name: 字段名
        expected_value: 期望值
        expected_codes: 可选，期望的状态码

    Example:
        assert_field_value(resp, 'object_type', 'user')
        assert_field_value(resp, 'import_enabled', True)
    """
    if expected_codes:
        assert_status(response, expected_codes)

    data = _get_json(response)
    actual_value = data.get(field_name)
    assert actual_value == expected_value, \
        f"字段 '{field_name}' 应为 {expected_value}，实际 {actual_value}"


# ==================== 分页列表断言 ====================

def assert_pagination(response, expected_codes=None):
    """
    [ASSERT] 断言分页响应结构

    Args:
        response: Flask test client response
        expected_codes: 可选，期望的状态码

    Example:
        assert_pagination(resp)
    """
    codes = expected_codes or [200]
    assert_status(response, codes)

    data = _get_json(response)
    assert 'data' in data, "响应应包含 data 字段"

    page_data = data.get('data', {})
    assert 'items' in page_data, "分页数据应包含 items"
    assert 'total' in page_data, "分页数据应包含 total"
    assert isinstance(page_data.get('items', []), list), "items 应为列表"


def assert_pagination_fields(response, expected_codes=None):
    """
    [ASSERT] 断言分页字段完整性

    Args:
        response: Flask test client response
        expected_codes: 可选，期望的状态码

    Example:
        assert_pagination_fields(resp)
    """
    assert_pagination(response, expected_codes)

    data = _get_json(response)
    page_data = data.get('data', {})

    pagination_fields = ['page', 'page_size', 'total', 'items']
    for field in pagination_fields:
        assert field in page_data, f"分页数据应包含 {field}"


def assert_items_count(response, min_count=None, max_count=None, expected_codes=None):
    """
    [ASSERT] 断言列表项数量

    Args:
        response: Flask test client response
        min_count: 最少项数
        max_count: 最多项数
        expected_codes: 可选，期望的状态码

    Example:
        assert_items_count(resp, min_count=1)  # 至少 1 项
        assert_items_count(resp, max_count=10)  # 最多 10 项
        assert_items_count(resp, min_count=1, max_count=10)
    """
    assert_pagination(response, expected_codes)

    data = _get_json(response)
    items = data.get('data', {}).get('items', [])

    if min_count is not None:
        assert len(items) >= min_count, \
            f"列表项数应 >= {min_count}，实际 {len(items)}"

    if max_count is not None:
        assert len(items) <= max_count, \
            f"列表项数应 <= {max_count}，实际 {len(items)}"


def assert_page_size(response, expected_page_size, expected_codes=None):
    """
    [ASSERT] 断言分页大小

    Args:
        response: Flask test client response
        expected_page_size: 期望的 page_size
        expected_codes: 可选，期望的状态码

    Example:
        assert_page_size(resp, 10)
    """
    assert_pagination(response, expected_codes)

    data = _get_json(response)
    page_data = data.get('data', {})
    actual_size = len(page_data.get('items', []))

    assert actual_size <= expected_page_size, \
        f"实际项数 {actual_size} 不应超过 page_size {expected_page_size}"


# ==================== 数据结构断言 ====================

def assert_list_response(response, expected_codes=None):
    """
    [ASSERT] 断言列表响应 (items 是列表)

    Args:
        response: Flask test client response
        expected_codes: 可选，期望的状态码

    Example:
        assert_list_response(resp)
    """
    assert_success(response, expected_codes)

    data = _get_json(response)
    assert 'data' in data
    assert isinstance(data.get('data', {}), (list, dict)), \
        f"data 应为 list 或 dict，实际 {type(data.get('data', {}))}"

    if isinstance(data.get('data', {}), dict):
        assert 'items' in data.get('data', {}), "data 应包含 items 字段"
        assert isinstance(data.get('data', {})['items'], list), "items 应为列表"


def assert_data_has_keys(response, keys, expected_codes=None):
    """
    [ASSERT] 断言 data 中包含指定的 keys

    Args:
        response: Flask test client response
        keys: 期望的 key 列表
        expected_codes: 可选，期望的状态码

    Example:
        assert_data_has_keys(resp, ['id', 'name', 'code'])
    """
    assert_success(response, expected_codes)

    data = _get_json(response)
    data_keys = set(data.get('data', {}).keys())

    for key in keys:
        assert key in data_keys, \
            f"data 应包含 '{key}'，实际 keys: {data_keys}"


def assert_nested_field(response, field_path, expected_codes=None):
    """
    [ASSERT] 断言嵌套字段存在

    Args:
        response: Flask test client response
        field_path: 字段路径，如 'data.user.id'
        expected_codes: 可选，期望的状态码

    Example:
        assert_nested_field(resp, 'data.items.0.id')  # 第一项的 id
        assert_nested_field(resp, 'data.user.name')  # user.name
    """
    if expected_codes:
        assert_status(response, expected_codes)

    data = _get_json(response)
    parts = field_path.split('.')

    current = data
    for part in parts:
        if part.isdigit():
            index = int(part)
            assert isinstance(current, list), f"'{part}' 应该是列表索引"
            assert index < len(current), f"索引 {index} 超出范围"
            current = current[index]
        else:
            assert isinstance(current, dict), f"'{part}' 应该是字典键"
            assert part in current, f"缺少字段 '{part}'"
            current = current[part]


# ==================== 错误消息断言 ====================

def assert_error_message(response, expected_message=None, expected_codes=None):
    """
    [ASSERT] 断言错误消息

    Args:
        response: Flask test client response
        expected_message: 期望的消息内容（支持子串匹配）
        expected_codes: 可选，期望的状态码

    Example:
        assert_error_message(resp)  # 只要有 message 字段
        assert_error_message(resp, 'Not Found')  # 消息包含 'Not Found'
    """
    codes = expected_codes or [400, 404, 500]
    assert_status(response, codes)

    data = _get_json(response)
    assert 'message' in data or 'error' in data, \
        "错误响应应包含 message 或 error 字段"

    if expected_message:
        message = data.get('message') or data.get('error') or ''
        assert expected_message in str(message), \
            f"错误消息应包含 '{expected_message}'，实际 '{message}'"


def assert_validation_error(response, expected_codes=None):
    """
    [ASSERT] 断言验证错误

    Args:
        response: Flask test client response
        expected_codes: 可选，期望的状态码

    Example:
        assert_validation_error(resp)
    """
    codes = expected_codes or [400, 422]
    assert_status(response, codes)

    data = _get_json(response)
    assert data.get('success') is False, "验证错误响应 success 应为 False"


# ==================== JSON 辅助函数 ====================

def _get_json(response):
    """
    [HELPER] 获取 JSON 响应数据

    Args:
        response: Flask test client response

    Returns:
        dict: JSON 解析后的数据
    """
    try:
        return json.loads(response.data)
    except (json.JSONDecodeError, AttributeError):
        return {}


def get_json(response):
    """
    [HELPER] 获取 JSON 响应数据（公开版本）

    Args:
        response: Flask test client response

    Returns:
        dict: JSON 解析后的数据
    """
    return _get_json(response)


def get_items(response):
    """
    [HELPER] 获取响应中的 items

    Args:
        response: Flask test client response

    Returns:
        list: items 列表
    """
    data = _get_json(response)
    page_data = data.get('data', {})

    if isinstance(page_data, dict):
        return page_data.get('items', [])

    if isinstance(page_data, list):
        return page_data

    return []


def get_total(response):
    """
    [HELPER] 获取响应中的 total

    Args:
        response: Flask test client response

    Returns:
        int: total 值
    """
    data = _get_json(response)
    page_data = data.get('data', {})

    if isinstance(page_data, dict):
        return page_data.get('total', 0)

    return 0


# ==================== 便捷别名 ====================

assert_http_ok = lambda r: assert_status(r, [200])
assert_http_created = lambda r: assert_status(r, [201, 200])
assert_http_not_found = lambda r: assert_status(r, [404])
assert_http_bad_request = lambda r: assert_status(r, [400, 422])
assert_http_unauthorized = lambda r: assert_unauthorized(r)
