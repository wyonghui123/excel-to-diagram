"""
assert_helpers - 通用断言助手函数 (Phase 7 重构)

替代散落在各测试中的 assert 模式
"""
import json
from typing import Any, Optional


def assert_api_success(response, expected_status: Optional[int] = None) -> None:
    """
    断言 API 成功响应 (2xx)

    Args:
        response: Flask test response
        expected_status: 期望的精确状态码 (默认 200-299)

    Raises:
        AssertionError
    """
    if expected_status is None:
        assert 200 <= response.status_code < 300, (
            f"Expected 2xx, got {response.status_code}: {response.data[:200]}"
        )
    else:
        assert response.status_code == expected_status, (
            f"Expected {expected_status}, got {response.status_code}: {response.data[:200]}"
        )


def assert_api_error(response,
                     expected_status: Optional[int] = None,
                     expected_code: Optional[str] = None) -> None:
    """
    断言 API 错误响应 (4xx/5xx)

    Args:
        response: Flask test response
        expected_status: 期望的精确状态码
        expected_code: 期望的错误码 (data.code 或 data.error_code)

    Raises:
        AssertionError
    """
    if expected_status is not None:
        assert response.status_code == expected_status, (
            f"Expected {expected_status}, got {response.status_code}: {response.data[:200]}"
        )
    else:
        assert response.status_code >= 400, (
            f"Expected 4xx/5xx, got {response.status_code}: {response.data[:200]}"
        )

    if expected_code is not None:
        data = response.get_json() or {}
        actual_code = data.get('code') or data.get('error_code')
        assert actual_code == expected_code, (
            f"Expected error code {expected_code!r}, got {actual_code!r}"
        )


def assert_data_field(response, field: str, expected: Any) -> Any:
    """
    断言 response.data 中指定字段值

    Args:
        response: Flask test response
        field: 字段名 (支持 data.field 嵌套)
        expected: 期望值

    Returns:
        实际值
    """
    data = response.get_json() or {}

    # 支持嵌套
    if '.' in field:
        parts = field.split('.')
        actual = data
        for p in parts:
            if isinstance(actual, dict):
                actual = actual.get(p)
            else:
                actual = None
                break
    else:
        # 优先 data.field, 然后 field
        actual = data.get('data', {}).get(field) if 'data' in data else data.get(field)

    assert actual == expected, (
        f"Field '{field}': expected {expected!r}, got {actual!r}"
    )
    return actual


def assert_status_code(response, expected: int) -> None:
    """简单状态码断言"""
    assert response.status_code == expected, (
        f"Expected status {expected}, got {response.status_code}: {response.data[:200]}"
    )