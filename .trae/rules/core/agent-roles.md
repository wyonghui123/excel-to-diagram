# 智能体角色与 Skills 体系

> 最后更新: 2026-06-07 | 状态: 活跃

## 智能体角色体系

**详细规则见** [../context-usage.md](../context-usage.md) 规则3（角色Context加载规则）

角色定义见 `.trae/roles/` 目录，关键要点：

- 根据用户意图自动识别角色并加载专属Context
- 跨角色协作时必须声明角色切换
- PM场景功能开发必须遵循 `.trae/context/pm/` 中的用户画像和设计原则

## Skills 铁律

- 实现功能前 → **test-driven-development**
- 复杂任务拆分 → **subagent-driven-development**
- 宣称完成前 → **verification-before-completion**（无证据不完成！）

## MCP 工具

项目已配置（`.trae/mcp.json`）：

- **Context7**：实时获取库文档，prompt末尾加 `use context7`
- **SQLite**：直接查询 architecture.db 元模型数据

## 会话间一致性

详见 [./checklist.md](./checklist.md) 中的"会话间一致性保证机制"。

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-07 | AI Assistant | 创建 |
