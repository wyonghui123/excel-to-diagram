# Claude / Cursor 集成 M10 v3 Engine MCP Server

> **版本**: v1.0.0
> **创建日期**: 2026-06-06
> **状态**: ✅ M10 MCP Server 实施完成 / 32 测试 PASS

---

## 概述

M10 MCP Server 把 v3 引擎的 10 entity 暴露为 20 个 MCP tools，可被 Claude Desktop / Cursor / 其他 MCP 客户端直接调用。

**Server 信息**：
- 名称: `v3-engine-mcp`
- 版本: 1.0.0
- 协议: MCP 2024-11-05
- 工具数: 20（10 entity × 2 tool = get + list）

---

## Claude Desktop 集成

### Step 1: 启动 MCP Server

```bash
# 方式 1：直接运行（开发模式）
cd d:/filework/excel-to-diagram
python -m mcp.server

# 方式 2：通过 HTTP 端点
# POST http://localhost:5000/mcp
# GET  http://localhost:5000/mcp/info
```

### Step 2: 配置 Claude Desktop

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "v3-engine": {
      "command": "python",
      "args": [
        "-m",
        "mcp.server"
      ],
      "cwd": "d:/filework/excel-to-diagram",
      "env": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}
```

### Step 3: 验证

重启 Claude Desktop，发送消息：

> 帮我查看所有可用的 v3 引擎 tools

Claude 应返回 20 个 tools 列表（get_user_by_id / list_user / 等）。

### Step 4: 使用示例

> 帮我获取 id=5 的 user 信息

Claude 应自动调用 `get_user_by_id(id=5)` 并返回结果。

---

## Cursor 集成

### Step 1: 配置 Cursor MCP

**文件**: `~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "v3-engine": {
      "url": "http://localhost:5000/mcp"
    }
  }
}
```

### Step 2: 验证

在 Cursor 中按 `Ctrl+L`（或 `Cmd+L`）打开 Chat，输入：

> 列出所有 v3 engine tools

应显示 20 个 tools。

---

## HTTP 端点

### GET /mcp - Server Info

```bash
curl http://localhost:5000/mcp
```

返回：
```json
{
  "name": "v3-engine-mcp",
  "version": "1.0.0",
  "protocol": "mcp-2024-11-05",
  "tools_count": 20,
  "tools": [...]
}
```

### GET /mcp/tools - Tool 列表

```bash
curl http://localhost:5000/mcp/tools
```

### POST /mcp - JSON-RPC 2.0 调用

```bash
# 列出 tools
curl -X POST http://localhost:5000/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":"1"}'

# 调用 tool
curl -X POST http://localhost:5000/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "method":"tools/call",
    "params":{
      "name":"get_user_by_id",
      "arguments":{"id":5}
    },
    "id":"2"
  }'
```

---

## 20 Tools 列表

| Entity | Get Tool | List Tool |
|--------|----------|-----------|
| User | `get_user_by_id` | `list_user` |
| Order | `get_order_by_id` | `list_order` |
| Product | `get_product_by_id` | `list_product` |
| Role | `get_role_by_id` | `list_role` |
| UserGroup | `get_user_group_by_id` | `list_user_group` |
| BusinessObject | `get_business_object_by_id` | `list_business_object` |
| Version | `get_version_by_id` | `list_version` |
| Domain | `get_domain_by_id` | `list_domain` |
| SubDomain | `get_sub_domain_by_id` | `list_sub_domain` |
| ServiceModule | `get_service_module_by_id` | `list_service_module` |

---

## 集成到 server.py（生产模式）

在 `meta/core/app_builder.py` 注册 mcp_bp（不修改 server.py 主体，仅追加）：

```python
# 末尾追加 +3 行
from mcp.server import mcp_bp
app.register_blueprint(mcp_bp)
```

---

## 故障排查

### Issue 1: Claude Desktop 看不到 tools

**症状**: 重启 Claude Desktop 后，tools 列表为空

**解决**:
1. 检查 `claude_desktop_config.json` 路径正确
2. 检查 `cwd` 路径正确
3. 在终端跑 `python -m mcp.server` 看是否有错误
4. 重启 Claude Desktop

### Issue 2: 调用返回 "Unknown tool"

**症状**: 调用 `get_user_by_id` 返回错误

**解决**:
- 检查 M9 ENTITY_SCHEMAS 包含 User entity
- 检查 `python -c "from mcp.tools import get_all_tools; print(len(get_all_tools()))"` 输出 20

### Issue 3: 执行失败

**当前是 mock 模式**：返回 `{tool, entity, id, result: 'Mock: ...'}`，不实际查 DB。

**启用真实执行**：
1. 编辑 `mcp/tools.py` 的 `GetEntityByIdTool.execute`：
   ```python
   def execute(self, id: int) -> dict:
       from meta.graphql import execute_query
       query = f'query {{ get{self._entity_name}(id: {id}) {{ ... }} }}'
       return execute_query(query)
   ```
2. 重启 server

---

## 安全注意事项

1. **公开部署前加认证**：当前 0 鉴权（仅开发用）
2. **审计日志**：建议接入 M14 Telemetry
3. **限流**：建议接入 M11 RLS 行级权限
4. **HTTPS**：生产部署必加

---

## 关联文档

- [spec-m10-mcp-server.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-m10-mcp-server.md) - 详细 spec
- [spec-m9-graphql-protocol.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-m9-graphql-protocol.md) - M9 GraphQL（SSOT）
- [spec-m11-rls.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-m11-rls.md) - M11 RLS（安全）
- [spec-m14-opentelemetry.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-m14-opentelemetry.md) - M14 Telemetry（监控）
