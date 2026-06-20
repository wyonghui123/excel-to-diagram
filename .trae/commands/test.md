---
name: test
description: 运行测试（使用合规入口 python test.py）
---

运行测试，遵循项目铁律：禁止直接 pytest，必须用 python d:\filework\test.py。

步骤：
1. 先检查是否有失败需要重跑：`python d:\filework\test.py --status`
2. 如果有失败：`python d:\filework\test.py --failed`
3. 如果要跑全量：`python d:\filework\test.py --all --force`（注意：--all 并行可能有假失败，必须再跑 --failed 确认）
4. 单文件测试：`python d:\filework\test.py --file <path>`
5. 快速单测：`python d:\filework\test.py --single <test_id>`

重要规则：
- 绝对禁止 `pytest` 或 `python -m pytest`
- 修复后跑 `--failed`，不要跑 `--all`
- 多 Agent 环境用 `--port <3010-3019>` 隔离
