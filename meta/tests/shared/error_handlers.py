# -*- coding: utf-8 -*-
"""
[MODULE] 统一错误处理模式
[DESCRIPTION] 提供一致的 API 请求和错误处理模式

使用方式：
    from meta.tests.shared.error_handlers import safe_request, APIRequest

    # 方式 1: 函数式
    response = safe_request(client.post, url, **kwargs)

    # 方式 2: 类式
    req = APIRequest(client)
    response = req.post(url, **kwargs)

错误处理原则：
1. 统一捕获网络异常和超时
2. 统一记录错误日志
3. 统一的响应验证
4. 可配置的失败处理策略
"""

import json
import logging
import time
from typing import Optional, Dict, Any, Callable, List, Union
from dataclasses import dataclass, field
from enum import Enum


logger = logging.getLogger(__name__)


# ==================== 错误类型定义 ====================

class ErrorType(Enum):
    """错误类型枚举"""
    NETWORK_ERROR = 'network_error'
    TIMEOUT_ERROR = 'timeout_error'
    HTTP_ERROR = 'http_error'
    VALIDATION_ERROR = 'validation_error'
    PARSE_ERROR = 'parse_error'
    UNKNOWN_ERROR = 'unknown_error'


class ErrorStrategy(Enum):
    """错误处理策略"""
    RAISE = 'raise'           # 直接抛出异常
    RETURN_DEFAULT = 'return_default'  # 返回默认值
    RETRY = 'retry'           # 重试
    LOG_ONLY = 'log_only'     # 仅记录日志


# ==================== 请求结果数据类 ====================

@dataclass
class RequestResult:
    """请求结果数据类"""
    success: bool
    response: Any = None
    error: Optional[str] = None
    error_type: ErrorType = ErrorType.UNKNOWN_ERROR
    status_code: Optional[int] = None
    retry_count: int = 0

    @property
    def data(self):
        """获取响应数据"""
        if self.response is None:
            return None
        try:
            if hasattr(self.response, 'data'):
                return json.loads(self.response.data)
            return self.response
        except (json.JSONDecodeError, AttributeError):
            return None

    @property
    def is_success_status(self):
        """是否成功的 HTTP 状态码"""
        if self.status_code is None:
            return False
        return 200 <= self.status_code < 300


# ==================== 统一请求函数 ====================

def safe_request(
    request_func: Callable,
    *args,
    timeout: int = 30,
    retry_count: int = 0,
    retry_delay: float = 1.0,
    error_strategy: ErrorStrategy = ErrorStrategy.RAISE,
    default_response: Any = None,
    expected_status: Optional[List[int]] = None,
    **kwargs
) -> RequestResult:
    """
    [FUNCTION] 安全请求包装器
    [DESCRIPTION] 统一处理网络异常、超时和 HTTP 错误

    Args:
        request_func: 请求函数 (如 client.get, client.post)
        *args: 请求函数的参数
        timeout: 超时时间（秒）
        retry_count: 重试次数
        retry_delay: 重试间隔（秒）
        error_strategy: 错误处理策略
        default_response: 默认响应（error_strategy=RETURN_DEFAULT 时使用）
        expected_status: 期望的状态码列表
        **kwargs: 请求函数的其他参数

    Returns:
        RequestResult: 请求结果对象

    Example:
        # 基础用法
        result = safe_request(client.get, '/api/v2/bo/user', headers=headers)

        # 自动重试
        result = safe_request(
            client.post, '/api/v2/bo/user',
            retry_count=3, retry_delay=0.5,
            **kwargs
        )

        # 返回默认值而非抛出异常
        result = safe_request(
            client.get, '/api/v2/bo/user',
            error_strategy=ErrorStrategy.RETURN_DEFAULT,
            default_response=MockResponse(status_code=500)
        )

        # 检查结果
        if result.success:
            data = result.data
        else:
            print(f"Error: {result.error}")
    """
    last_error = None
    current_retry = 0

    while True:
        try:
            response = request_func(*args, timeout=timeout, **kwargs)

            status_code = getattr(response, 'status_code', None)

            if expected_status and status_code not in expected_status:
                error_msg = f'Unexpected status code: {status_code}, expected: {expected_status}'
                logger.warning(f"[safe_request] {error_msg}")

                if error_strategy == ErrorStrategy.RAISE:
                    raise HTTPStatusError(error_msg, status_code=status_code)

                return RequestResult(
                    success=False,
                    response=response,
                    error=error_msg,
                    error_type=ErrorType.HTTP_ERROR,
                    status_code=status_code,
                    retry_count=current_retry
                )

            return RequestResult(
                success=True,
                response=response,
                status_code=status_code,
                retry_count=current_retry
            )

        except (ConnectionError, TimeoutError) as e:
            last_error = e
            error_type = ErrorType.NETWORK_ERROR if isinstance(e, ConnectionError) else ErrorType.TIMEOUT_ERROR
            error_msg = f'{error_type.value}: {str(e)}'
            logger.warning(f"[safe_request] Retry {current_retry}/{retry_count}: {error_msg}")

        except json.JSONDecodeError as e:
            last_error = e
            error_msg = f'JSON parse error: {str(e)}'
            logger.warning(f"[safe_request] {error_msg}")

            if error_strategy == ErrorStrategy.RAISE:
                raise ParseError(error_msg) from e

            return RequestResult(
                success=False,
                error=error_msg,
                error_type=ErrorType.PARSE_ERROR,
                retry_count=current_retry
            )

        except Exception as e:
            last_error = e
            error_msg = f'Unexpected error: {str(e)}'
            logger.error(f"[safe_request] {error_msg}")

            if error_strategy == ErrorStrategy.RAISE:
                raise

            return RequestResult(
                success=False,
                error=error_msg,
                error_type=ErrorType.UNKNOWN_ERROR,
                retry_count=current_retry
            )

        if current_retry >= retry_count:
            break

        current_retry += 1
        time.sleep(retry_delay)

    if error_strategy == ErrorStrategy.RAISE and last_error:
        raise last_error

    if error_strategy == ErrorStrategy.RETURN_DEFAULT:
        return RequestResult(
            success=False,
            response=default_response,
            error=str(last_error) if last_error else 'Max retries exceeded',
            error_type=ErrorType.UNKNOWN_ERROR,
            status_code=getattr(default_response, 'status_code', None),
            retry_count=retry_count
        )

    return RequestResult(
        success=False,
        error=str(last_error) if last_error else 'Max retries exceeded',
        error_type=ErrorType.UNKNOWN_ERROR,
        retry_count=retry_count
    )


# ==================== API 请求类 ====================

class APIRequest:
    """
    [CLASS] API 请求封装类
    [DESCRIPTION] 提供更友好的 API 请求接口

    Example:
        req = APIRequest(client, headers=default_headers)

        # GET 请求
        result = req.get('/api/v2/bo/user')
        if result.success:
            users = result.data.get('items', [])

        # POST 请求
        result = req.post('/api/v2/bo/user', json={'username': 'test'})
        if result.success:
            user_id = result.data['id']

        # 自动处理错误
        result = req.post('/api/v2/bo/user', json=data, raise_on_error=True)
    """

    def __init__(
        self,
        client,
        headers: Optional[Dict[str, str]] = None,
        default_timeout: int = 30,
        default_retry: int = 0,
        default_strategy: ErrorStrategy = ErrorStrategy.RAISE
    ):
        """
        [INIT] 初始化 API 请求器

        Args:
            client: Flask test client 或 HTTP client
            headers: 默认请求头
            default_timeout: 默认超时时间
            default_retry: 默认重试次数
            default_strategy: 默认错误策略
        """
        self.client = client
        self.default_headers = headers or {}
        self.default_timeout = default_timeout
        self.default_retry = default_retry
        self.default_strategy = default_strategy

    def _merge_headers(self, headers=None):
        """合并请求头"""
        if headers is None:
            return self.default_headers
        return {**self.default_headers, **headers}

    def _make_request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict] = None,
        timeout: Optional[int] = None,
        retry: Optional[int] = None,
        strategy: Optional[ErrorStrategy] = None,
        raise_on_error: bool = False,
        **kwargs
    ) -> RequestResult:
        """发送请求"""
        request_func = getattr(self.client, method)
        merged_headers = self._merge_headers(headers)

        return safe_request(
            request_func,
            url,
            headers=merged_headers,
            timeout=timeout or self.default_timeout,
            retry_count=retry if retry is not None else self.default_retry,
            error_strategy=strategy if strategy else self.default_strategy,
            **kwargs
        )

    def get(self, url: str, **kwargs) -> RequestResult:
        """GET 请求"""
        return self._make_request('get', url, **kwargs)

    def post(self, url: str, **kwargs) -> RequestResult:
        """POST 请求"""
        return self._make_request('post', url, **kwargs)

    def put(self, url: str, **kwargs) -> RequestResult:
        """PUT 请求"""
        return self._make_request('put', url, **kwargs)

    def delete(self, url: str, **kwargs) -> RequestResult:
        """DELETE 请求"""
        return self._make_request('delete', url, **kwargs)

    def patch(self, url: str, **kwargs) -> RequestResult:
        """PATCH 请求"""
        return self._make_request('patch', url, **kwargs)


# ==================== 自定义异常 ====================

class HTTPStatusError(Exception):
    """HTTP 状态码错误"""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class ParseError(Exception):
    """JSON 解析错误"""
    pass


class NetworkError(Exception):
    """网络错误"""
    pass


class TimeoutException(Exception):
    """超时错误"""
    pass


# ==================== 便捷函数 ====================

def get_json(response) -> Optional[Dict]:
    """
    [FUNCTION] 安全获取 JSON 响应
    [DESCRIPTION] 统一处理 JSON 解析错误

    Args:
        response: HTTP 响应对象

    Returns:
        dict 或 None: 解析后的数据
    """
    try:
        if hasattr(response, 'data'):
            return json.loads(response.data)
        if isinstance(response, str):
            return json.loads(response)
        return response
    except (json.JSONDecodeError, AttributeError, TypeError):
        return None


def check_response(
    response,
    expected_status: Optional[List[int]] = None,
    required_fields: Optional[List[str]] = None
) -> RequestResult:
    """
    [FUNCTION] 检查响应
    [DESCRIPTION] 统一验证响应状态码和字段

    Args:
        response: HTTP 响应对象
        expected_status: 期望的状态码列表
        required_fields: 必需的 JSON 字段

    Returns:
        RequestResult: 检查结果
    """
    if response is None:
        return RequestResult(
            success=False,
            error='Response is None',
            error_type=ErrorType.UNKNOWN_ERROR
        )

    status_code = getattr(response, 'status_code', None)
    data = get_json(response)

    if expected_status and status_code not in expected_status:
        return RequestResult(
            success=False,
            response=response,
            error=f'Status code {status_code} not in {expected_status}',
            error_type=ErrorType.HTTP_ERROR,
            status_code=status_code
        )

    if required_fields and data:
        missing_fields = [f for f in required_fields if f not in data]
        if missing_fields:
            return RequestResult(
                success=False,
                response=response,
                error=f'Missing fields: {missing_fields}',
                error_type=ErrorType.VALIDATION_ERROR,
                status_code=status_code
            )

    return RequestResult(
        success=True,
        response=response,
        status_code=status_code
    )
