# [!!!] 已永久废弃 — 禁止读取 [!!!]

> **此文件已被完全清空。原 MCP 浏览器测试内容已全部删除。**

---

## 唯一规则：浏览器测试只允许 PlaywrightCLI

```
[X] 绝对禁止: mcp_Chrome_DevTools_MCP_*、mcp_Concurrent-Browser_*、mcp_Playwright_*、任何 MCP 浏览器工具

[OK] 唯一合法入口: test_helpers/browser_auth_cli.py (PlaywrightCLI)
```

```python
import sys; sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-table')
```

---

**规则来源：** `.trae/rules/SESSION_REMINDER.md` 顶部「浏览器测试铁律」
**完整验证方法：** `.trae/rules/browser-test-verification.md`
**认证规范：** `.trae/rules/frontend-test-auth.md`

---

_此文件不再包含任何 MCP 内容。如果你正在阅读本文，说明你试图通过废弃文件寻找测试方案。请改用 PlaywrightCLI。_