# [DEPRECATED] 废弃规范目录

> 最后更新: 2026-06-07 | 状态: 已废弃

## 警告

**此目录下的所有文件已废弃，禁止作为执行规范参考。**

## 废弃文件清单

| 文件 | 废弃原因 | 替代方案 |
|------|---------|---------|
| `mcp-testing.md` | MCP 浏览器工具全面禁用 | `PlaywrightCLI` (test_helpers/browser_auth_cli.py) |
| `mcp-parallel-integration.md` | MCP 多实例方案废弃 | `PlaywrightCLI` (天然进程级隔离) |
| `multi-agent-browser-isolation.md` | session_manager 废弃 | `PlaywrightCLI` (无需 session_manager) |
| `multi-agent-quickstart.md` | 旧版多智能体指南 | `multi-agent-coordination.md` |

## 替代方案

### 浏览器测试（统一入口）

```python
import sys; sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-table')
```

### 多智能体协作

参考活跃规范：[../multi-agent-coordination.md](../multi-agent-coordination.md)

## 规则来源

`.trae/rules/SESSION_REMINDER.md` 顶部「浏览器测试铁律」

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-07 | AI Assistant | 移动 4 个废弃规范到此目录，统一管理 |
