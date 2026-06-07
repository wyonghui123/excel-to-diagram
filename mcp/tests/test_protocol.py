"""
test_protocol.py - M10 v1.1.0 MCP 协议层测试
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestJSONRPCRequest(unittest.TestCase):
    """JSONRPCRequest 测试"""

    def test_create_request(self):
        """创建请求"""
        from mcp.protocol import JSONRPCRequest
        req = JSONRPCRequest(method='test', params={'k': 'v'})
        self.assertEqual(req.method, 'test')
        self.assertEqual(req.params, {'k': 'v'})
        self.assertIsNotNone(req.id)

    def test_to_dict(self):
        """转 dict"""
        from mcp.protocol import JSONRPCRequest
        req = JSONRPCRequest(method='test', id='abc')
        d = req.to_dict()
        self.assertEqual(d['jsonrpc'], '2.0')
        self.assertEqual(d['method'], 'test')
        self.assertEqual(d['id'], 'abc')

    def test_from_dict(self):
        """从 dict 解析"""
        from mcp.protocol import JSONRPCRequest
        data = {
            'jsonrpc': '2.0',
            'method': 'tools/list',
            'params': {},
            'id': 'xyz',
        }
        req = JSONRPCRequest.from_dict(data)
        self.assertEqual(req.method, 'tools/list')
        self.assertEqual(req.id, 'xyz')

    def test_from_dict_invalid_jsonrpc(self):
        """非法 jsonrpc 抛错"""
        from mcp.protocol import JSONRPCRequest
        with self.assertRaises(ValueError):
            JSONRPCRequest.from_dict({'method': 'test'})

    def test_from_dict_missing_method(self):
        """缺 method 抛错"""
        from mcp.protocol import JSONRPCRequest
        with self.assertRaises(ValueError):
            JSONRPCRequest.from_dict({'jsonrpc': '2.0'})


class TestJSONRPCResponse(unittest.TestCase):
    """JSONRPCResponse 测试"""

    def test_success_response(self):
        """成功响应"""
        from mcp.protocol import JSONRPCResponse
        resp = JSONRPCResponse.success('id1', {'key': 'value'})
        d = resp.to_dict()
        self.assertEqual(d['jsonrpc'], '2.0')
        self.assertEqual(d['id'], 'id1')
        self.assertEqual(d['result'], {'key': 'value'})
        self.assertNotIn('error', d)

    def test_failure_response(self):
        """失败响应"""
        from mcp.protocol import JSONRPCResponse
        resp = JSONRPCResponse.failure('id1', -32600, 'Invalid request')
        d = resp.to_dict()
        self.assertEqual(d['error']['code'], -32600)
        self.assertEqual(d['error']['message'], 'Invalid request')
        self.assertNotIn('result', d)


class TestHandleRequest(unittest.TestCase):
    """handle_request 统一入口测试"""

    def test_initialize_method(self):
        """initialize 方法"""
        from mcp.protocol import handle_request
        response = handle_request({
            'jsonrpc': '2.0',
            'method': 'initialize',
            'id': '1',
        })
        self.assertIn('result', response)
        self.assertEqual(response['result']['protocolVersion'], '2024-11-05')
        self.assertIn('serverInfo', response['result'])

    def test_ping_method(self):
        """ping 方法"""
        from mcp.protocol import handle_request
        response = handle_request({
            'jsonrpc': '2.0',
            'method': 'ping',
            'id': '2',
        })
        self.assertIn('result', response)

    def test_unknown_method(self):
        """未知方法返回错误"""
        from mcp.protocol import handle_request
        response = handle_request({
            'jsonrpc': '2.0',
            'method': 'unknown/method',
            'id': '3',
        })
        self.assertIn('error', response)
        self.assertEqual(response['error']['code'], -32601)

    def test_invalid_request(self):
        """非法请求返回错误"""
        from mcp.protocol import handle_request
        response = handle_request({'method': 'test'})  # 缺 jsonrpc
        self.assertIn('error', response)
        self.assertEqual(response['error']['code'], -32600)


if __name__ == '__main__':
    unittest.main()
