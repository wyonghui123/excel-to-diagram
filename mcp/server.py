"""
mcp/server.py - M10 v1.1.0 MCP HTTP Server

简化实现：
- POST /mcp 接收 JSON-RPC 2.0 请求
- GET /mcp 返回 server info
- 0 业务代码破坏

回滚：删除 mcp/ 目录 + app_builder.py 中 blueprint 注册即可
"""
import json
import logging
from flask import Blueprint, request, jsonify, Response

from .protocol import handle_request, handle_batch

logger = logging.getLogger(__name__)

mcp_bp = Blueprint('mcp', __name__, url_prefix='/mcp')


@mcp_bp.route('', methods=['POST'])
def mcp_post():
    """POST /mcp 端点

    接收 JSON-RPC 2.0 请求（单条或批量）
    """
    try:
        data = request.get_json(force=True, silent=False)
    except Exception as e:
        return jsonify({
            'jsonrpc': '2.0',
            'id': None,
            'error': {'code': -32700, 'message': f'Parse error: {e}'},
        }), 400

    if isinstance(data, list):
        # 批量请求
        responses = handle_batch(data)
        # 过滤全为通知（无 id）的响应
        return jsonify(responses)
    else:
        # 单条请求
        response = handle_request(data)
        return jsonify(response)


@mcp_bp.route('', methods=['GET'])
def mcp_info():
    """GET /mcp 返回 server info"""
    from .tools import get_all_tools
    tools = get_all_tools()
    return jsonify({
        'name': 'v3-engine-mcp',
        'version': '1.0.0',
        'protocol': 'mcp-2024-11-05',
        'tools_count': len(tools),
        'tools': [t.to_mcp_dict() for t in tools],
    })


@mcp_bp.route('/tools', methods=['GET'])
def mcp_list_tools():
    """GET /mcp/tools 列出所有 tools"""
    from .tools import get_all_tools
    tools = get_all_tools()
    return jsonify({
        'count': len(tools),
        'tools': [t.to_mcp_dict() for t in tools],
    })
