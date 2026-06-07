"""
test_tools.py - M10 v1.1.0 MCP Tools 测试
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class TestMCPToolBase(unittest.TestCase):
    """MCPTool 基类测试"""

    def test_subclass_implements_execute(self):
        """子类必须实现 execute"""
        from mcp.tools import MCPTool
        tool = MCPTool(name='t', description='d', input_schema={'type': 'object'})
        with self.assertRaises(NotImplementedError):
            tool.execute()


class TestGetEntityByIdTool(unittest.TestCase):
    """GetEntityByIdTool 测试"""

    def setUp(self):
        from mcp.tools import reset_tools_cache
        reset_tools_cache()

    def tearDown(self):
        from mcp.tools import reset_tools_cache
        reset_tools_cache()

    def test_creates_user_tool(self):
        """创建 User tool"""
        from mcp.tools import GetEntityByIdTool
        tool = GetEntityByIdTool('User', {'object_type': 'user', 'fields': ['id', 'name']})
        self.assertEqual(tool.name, 'get_user_by_id')
        self.assertIn('id', tool.input_schema['properties'])

    def test_creates_order_tool(self):
        """创建 Order tool"""
        from mcp.tools import GetEntityByIdTool
        tool = GetEntityByIdTool('Order', {'object_type': 'order', 'fields': ['id']})
        self.assertEqual(tool.name, 'get_order_by_id')

    def test_to_mcp_dict(self):
        """转 MCP 协议 dict"""
        from mcp.tools import GetEntityByIdTool
        tool = GetEntityByIdTool('User', {'object_type': 'user', 'fields': []})
        d = tool.to_mcp_dict()
        self.assertEqual(d['name'], 'get_user_by_id')
        self.assertIn('description', d)
        self.assertIn('inputSchema', d)

    def test_execute_returns_dict(self):
        """execute 返回 dict"""
        from mcp.tools import GetEntityByIdTool
        tool = GetEntityByIdTool('User', {'object_type': 'user', 'fields': []})
        result = tool.execute(id=5, user_context={'id': 1, 'roles': ['admin']})
        self.assertIn('tool', result)
        self.assertIn('entity', result)
        # TODO-7 包装后 result 含 'allowed' / 'rls_applied'
        self.assertIn('allowed', result)
        self.assertTrue(result['allowed'])
        # 内部 raw_result 含 id
        self.assertIn('result', result)
        # result 是字符串，不是 dict 含 id
        self.assertIn('User', str(result['result']))


class TestListEntityTool(unittest.TestCase):
    """ListEntityTool 测试"""

    def setUp(self):
        from mcp.tools import reset_tools_cache
        from rls.loader import RLSLoader
        from rls import loader as loader_mod
        reset_tools_cache()
        RLSLoader._instance = None
        RLSLoader._rules = {}
        RLSLoader._mtimes = {}
        RLSLoader._rules_dir = None
        loader_mod.get_loader('rls_rules')

    def tearDown(self):
        from mcp.tools import reset_tools_cache
        reset_tools_cache()

    def test_creates_user_list_tool(self):
        """创建 User list tool"""
        from mcp.tools import ListEntityTool
        tool = ListEntityTool('User', {'object_type': 'user', 'fields': []})
        self.assertEqual(tool.name, 'list_user')

    def test_default_limit(self):
        """默认 limit=20"""
        from mcp.tools import ListEntityTool
        tool = ListEntityTool('User', {'object_type': 'user', 'fields': []})
        self.assertEqual(tool.input_schema['properties']['limit']['default'], 20)

    def test_execute_with_defaults(self):
        """execute 默认值（admin 角色无 RLS 限制）"""
        from mcp.tools import ListEntityTool
        tool = ListEntityTool('User', {'object_type': 'user', 'fields': []})
        result = tool.execute(user_context={'id': 1, 'roles': ['admin']})
        self.assertTrue(result['allowed'])
        # result 内部含 'limit' / 'offset' 字符串
        self.assertIn('limit', str(result))

    def test_execute_with_filter(self):
        """execute 带 filter（admin 角色）"""
        from mcp.tools import ListEntityTool
        tool = ListEntityTool('User', {'object_type': 'user', 'fields': []})
        result = tool.execute(
            limit=10, offset=5, filter={'status': 'active'},
            user_context={'id': 1, 'roles': ['admin']},
        )
        self.assertTrue(result['allowed'])
        # raw_result 中 filter 字段应被保留
        self.assertIn('filter', result)
        self.assertEqual(result['filter'], {'status': 'active'})


class TestGetAllTools(unittest.TestCase):
    """get_all_tools 测试"""

    def setUp(self):
        from mcp.tools import reset_tools_cache
        reset_tools_cache()

    def tearDown(self):
        from mcp.tools import reset_tools_cache
        reset_tools_cache()

    def test_10_entities_20_tools(self):
        """10 entity × 2 = 20 tools"""
        from mcp.tools import get_all_tools
        tools = get_all_tools()
        self.assertEqual(len(tools), 20)

    def test_each_entity_has_get_and_list(self):
        """每个 entity 有 get + list"""
        from mcp.tools import get_all_tools
        tools = get_all_tools()
        # 应该有 get_*_by_id 和 list_*
        get_tools = [t for t in tools if t.name.startswith('get_')]
        list_tools = [t for t in tools if t.name.startswith('list_')]
        self.assertEqual(len(get_tools), 10)
        self.assertEqual(len(list_tools), 10)

    def test_get_tool_by_name(self):
        """通过 name 查询"""
        from mcp.tools import get_all_tools, get_tool_by_name
        get_all_tools()  # 触发缓存
        tool = get_tool_by_name('get_user_by_id')
        self.assertIsNotNone(tool)
        self.assertEqual(tool.name, 'get_user_by_id')

    def test_get_tool_by_name_not_found(self):
        """未找到返回 None"""
        from mcp.tools import get_all_tools, get_tool_by_name
        get_all_tools()
        tool = get_tool_by_name('non_existent')
        self.assertIsNone(tool)


if __name__ == '__main__':
    unittest.main()
