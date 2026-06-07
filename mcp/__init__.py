"""
mcp - M10 v3 引擎：MCP Server（Model Context Protocol）

基于实际代码（M9 ENTITY_SCHEMAS + 10 entity）：
- mcp/protocol.py: JSON-RPC 2.0 协议 + 4 个 MCP 方法
- mcp/tools.py: 10 entity × 2 tool = 20 tools 自动派生
- mcp/server.py: POST /mcp + GET /mcp 端点
- mcp/rls_integration.py: M11 RLS 自动集成（TODO-7）[DECORATIVE]

回滚：删除 mcp/ 目录 + 移除 blueprint 注册即可
"""
import logging
from .protocol import (
    JSONRPCRequest,
    JSONRPCResponse,
    handle_request,
    handle_batch,
)
from .tools import (
    MCPTool,
    GetEntityByIdTool,
    ListEntityTool,
    get_all_tools,
    get_tool_by_name,
    reset_tools_cache,
)
from .rls_integration import (
    apply_rls_to_result,
    _normalize_user_context,
)
from .server import mcp_bp

logger = logging.getLogger(__name__)

__all__ = [
    'JSONRPCRequest',
    'JSONRPCResponse',
    'handle_request',
    'handle_batch',
    'MCPTool',
    'GetEntityByIdTool',
    'ListEntityTool',
    'get_all_tools',
    'get_tool_by_name',
    'reset_tools_cache',
    'apply_rls_to_result',
    '_normalize_user_context',
    'mcp_bp',
]

__version__ = '1.1.0'
