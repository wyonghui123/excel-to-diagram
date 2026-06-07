"""
test_server.py - M10 v1.1.0 MCP HTTP Server 测试
"""
import os
import sys
import unittest
import json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestMCPServer(unittest.TestCase):
    """MCP HTTP Server 测试"""

    def setUp(self):
        from flask import Flask
        from mcp.server import mcp_bp
        from mcp.tools import reset_tools_cache
        reset_tools_cache()
        self.app = Flask(__name__)
        self.app.register_blueprint(mcp_bp)
        self.client = self.app.test_client()

    def tearDown(self):
        from mcp.tools import reset_tools_cache
        reset_tools_cache()

    def test_get_info(self):
        """GET /mcp 返回 server info"""
        resp = self.client.get('/mcp')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['name'], 'v3-engine-mcp')
        self.assertEqual(data['protocol'], 'mcp-2024-11-05')
        self.assertEqual(data['tools_count'], 20)

    def test_get_tools(self):
        """GET /mcp/tools 列出所有 tools"""
        resp = self.client.get('/mcp/tools')
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['count'], 20)

    def test_post_initialize(self):
        """POST /mcp initialize"""
        resp = self.client.post(
            '/mcp',
            json={'jsonrpc': '2.0', 'method': 'initialize', 'id': '1'},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data['jsonrpc'], '2.0')
        self.assertIn('result', data)
        self.assertEqual(data['result']['protocolVersion'], '2024-11-05')

    def test_post_ping(self):
        """POST /mcp ping"""
        resp = self.client.post(
            '/mcp',
            json={'jsonrpc': '2.0', 'method': 'ping', 'id': '2'},
        )
        data = resp.get_json()
        self.assertIn('result', data)

    def test_post_tools_list(self):
        """POST /mcp tools/list"""
        resp = self.client.post(
            '/mcp',
            json={'jsonrpc': '2.0', 'method': 'tools/list', 'id': '3'},
        )
        data = resp.get_json()
        self.assertIn('tools', data['result'])
        self.assertEqual(len(data['result']['tools']), 20)

    def test_post_tools_call(self):
        """POST /mcp tools/call 调用 get_user_by_id"""
        resp = self.client.post(
            '/mcp',
            json={
                'jsonrpc': '2.0',
                'method': 'tools/call',
                'params': {
                    'name': 'get_user_by_id',
                    'arguments': {'id': 5},
                },
                'id': '4',
            },
        )
        data = resp.get_json()
        self.assertIn('result', data)
        self.assertIn('content', data['result'])
        self.assertEqual(data['result']['isError'], False)

    def test_post_tools_call_unknown_tool(self):
        """POST /mcp tools/call 未知工具"""
        resp = self.client.post(
            '/mcp',
            json={
                'jsonrpc': '2.0',
                'method': 'tools/call',
                'params': {'name': 'unknown', 'arguments': {}},
                'id': '5',
            },
        )
        data = resp.get_json()
        # 工具未找到 → result.isError=true
        self.assertIn('result', data)
        self.assertEqual(data['result']['isError'], True)

    def test_post_invalid_json(self):
        """POST /mcp 非法 JSON"""
        resp = self.client.post(
            '/mcp',
            data='not json',
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == '__main__':
    unittest.main()
