"""
mcp/tools.py - M10 v1.1.0 MCP 工具（从 M9 ENTITY_SCHEMAS 派生）

策略：每个 entity 自动派生 2 个 tool
- get_{entity_name}_by_id
- list_{entity_name}

10 entity × 2 tool = 20 tools（与 spec 一致）
"""
import logging
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


# ==================== Tool 基类 ====================

class MCPTool:
    """MCP 工具基类

    每个 tool 有：
    - name: 工具名（Claude/Cursor 调用时用）
    - description: 工具描述
    - inputSchema: 参数 JSON Schema
    - execute: 实际执行（业务逻辑）
    """

    def __init__(self, name: str, description: str, input_schema: dict):
        self.name = name
        self.description = description
        self.input_schema = input_schema

    def execute(self, **kwargs) -> Any:
        """执行工具（子类实现）"""
        raise NotImplementedError

    def to_mcp_dict(self) -> dict:
        """转 MCP 协议 dict"""
        return {
            'name': self.name,
            'description': self.description,
            'inputSchema': self.input_schema,
        }


class GetEntityByIdTool(MCPTool):
    """get_{entity}_by_id 工具

    自动从 ENTITY_SCHEMAS 派生 description + inputSchema
    """

    def __init__(self, entity_name: str, entity_def: dict):
        self._entity_name = entity_name
        self._entity_def = entity_def
        super().__init__(
            name=f'get_{entity_name.lower()}_by_id',
            description=f'Get a single {entity_name} by its ID. Returns the full {entity_name} object with all fields.',
            input_schema={
                'type': 'object',
                'properties': {
                    'id': {
                        'type': 'integer',
                        'description': f'The ID of the {entity_name} to retrieve',
                    },
                },
                'required': ['id'],
            },
        )

    def execute(self, id: int, user_context: dict = None) -> dict:
        """执行：调用 M9 GraphQL get{entity}（mock 模式 + M11 RLS 自动应用）

        实际部署时替换为真实 GraphQL 调用：
            from meta.graphql import execute_query
            query = f'query {{ get{self._entity_name}(id: {id}) {{ ... }} }}'
            return execute_query(query)

        [DECORATIVE] M11 RLS 自动集成（TODO-7）：
        - user_context 含 'ai_agent: true' → 自动添加 'ai-agent' 角色
        - check_action() 检查 action 权限
        - apply_field_masks() 脱敏敏感字段
        """
        from mcp.rls_integration import apply_rls_to_result
        # Mock 模式：返回工具调用上下文（不实际查 DB）
        raw_result = {
            'tool': self.name,
            'entity': self._entity_name,
            'id': id,
            'result': f'Mock: {self._entity_name}#{id} (use real GraphQL endpoint)',
        }
        # 应用 M11 RLS（行级 + 字段级）
        return apply_rls_to_result(
            entity=self._entity_name.lower(),
            action='read',
            user_context=user_context or {},
            raw_result=raw_result,
        )


class ListEntityTool(MCPTool):
    """list_{entity} 工具

    支持 limit / offset / filter 参数
    """

    def __init__(self, entity_name: str, entity_def: dict):
        self._entity_name = entity_name
        self._entity_def = entity_def
        super().__init__(
            name=f'list_{entity_name.lower()}',
            description=f'List {entity_name} objects with pagination and optional filtering. Returns an array of {entity_name} objects.',
            input_schema={
                'type': 'object',
                'properties': {
                    'limit': {
                        'type': 'integer',
                        'description': 'Maximum number of objects to return (default 20, max 100)',
                        'default': 20,
                        'minimum': 1,
                        'maximum': 100,
                    },
                    'offset': {
                        'type': 'integer',
                        'description': 'Number of objects to skip for pagination (default 0)',
                        'default': 0,
                        'minimum': 0,
                    },
                    'filter': {
                        'type': 'object',
                        'description': 'Optional filter object (e.g., {"status": "active"})',
                    },
                },
            },
        )

    def execute(self, limit: int = 20, offset: int = 0, filter: Optional[dict] = None, user_context: dict = None) -> dict:
        """执行：调用 M9 GraphQL list{entity}（mock 模式 + M11 RLS 自动应用）

        [DECORATIVE] M11 RLS 自动集成（TODO-7）：同 GetEntityByIdTool
        """
        from mcp.rls_integration import apply_rls_to_result
        raw_result = {
            'tool': self.name,
            'entity': self._entity_name,
            'limit': limit,
            'offset': offset,
            'filter': filter or {},
            'result': f'Mock: list {self._entity_name} (limit={limit}, offset={offset})',
        }
        return apply_rls_to_result(
            entity=self._entity_name.lower(),
            action='read',
            user_context=user_context or {},
            raw_result=raw_result,
        )


# ==================== Tool 注册表 ====================

_tools_cache: Optional[List[MCPTool]] = None


def get_all_tools() -> List[MCPTool]:
    """获取所有 tool（从 M9 ENTITY_SCHEMAS 派生）"""
    global _tools_cache
    if _tools_cache is not None:
        return _tools_cache

    from meta.graphql import ENTITY_SCHEMAS

    tools = []
    for entity_name, entity_def in ENTITY_SCHEMAS.items():
        # 派生 get_{entity}_by_id
        tools.append(GetEntityByIdTool(entity_name, entity_def))
        # 派生 list_{entity}
        tools.append(ListEntityTool(entity_name, entity_def))

    _tools_cache = tools
    logger.info(f'[MCP] Built {len(tools)} tools from {len(ENTITY_SCHEMAS)} entities')
    return tools


def get_tool_by_name(name: str) -> Optional[MCPTool]:
    """通过 name 查询 tool"""
    for tool in get_all_tools():
        if tool.name == name:
            return tool
    return None


def reset_tools_cache() -> None:
    """重置缓存（测试用）"""
    global _tools_cache
    _tools_cache = None
