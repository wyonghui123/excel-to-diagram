---
name: mcp-frontend-testing
description: [X] 已废弃 — 禁止 invoke。2026-06-02 起统一使用 playwright-cli-testing Skill 或 PlaywrightCLI。
---

# [!!!] 此 Skill 已永久废弃 [!!!]

> **禁止 invoke 此 Skill。**
>
> **所有 MCP 浏览器工具已全面禁用。**
>
> **正确做法：**

```python
import sys; sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-table')
    # ... 你的测试操作 ...
    cli.screenshot('result.png')
```

**替代 Skill：**
- `playwright-cli-testing` — Playwright CLI 高效测试
- `code-gen-testing` — Skills 代码生成测试（Token 最低 ~7.5K）

**规则来源：** `.trae/rules/SESSION_REMINDER.md` 顶部「浏览器测试铁律」

---

_此 Skill 不再包含任何可执行内容。如果你正在阅读本文，说明你试图通过废弃 Skill 寻找测试方案。请改用 PlaywrightCLI。_
