# 终端工具通道故障 —— RunCommand 已退役，重启 IDE 无效

> **日期**: 2026-10-22
> **现象**: 所有终端命令一律失败，报 `Toolhost terminal commands must be routed through the agent runtime`
> **根因**: `RunCommand` 工具已退役，当前构建不再产生 agent runtime 路由
> **结果**: 改用 `Shell` 工具通道后首条命令即通，全部工作照常完成
> **代价**: 误信"重启 IDE"结论，白费一轮排查

---

## TL;DR

`RunCommand` 是**已退役工具**，其门卫要求命令经 agent runtime 路由，而当前 IDE 构建不再产生该路由
⇒ 所有命令在**执行前**被拒（0–2ms，shell 从未创建，exit -1）。
**这不是沙箱隔离，也不是进程状态问题，重启 IDE 完全无效**（本次已实测）。
当前构建实际挂载的终端工具是 **`Shell`**（走 toolhost 原生通道），换过去即恢复。

---

## 问题时间线

| 时间 | 事件 |
|------|------|
| T0 | 第一条命令 `Write-Output "shell-ok"` 失败，报 `Toolhost terminal commands must be routed through the agent runtime` |
| T0+ | 连续重试 10+ 次，**报错逐字相同**，与命令内容无关 |
| T0+ | 查经验库 `.deprecated/multi-agent-infrastructure-v20260620-v2.md`：沙箱三态（healthy/isolated/deadlock），deadlock ⇒ 重启 IDE |
| T0+ | **基于废弃文档建议用户重启 IDE** ← ⚠️ 误判点 |
| T1 | 用户重启后复测，**故障依旧** |
| T1 | 改走"绕过主通道"路径：经 MCP `integrated_code_mode` 的 `Exec` 调 `RunCommand` → **仍是逐字相同错误** |
| T1 | 关键判据：经 MCP 调**子进程**（`subprocess` 起 powershell）能正常执行 ⇒ 错误不在命令层、不在沙箱层 |
| T1 | 用 `ALL_TOOLS` 列出当前工具集 → 发现有 `Shell`、**无**有效的 `RunCommand` 通道 |
| T1 | 经 `Exec` 调 `tools.Shell` → `shell-ok` / PS 5.1.26100.9711，**首条即通** |
| T1+ | 用 `Shell` 通道完成全部剩余工作：跑测试、提交、push、起 cloudflared 隧道并验证 |

---

## 根因技术细节

```
RunCommand（已退役）──► 门卫检查 agent runtime 路由 ──► 无路由 ──► 100% 拒绝
                                    │                                │
                                    │                    exit -1, 0-2ms, shell 未创建
                                    ▼
Shell（当前挂载）──► toolhost 原生通道 ──► 正常执行 ✅
```

### 判别表

| 维度 | 沙箱 isolated / deadlock（2026-06-20） | **终端通道故障（2026-10-22）** |
|------|---------------------------------------|-------------------------------|
| 失败时机 | 命令**执行中/后** | 命令**执行前** |
| 退出码 | 7（拦截）或 0（假成功） | `-1`（工具层） |
| stdout | 空 / 被吞 | 从未产生（shell 未创建） |
| Write/Read 工具 | 正常 | 正常（**无法区分**） |
| `check_sandbox_status.py` | 可判 | **测不出**（它起子进程，绕开了 agent 通道） |
| 处置 | 切 Read-First / 重启 IDE | **换 `Shell` 工具**，重启无效 |

### 判定顺序（不可跳步）

```
Step 1  跑一条最简命令，记录：报错文本 / 退出码 / 耗时
Step 2  看失败时机
        执行前 + exit -1  ⇒ 走 Step 3（通道故障）
        执行后 + exit 7/0 ⇒ 走 Step 4（沙箱隔离）
Step 3  查当前会话挂载了哪些工具（以运行时 ALL_TOOLS 为准）
        ALL_TOOLS.map(t => t.name)
        有 Shell ⇒ 换用 Shell
        Shell 不在直接工具清单里 ⇒ 经 MCP Exec 调 tools.Shell({command, cwd})
        ALL_TOOLS 里真没有 Shell ⇒ 本轮构建彻底无终端通道，只能用 Read/Write/Edit/MCP，
                          并明确告知用户「本轮无终端通道」
Step 4  沙箱隔离路径：跑 scripts/check_sandbox_status.py → isolated ⇒ 切 Read-First
```

---

## 调试方法论：什么有效，什么无效

| 手段 | 有效性 | 说明 |
|------|--------|------|
| 连续重试同一命令 | ❌ 无效 | 报错逐字相同，100% 确定性失败，重试纯浪费 |
| 查经验库比对历史 | ⚠️ 有用但有陷阱 | 历史档的「deadlock ⇒ 重启 IDE」是**误判**——它描述的是真沙箱死锁 |
| 建议用户重启 IDE | ❌ 无效（本次已实测） | 失效的是工具本身，不是连接/进程状态 |
| **看失败时机（执行前 vs 执行后）** | ✅ **决定性** | 这一条直接分开两类故障 |
| **绕主通道调同名工具** | ✅ **决定性** | 经 MCP `Exec` 调 `RunCommand` 仍同一错误 ⇒ 错误在 toolhost 之下 |
| **起子进程验证** | ✅ **决定性** | `subprocess` 起 powershell 正常 ⇒ 命令层/沙箱层无罪 |
| **`ALL_TOOLS` 列工具集** | ✅ **决定性** | 直接看到当前构建实际挂载了 `Shell` |
| 查 sbox_sdk 日志 | ❌ 无信息 | 本次环境根本没有该日志文件 |

---

## 测试缺口 & 改进

**缺口**：现有 `scripts/check_sandbox_status.py` 只覆盖沙箱三态，**没有第 4 态（工具通道故障）的探测能力**；
且它起子进程，天然测不到 agent 通道层的问题。

**改进**（已落进规范，未改脚本）：

1. 全局规则新增 [terminal-channel-failure.md](file:///d:/filework/.trae/rules/scenarios/8-meta-trae/terminal-channel-failure.md)
   —— 场景 8 的独立经验档，含判别表、诊断步骤、处置铁律、副作用清单。
2. `multi-agent-coordination.md` 沙箱状态机补第 4 态 `blocked`，并标注「仅 deadlock 一态该重启 IDE」。
3. `IRON-RULES-CHEATSHEET.md` 补 **L10「命令全失败先判通道」**（alwaysApply，全会话可见）。
4. `SESSION_REMINDER.md` 踩坑表补一条「命令全失败就重启 IDE」。
5. `START_HERE.md` 决策树补入口行「⛔ 所有终端命令一律失败」。
6. 废弃档 `multi-agent-infrastructure-v20260620-v2.md` 加订正横幅，防止后续再被误用。

---

## 复发记录

### 2026-10-23（复发，原因同根）

现象与 10-22 完全一致（报错逐字相同）。**不是新问题**，是同一根因的重犯：

| 项 | 内容 |
|---|---|
| 触发 | 会话中连续多次调用 **`RunCommand`**（该工具已退役，且不在当前工具集里） |
| 表现 | 每条命令 0–2ms 返回 `Toolhost terminal commands must be routed through the agent runtime`，`exit -1` |
| 误判 | 据此向用户断言「终端坏了、构建和验证都跑不了」，并连续两轮让用户自己手动 `npm run build` |
| 纠正 | 按本文档处置铁律改调 **`Shell`** ⇒ 首条命令即通（`shell-ok` / PS 5.1.26100.9711） |
| 后续 | 一次 `npm run build`（49.7s，93 chunk 无环）、隧道验证 200、411px 浏览器实测全部完成 |

**新增教训**：

7. **报错原文就是线索**。`terminal commands must be routed through the agent runtime` 直指工具通道，不该被读成"终端服务挂了"。本文档第 2 条已写明「报错逐字相同 ⇒ 确定性工具/路由层问题」，复发时仍未据此定位。
8. **不要用"通道坏了"解释不了的现象去阻塞交付**。本次实际耗时全花在反复重试与绕过上，而换 `Shell` 只需一次调用。**先换通道试一条 `echo`，再谈阻塞**。

### 2026-10-23（第二次复发，**差异点在"我看到什么工具"**）

现象仍是逐字相同的报错，但**触发根因与前两次不同**——这次不是"直接调了已退役的 `RunCommand`"，而是：

| 项 | 10-22 / 10-23 第一次复发 | **本次（第二次复发）** |
|---|---|---|
| 我直接调用的工具 | `RunCommand`（已退役，不在工具集里） | `RunCommand`（仍在我的**直接工具清单**里，被我当唯一入口） |
| `Shell` 在我的直接工具清单中 | ✅ 可见，直接调即可 | ❌ **不可见**（上下文压缩后未暴露给我） |
| `Shell` 在运行时 `ALL_TOOLS` 中 | ✅ | ✅ **完好** |
| 正确入口 | 直接调 `Shell` | **必须经 MCP `integrated_code_mode` 的 `Exec` 调 `tools.Shell`** |

**新判据（第 9 条教训）**：

9. **「直接工具清单」≠「运行时 `ALL_TOOLS`」**。上下文被压缩后，我这一轮拿到的直接工具清单可能只剩 `RunCommand`，
   而 `Shell` 仍在运行时 `ALL_TOOLS` 里。此时**不要因为清单里没有 `Shell` 就断定"本轮无终端通道"**——
   先用 MCP `Exec` 查 `ALL_TOOLS`（`ALL_TOOLS.map(t => t.name)`），再经 `Exec` 调 `tools.Shell({command, cwd})` 绕行。
   本次经此路径首条即通（`git status` 正常返回 11 个改动文件），后续全量测试、stash 对照、提交全部完成。
   **推论**：上表 Step 3 里「只有 RunCommand ⇒ 本轮构建彻底无终端通道」这条判据**不成立**——
   必须以运行时 `ALL_TOOLS` 为准，而不是以你眼前看到的工具清单为准。

---

## 经验教训（跨项目适用）

1. **「执行前失败」与「执行后失败」是两类故障的硬边界**。看到命令失败，先问"shell 起来了吗"。
2. **报错逐字相同 ⇒ 是确定性的工具/路由层问题**，不是命令问题，重试无意义。
3. **历史经验档会过期，也会误判**。引用前先确认它描述的现象与当前现象**是否同构**；
   现象不同构时，不能照搬处置手段（本次照搬"重启 IDE"就白费一轮）。
4. **"重启 IDE"是强手段，应留到排除其它可能后**。它掩盖症状、消耗用户耐心，且对工具层故障无效。
5. **换工具通道后先跑一条最简命令验证**，不要凭"应该能通"就继续。
6. **通道切换不影响已产生的副作用**，但换通道后要重新确认：commit 是否真成功、长跑进程是否重复起。

---

## 行动项

| # | 项 | 状态 |
|---|---|------|
| 1 | 新增终端通道故障经验档（场景 8） | ✅ 完成 |
| 2 | 沙箱状态机补第 4 态 + 订正废弃档 | ✅ 完成 |
| 3 | alwaysApply 铁律卡补 L10 + 踩坑表补 1 条 | ✅ 完成 |
| 4 | 决策树补入口 | ✅ 完成 |
| 5 | `check_sandbox_status.py` 补第 4 态探测 | ⏳ 未做（脚本层面，可后续） |
| 6 | 清理 user_group 迁移遗留测试（另一主题） | ✅ 见 [metadata-migration-test-cleanup.md](file:///d:/filework/excel-to-diagram/docs/lessons-learned/testing/metadata-migration-test-cleanup.md) |

---

## 相关文件清单

- 新增经验档：[terminal-channel-failure.md](file:///d:/filework/.trae/rules/scenarios/8-meta-trae/terminal-channel-failure.md)
- 沙箱状态机：[multi-agent-coordination.md](file:///d:/filework/.trae/rules/scenarios/7-ai-collaboration/multi-agent-coordination.md)
- 铁律卡：[IRON-RULES-CHEATSHEET.md](file:///d:/filework/.trae/rules/IRON-RULES-CHEATSHEET.md)
- 会话提醒：[SESSION_REMINDER.md](file:///d:/filework/.trae/rules/SESSION_REMINDER.md)
- 入口决策树：[START_HERE.md](file:///d:/filework/.trae/rules/START_HERE.md)
- 废弃档订正：[multi-agent-infrastructure-v20260620-v2.md](file:///d:/filework/.trae/rules/.deprecated/multi-agent-infrastructure-v20260620-v2.md)
- 沙箱探测脚本（未改）：[check_sandbox_status.py](file:///d:/filework/excel-to-diagram/scripts/check_sandbox_status.py)
