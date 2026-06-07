# AI 编码规范

> 最后更新: 2026-06-07 | 状态: 活跃
> 拆分自 project_rules.md（原第 359-394 行）+ ai-coding-standards.md

## 核心原则

### 1. [FORBIDDEN] 禁止使用任何 Emoji 符号

- 适用范围：代码、配置、文档、注释、提交信息
- 原因：可能导致编码错误、解析问题、显示异常
- 替代方案：使用纯 ASCII 文本标记（如 `[WARNING]`、`[OK]`、`[X]`）

### 2. YonDesign 设计规范必须遵守

- 主色调：YonDesign Orange (#ea580c 橙色系)
- 颜色值：必须使用 CSS 变量，禁止硬编码
- 参考文档：`src/styles/YON_DESIGN_CONSTANTS.md`

### 3. 代码质量标准

- 注释：使用标准文本标记，不使用 Emoji
- 命名：语义化、一致性、可读性
- 文档：符合 Markdown 规范

## 违规后果

- **轻微违规**：需要立即修正并记录到设计决策清单
- **严重违规**：可能导致构建失败或运行时错误
- **重复违规**：将影响 AI 智能体的可信度评估

## 检查命令

```bash
# 检测 Emoji 使用
grep -rP '[\x{1F600}-\x{1F64F}]' src/ docs/ --include="*.md" --include="*.js" --include="*.vue"

# 检测硬编码颜色
grep -rn '#1677ff\|#1890ff' src/styles/
```

## 智能体角色体系

**详细规则见** [./agent-roles.md](./agent-roles.md) 规则3（角色Context加载规则）

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

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-07 | AI Assistant | 从 project_rules.md 拆分 + 合并 ai-coding-standards.md |
