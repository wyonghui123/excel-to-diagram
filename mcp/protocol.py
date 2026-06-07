"""
mcp/protocol.py - M10 v1.1.0 MCP 协议层（JSON-RPC 2.0）

MCP（Model Context Protocol）= Anthropic 提出的 AI Agent 工具调用协议
基于 JSON-RPC 2.0，通过 stdio / HTTP / SSE 传输

简化实现：
- 支持 tools/list + tools/call 两种方法
- 支持 initialize / ping
- 0 依赖（仅 stdlib）
"""
import json
import logging
import uuid
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


# JSON-RPC 2.0 标准错误码
JSON_RPC_ERRORS = {
    -32700: 'Parse error',
    -32600: 'Invalid Request',
    -32601: 'Method not found',
    -32602: 'Invalid params',
    -32603: 'Internal error',
    -32000: 'Server error (custom)',
}


class JSONRPCRequest:
    """JSON-RPC 2.0 请求"""
    def __init__(self, method: str, params: Optional[dict] = None, id: Optional[str] = None):
        self.method = method
        self.params = params or {}
        self.id = id or str(uuid.uuid4())
        self.jsonrpc = '2.0'

    def to_dict(self) -> dict:
        return {
            'jsonrpc': self.jsonrpc,
            'method': self.method,
            'params': self.params,
            'id': self.id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'JSONRPCRequest':
        """从 dict 解析"""
        if not isinstance(data, dict):
            raise ValueError('Request must be a dict')
        if data.get('jsonrpc') != '2.0':
            raise ValueError('jsonrpc must be 2.0')
        if 'method' not in data:
            raise ValueError('method is required')
        return cls(
            method=data['method'],
            params=data.get('params', {}),
            id=data.get('id', str(uuid.uuid4())),
        )


class JSONRPCResponse:
    """JSON-RPC 2.0 响应"""
    def __init__(self, id: str, result: Any = None, error: Optional[dict] = None):
        self.jsonrpc = '2.0'
        self.id = id
        self.result = result
        self.error = error

    def to_dict(self) -> dict:
        response = {'jsonrpc': self.jsonrpc, 'id': self.id}
        if self.error is not None:
            response['error'] = self.error
        else:
            response['result'] = self.result
        return response

    @classmethod
    def success(cls, id: str, result: Any) -> 'JSONRPCResponse':
        return cls(id=id, result=result)

    @classmethod
    def failure(cls, id: str, code: int, message: str, data: Any = None) -> 'JSONRPCResponse':
        error = {'code': code, 'message': message}
        if data is not None:
            error['data'] = data
        return cls(id=id, error=error)


# ==================== MCP 方法处理 ====================

def handle_initialize(request: JSONRPCRequest) -> JSONRPCResponse:
    """MCP initialize 方法

    Returns:
        {
            'protocolVersion': '2024-11-05',
            'capabilities': {'tools': {}},
            'serverInfo': {
                'name': 'v3-engine-mcp',
                'version': '1.0.0',
            },
        }
    """
    return JSONRPCResponse.success(request.id, {
        'protocolVersion': '2024-11-05',
        'capabilities': {
            'tools': {},  # 支持工具调用
        },
        'serverInfo': {
            'name': 'v3-engine-mcp',
            'version': '1.0.0',
        },
    })


def handle_ping(request: JSONRPCRequest) -> JSONRPCResponse:
    """MCP ping 方法（心跳）"""
    return JSONRPCResponse.success(request.id, {})


def handle_tools_list(request: JSONRPCRequest) -> JSONRPCResponse:
    """MCP tools/list 方法：列出所有可用工具

    Returns:
        {
            'tools': [
                {
                    'name': 'get_user_by_id',
                    'description': '...',
                    'inputSchema': {...},
                },
                ...
            ],
        }
    """
    from .tools import get_all_tools
    tools = get_all_tools()
    return JSONRPCResponse.success(request.id, {
        'tools': [t.to_mcp_dict() for t in tools],
    })


def handle_tools_call(request: JSONRPCRequest) -> JSONRPCResponse:
    """MCP tools/call 方法：调用工具

    Params:
        {
            'name': 'get_user_by_id',
            'arguments': {'id': 5},
        }

    Returns:
        {
            'content': [
                {'type': 'text', 'text': '...JSON...'},
            ],
            'isError': False,
        }
    """
    from .tools import get_tool_by_name
    params = request.params or {}
    name = params.get('name')
    arguments = params.get('arguments', {})

    if not name:
        return JSONRPCResponse.success(request.id, {
            'content': [{'type': 'text', 'text': 'Error: Missing tool name'}],
            'isError': True,
        })

    tool = get_tool_by_name(name)
    if tool is None:
        return JSONRPCResponse.success(request.id, {
            'content': [{'type': 'text', 'text': f'Error: Unknown tool: {name}'}],
            'isError': True,
        })

    try:
        result = tool.execute(**arguments)
        return JSONRPCResponse.success(request.id, {
            'content': [
                {'type': 'text', 'text': json.dumps(result, ensure_ascii=False, default=str)},
            ],
            'isError': False,
        })
    except Exception as e:
        logger.error(f'[MCP] Tool {name} failed: {e}')
        return JSONRPCResponse.success(request.id, {
            'content': [
                {'type': 'text', 'text': f'Error: {str(e)}'},
            ],
            'isError': True,
        })


# ==================== 主入口 ====================

# 方法路由表
METHOD_HANDLERS = {
    'initialize': handle_initialize,
    'ping': handle_ping,
    'tools/list': handle_tools_list,
    'tools/call': handle_tools_call,
}


def handle_request(request_data: dict) -> dict:
    """统一入口：处理 JSON-RPC 2.0 请求

    Args:
        request_data: 原始 dict（从 JSON 解析）

    Returns:
        dict: 响应 dict（序列化为 JSON）
    """
    try:
        request = JSONRPCRequest.from_dict(request_data)
    except ValueError as e:
        return JSONRPCResponse.failure(
            id=request_data.get('id', 'unknown'),
            code=-32600,
            message=f'Invalid Request: {e}',
        ).to_dict()

    handler = METHOD_HANDLERS.get(request.method)
    if handler is None:
        return JSONRPCResponse.failure(
            request.id, -32601, f'Method not found: {request.method}',
        ).to_dict()

    try:
        response = handler(request)
        return response.to_dict()
    except Exception as e:
        logger.exception(f'[MCP] Handler error: {e}')
        return JSONRPCResponse.failure(
            request.id, -32603, f'Internal error: {e}',
        ).to_dict()


def handle_batch(requests: List[dict]) -> List[dict]:
    """批量请求处理"""
    return [handle_request(req) for req in requests]
