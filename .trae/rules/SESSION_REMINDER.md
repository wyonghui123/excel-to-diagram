# 会话开始提醒

> [!!!] 本文件是 Agent 每次会话的必读入口，包含核心铁律和速查表
> [!!!] 详细规则已拆分到单独文件，按需读取

---

## 项目概述 (WHAT)

**项目类型**：企业级元数据驱动的权限管理系统（BIP 架构）

**技术栈**：
- **后端**：Python + Flask + SQLite（meta/architecture.db）
- **前端**：Vue 3 + Element Plus + Vite
- **测试**：PlaywrightCLI（Python 封装）+ pytest
- **服务管理**：PowerShell service_manager.ps1

**关键目录**：
- `meta/` - 后端 Python 代码、API、schemas、tests
- `src/` - 前端 Vue 代码、组件、路由
- `e2e/` - 浏览器测试（Playwright .spec.js）
- `tests/` - Python 测试（pytest）
- `.trae/rules/` - AI Agent 规则（本文件所在）

**为什么这样组织**：让智能体快速定位代码位置，避免在错误目录中搜索。

---

## 核心铁律（最高优先级）

| # | 铁律 | 违规后果 |
|---|------|---------|
| 1 | **禁止直接运行 pytest** | pytest 测试（.py）必须用 `python d:\filework\test.py`；E2E 测试（.spec.js）用 `npm run test:e2e` 或 `npx playwright test` |
| 2 | **测试场景禁止 MCP 浏览器工具** | 必须用 PlaywrightCLI |
| 3 | **服务启停必须用 service_manager.ps1** | 禁止 `npm run dev` / `taskkill` |
| 4 | **PowerShell 禁止用 curl** | 用 `curl.exe` 或 Python |
| 5 | **UI 修改必须验证** | 禁止改完代码直接提交 |
| 6 | **测试数据禁止硬编码** | 用 `test_data_inventory.json` |
| 7 | **认证必须用 authenticated_navigate()** | 禁止自己拼 dev-login |
| 7a | **禁止使用 Bearer token 认证** | 应该用 cookie（dev-login 设置 httpOnly cookie） |
| 8 | **测试失败后禁止反复修改脚本** | 应先诊断根因，再修复 |
| 9 | **必须检查页面健康状态** | 关键操作前调用 `check_health()`，测试结束调用 `assert_healthy()` |
| 10 | **测试脚本内禁止 wait_for_timeout / sleep** | 用 `wait_for_selector` 或 `wait_for_stable()`；测试外部等待测试完成可用 `Start-Sleep` |
| 11 | **禁止直接运行测试脚本** | 必须用 `python d:\filework\test.py --file <path>` |
| 12 | **禁止直接运行 Python 脚本** | 应该用 pytest fixture 或 API 封装 |
| 13 | **长测试必须分批运行** | 每批 < 5 分钟，启用 `--batch-size --fail-fast` |
| 14 | **运行测试必须实时输出** | 用 `Tee-Object` 输出到终端和文件 |
| 14a | **测试跑完必须检查结果（pass/fail）** | 用 `Select-String -Pattern "passed\|failed"` 验证，不能只看退出码 |
| 15 | **每批后必须检查进度** | 查看 `test_progress.json` 或 `test_live.md` |
| 16 | **前端测试必须开启 Source Map** | `build.sourcemap: 'hidden'` + `test.sourcemap: true` |
| 17 | **前端测试用 happy-dom** | 不用 jsdom（性能差 2-3 倍） |
| 18 | **前端 API mock 用 MSW** | 不用模块 mock（脆弱） |
| 19 | **多 Agent 必须分配独立端口** | 用 `python scripts/allocate_ports.py allocate --agent X` |
| 20 | **多 Agent 必须创建 worktree** | 防止文件相互覆盖 |
| 21 | **启动前必须检查资源** | 用 `python scripts/resource_monitor.py check` |
| 22 | **运行命令前必须设置 UTF-8** | `chcp 65001` + `$env:PYTHONIOENCODING="utf-8"` + `$env:PYTHONUTF8=1` |
| 23 | **新写 E2E 测试必须用 v2 简化方案** | 重复登录 + Date.now 命名 + 不清理 = DB 垃圾 | 见 [e2e-simplification.md](./e2e-simplification.md) |
| 24 | **读写文件必须 UTF-8 + ast.parse 验证** | docstring 损坏 + IndentationError 调试 30+ 分钟 | 见 [file-encoding-rules.md](./file-encoding-rules.md) |
> **为什么要遵守这些规则**：
> - **铁律 1-3**：保护数据库、避免服务冲突、提高多 Agent 协作效率
> - **铁律 4-7**：避免常见错误（卡死终端、覆盖文件、认证失败）
> - **铁律 8-10**：避免测试循环、提高测试效率
> - **铁律 11-12**：强制使用标准测试入口
> - **铁律 13-15**：保证长测试的可观测性（分批、实时输出、过程检查）
> - **铁律 16-18**：前端测试质量（Source Map、happy-dom、MSW）
> - **铁律 19-21**：多 Agent 协作安全（端口隔离、worktree、资源检查）
> - **铁律 22**：UTF-8 编码（中文不乱码）

---

## 测试类型区分（重要！）

| 测试类型 | 文件位置 | 运行入口 | 示例 |
|---------|---------|---------|------|
| **pytest 测试** | `meta/tests/*.py` | `python d:\filework\test.py --file <path>` | `python d:\filework\test.py --file meta/tests/test_api.py` |
| **E2E 测试** | `e2e/**/*.spec.js` | `npm run test:e2e` 或 `npx playwright test <path>` | `npx playwright test e2e/features/login.spec.js` |

**常见错误**：
- [X] `python d:\filework\test.py --file e2e/features/xxx.spec.js` — test.py 不识别 .spec.js
- [X] `pytest meta/tests/test_api.py` — 必须用 test.py 入口
- [OK] `python d:\filework\test.py --file meta/tests/test_api.py` — pytest 测试正确入口
- [OK] `npx playwright test e2e/features/xxx.spec.js` — E2E 测试正确入口

**为什么区分**：
- pytest 测试需要 DB 快照、锁机制、并发控制（test.py 提供）
- E2E 测试需要浏览器环境、认证状态共享（Playwright 提供）

---

## 关键架构决策 (WHY)

| 决策 | 原因 |
|------|------|
| **唯一测试入口 `test.py`** | 强制 DB 快照、锁机制、并发控制 |
| **PlaywrightCLI 替代 MCP** | Python 子进程天然隔离，多 Agent 协作无需复杂方案 |
| **Cookie 认证（非 Bearer）** | httpOnly cookie 更安全，前端代码自动处理 |
| **service_manager.ps1 统一管理** | 跨 Agent 状态可见，端口冲突自动避免 |
| **测试数据清单文件** | 避免硬编码，测试数据变化时自动适配 |

---

## 开发工作流 (HOW)

### 修改代码的标准流程

1. **修改前**：
   - 阅读相关规则文件（按需）
   - 用 `git status` 确认当前状态

2. **修改中**：
   - 遵循现有代码风格
   - 添加必要的注释和文档

3. **修改后**：
   - **UI 修改**：用 PlaywrightCLI 截图验证
   - **后端修改**：用 `python test.py --file <test_path>` 验证
   - **测试失败**：用 `--failed` 重新运行，不要 `--all`

### 写新测试的标准流程

1. 继承现有测试结构（看 `tests/e2e/test_*.py`）
2. 使用 PlaywrightCLI 或 pytest fixture
3. 添加健康检测（`check_health()` + `assert_healthy()`）
4. 用 `valid_*` fixture 获取有效测试数据
5. 提交前用 `python test.py --file <your_test.py>` 验证

### 调试标准流程

1. 收集症状（错误信息、stack trace、复现步骤）
2. 检查规则文件（是否有相关禁止）
3. 用最小化复现验证假设
4. 修复后用 `--failed` 验证
5. 添加回归测试

---

## 快速路由表

| 任务场景 | 行动 |
|---------|------|
| **pytest 测试** | `python d:\filework\test.py --failed` |
| **浏览器测试** | PlaywrightCLI 写 Python 脚本 |
| **UI 修改验证** | PlaywrightCLI 截图，禁止不验证直接提交 |
| **E2E 测试** | invoke `e2e-testing` Skill |
| **问题修复** | invoke `problem-fixing` Skill |
| **服务启停** | `powershell -File scripts/service_manager.ps1 status\|start\|stop\|restart` |
| **后端 API 调试** | `requests.Session()` 携带 cookie（不要拼 Bearer token） |

---

## 常见踩坑速查（精简版）

| # | 场景 | 错误 | 正确 |
|---|------|------|------|
| 1 | pytest | 直接运行 pytest | `python test.py` |
| 2 | pytest | `--all` 后不跑 `--failed` | 并发假失败需确认 |
| 3 | 浏览器测试 | 用 MCP 工具做测试 | PlaywrightCLI |
| 4 | 服务管理 | 直接 `npm run dev` | `service_manager.ps1` |
| 5 | 服务管理 | 用 `Get-Process` 判断状态 | `service_manager.ps1 status` |
| 6 | PowerShell | 用 `curl` | `curl.exe` 或 Python |
| 7 | PowerShell | 用 `&&` / `||` 串联命令 | `;` 或 `if ($LASTEXITCODE)` |
| 8 | UI 修改 | 改完 Vue/CSS 不验证 | PlaywrightCLI 截图 |
| 9 | 测试结果 | hasTable=False 但标记 PASS | 误报！必须诊断 |
| 10 | 测试流程 | 连续 2 次超时后继续重跑 | 停止，诊断超时根因 |
| 11 | 认证 | 自己拼 dev-login + 手动处理 cookie | `authenticated_navigate()` |
| 12 | 测试数据 | 硬编码产品名称 | `test_data_inventory.json` |
| 13 | API 测试 | 用 curl.exe 测试 API | PlaywrightCLI.request() |
| 14 | 诊断 | 发现问题后继续修改脚本 | 停下来分析根因 |
| 15 | 文件操作 | Write 覆盖用户恢复的文件 | 先检查 git status |
| 16 | 页面健康 | 不检查页面错误就操作 | 关键操作前 `check_health()` |
| 17 | 页面健康 | 测试结束不检查健康状态 | 调用 `assert_healthy()` |
| 18 | 测试脚本 | 使用 `wait_for_timeout` 或 `sleep` | 用 `wait_for_selector` 或 `wait_for_stable()` |
| 19 | 测试脚本 | 没有 pytest 结构 | 无法并行、无法重试 |
| 20 | 测试脚本 | 直接操作数据库 | 用 fixture 或 API |
| 21 | 运行测试 | 直接 `python tests/xxx.py` | `python test.py --file tests/xxx.py` |
| 22 | PowerShell | 路径分隔符混用 | 统一用正斜杠 `tests/e2e/` |
| 23 | PowerShell | 重定向 `2>&1 1>file` | 用 `*> file` 或 `2>&1 | Out-File` |
| 24 | 输出捕获 | 用 `Out-File` 但输出被截断 | 用 `Tee-Object` 或 `*> file` |
| 25 | 直接读 DB | `sqlite3.connect('meta/architecture.db')` | 用 API `cli.request('/api/v2/...')` |
| 26 | 诊断脚本 | 反复创建 diag_v1/v2/v3 | 一次写好，用 fixture 或参数化 |
| 27 | 运行 E2E | 直接 `npx playwright test` | 用 `python test.py --file e2e/...` |
| 28 | 跑测试 | 一次性跑全套（5-10 分钟） | 先 `--failed` 找到失败再修 |
| 29 | 输出过滤 | `Out-String \| Select-String` 丢失日志 | 用 `Tee-Object` 保留完整输出 |
| 30 | 后台运行 | 在沙箱中跑长时间任务 | 用"在沙箱外"异步运行 |
| 31 | 长测试 | 一次性跑完全部（5-10 分钟） | 分批运行 + Fail-Fast |
| 32 | 长测试 | 输出被截断或过滤 | 用 `Tee-Object` 实时输出 |
| 33 | 长测试 | 跑完才知道结果 | 实时查看 `test_progress.json` |
| 34 | 前端测试 | 错误信息指向压缩代码 | 开启 `build.sourcemap: 'hidden'` |
| 35 | 前端测试 | 用 jsdom（慢 2-3 倍） | 改用 `environment: 'happy-dom'` |
| 36 | 前端测试 | 模块 mock（脆弱） | 用 MSW 拦截网络层 |
| 37 | 前端测试 | 测试失败无法调试 | 启用 `@vitest/ui` 可视化调试 |
| 38 | 多 Agent | 端口冲突（3004 被占用） | 先 `allocate_ports` 再启动 |
| 39 | 多 Agent | 共享目录导致文件覆盖 | 用 `git worktree` 隔离 |
| 40 | 多 Agent | 资源耗尽（CPU/内存 100%） | 启动前 `resource_monitor check` |
| 41 | 中文乱码 | PowerShell 输出 `涓..` 等乱码 | `chcp 65001` + 设置 `PYTHONIOENCODING=utf-8` |
| 42 | Tee-Object 编码 | 中文日志乱码 | 用 `Out-File -Encoding utf8` |
| 43 | PS5 解析错误 | `"[OK] 中文"` 报语法错误 | 用中文【】或纯英文 |
| 44 | 缺依赖 | `ModuleNotFoundError: No module named 'psutil'` | 先 `pip install psutil` |
| 45 | 中文乱码终极 | 用 `\| Out-String` 或 `*>` 都乱码 | **必须** 5 行配置：`[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` |
| 46 | 重复登录 | 每个测试都调 `login(page)` 浪费 5-15s | 用 `global-setup.js` + `storageState` 一次登录 |
| 47 | 硬编码 ID | 测试中硬编码产品/版本 ID | 用 `dataFinder.productWithVersion()` 智能查找 |
| 48 | 硬编码等待 | `page.waitForTimeout(1500)` | 用 `navigateTo()` 智能稳定等待 |
| 49 | 测试样板多 | 5-6 行 login + nav + stable 重复 | 用 `auto-fixtures.js` 一行 `navigateTo(page, path)` |

---

## 详细规则文件索引

| 文件 | 内容 | 何时读取 |
|------|------|---------|
| `test-script-quality-analysis.md` | 测试脚本质量分析、效率优化建议 | 写测试脚本时 |
| `page-health-rules.md` | 页面健康检测规范、四层错误检测机制 | 写浏览器测试时 |
| `powershell-rules.md` | PowerShell 语法规范、Bash→PowerShell 速查表 | 遇到 PowerShell 语法问题时 |
| `test-data-rules.md` | 测试数据管理规范、fixture 使用方法 | 需要选择测试数据时 |
| `service-management-rules.md` | 服务管理规范、重启安全规则 | 需要启停服务时 |
| `browser-test-verification.md` | 浏览器测试验证方法、认证规范 | 写浏览器测试时 |
| `frontend-test-auth.md` | 前端测试认证规范 | 需要认证时 |
| `e2e-testing.md` | E2E 测试专用规则（v1） | 维护旧测试时 |
| `e2e-simplification.md` | **[NEW] E2E v2 简化方案强制规范（POM/fixtures/isolation/auto-trace）** | **写新 E2E 测试时** |
| `file-encoding-rules.md` | **[NEW] 文件编码与字符串语法规范（UTF-8 + ast.parse 验证）** | **写任何 .py 文件时** |
| `test-runner-template.md` | **[NEW] 测试运行标准模板（Tee-Object + Select-String 验证）** | **跑任何测试后** |
| `test-case-standards.md` | 测试用例编写规范 | 写测试用例时 |
| `test-observability-rules.md` | **测试可观测性规范（分批、实时输出、过程检查）** | **运行长测试时** |
| `frontend-testing-standards.md` | **前端测试标准（Vitest + happy-dom + MSW + Source Map）** | **写前端测试时** |
| `multi-agent-coordination.md` | **多 Agent 协作规范（端口隔离 + worktree + 资源监控）** | **多 Agent 并行时** |
| `project_rules.md` | 项目核心规则 | 了解项目规范时 |

---

## 附录：废弃文件/Skill（禁止读取/invoke）

| 文件/Skill | 状态 |
|------|------|
| `.trae/rules/mcp-testing.md` | 内容已清空 |
| `.trae/rules/mcp-parallel-integration.md` | 方案已废弃 |
| `.trae/rules/multi-agent-browser-isolation.md` | 方案已废弃 |
| `.trae/rules/multi-agent-quickstart.md` | 方案已废弃 |
| `.trae/skills/mcp-frontend-testing/` | Skill 已清空，禁止 invoke |
| `.trae/skills/browser-use-testing/` | Skill 已清空，禁止 invoke |
| `webapp-testing`（系统级 Skill） | 使用 MCP 浏览器工具，禁止 invoke |
