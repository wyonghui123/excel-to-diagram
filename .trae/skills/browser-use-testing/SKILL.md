---
name: "browser-use-testing"
description: [X] 已废弃 — 禁止 invoke。2026-06-03 起统一使用 PlaywrightCLI（test_helpers/browser_auth_cli.py）。
---

# [!!!] 此 Skill 已永久废弃 [!!!]

> **禁止 invoke 此 Skill。**
>
> **browser-use 框架已全面禁用用于本项目浏览器测试。**
>
> **原因：**
> 1. 需要外部 LLM API Key（OpenAI/Anthropic），增加依赖
> 2. Token 消耗 ~40-60K/任务，比 PlaywrightCLI (~27K) 高
> 3. 执行时间较长，AI 决策不确定
> 4. 与项目 PlaywrightCLI 统一方案冲突
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
- `e2e-testing` — Playwright E2E 测试

**规则来源：** `.trae/rules/SESSION_REMINDER.md` 顶部「浏览器测试铁律」

---

_此 Skill 不再包含任何可执行内容。如果你正在阅读本文，说明你试图通过废弃 Skill 寻找测试方案。请改用 PlaywrightCLI。_
