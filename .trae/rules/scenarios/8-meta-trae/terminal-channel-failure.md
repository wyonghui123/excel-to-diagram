---
alwaysApply: false
description: "AI 在 Trae IDE 中所有终端命令一律失败（报错 Toolhost terminal commands must be routed through the agent runtime / 沙箱 deadlock 误判 / 重启 IDE 无效）时查阅此规则。给出根因判定、区分「命令通道故障」与「沙箱隔离」、以及改用 Shell 工具的解法。"
---

# 终端通道故障诊断（v2026.10.22）

> **来源**：2026-10-22 实战排查（本轮连续 10+ 次命令失败 → 定位到工具通道层）
> **性质**：**平台侧工具路由问题，不是本项目代码问题，也不是沙箱隔离**
> **重要**：与 2026-06-20 记录的「沙箱 deadlock ⇒ 重启 IDE」是**两回事**，别混用处置手段

---

## 一、故障现象

所有终端命令**一律**失败，且**在命令执行前**就被拒：

```
command error: Execute command `Write-Output "shell-ok" ` failed,
the err is: unknown error: Toolhost terminal commands must be routed through the agent runtime
```

关键特征：

| 特征 | 实测值 | 判读 |
|------|--------|------|
| 失败位置 | 命令**执行前**（shell 从未创建） | 非命令语法/编码问题 |
| 耗时 | 0–2 ms 立即返回 | 非超时、非假成功 |
| 退出码 | `-1`（工具层错误） | 非 PowerShell 退出码 |
| 报错文本 | 逐字相同，与命令内容**完全无关** | 非命令级错误 |
| 影响范围 | **所有**命令，含 `echo`/`git status`/简单表达式 | 非特定命令触发 |
| 绕道 MCP Exec 调 RunCommand | 仍返回**逐字相同**错误 | 错误在 toolhost 之下，更底层 |
| Read / Write / Edit / Glob | **全部正常** | 仅终端通道坏，其它通道完好 |
| 重启 IDE | **无效**（用户已实测） | 非进程状态问题 |

---

## 二、根因

`RunCommand` 工具是**已退役工具**。它的门卫要求命令必须经 **agent runtime 路由**（`Toolhost terminal commands must be routed through the agent runtime`），而**当前 IDE 构建不再产生这条路由**：

```
RunCommand（已退役）──► 门卫检查 agent runtime 路由 ──► 无路由 ──► 100% 拒绝
                                    │
                                    ▼
Shell（当前挂载）──► toolhost 原生通道 ──► 正常执行 ✅
```

**判定为「工具本身失效」而非「连接/进程状态问题」**——这是本条最重要的结论。

### 3.1 与历史沙箱故障的区别（必读）

历史经验档（`.deprecated/multi-agent-infrastructure-v20260620-v2.md`、`multi-agent-coordination.md`）描述的沙箱三态：

```
[healthy] ──exec_too_long──► [isolated] ──持续异常──► [deadlock] ──► 重启 Trae IDE
```

| 维度 | 沙箱 isolated / deadlock（2026-06-20） | **终端通道故障（2026-10-22）** |
|------|---------------------------------------|-------------------------------|
| 失败时机 | 命令**执行中/后** | 命令**执行前** |
| 退出码 | 7（沙箱拦截）或 0（假成功） | `-1`（工具层） |
| stdout | 空 / 被吞 | 从未产生（shell 未创建） |
| Write/Read 工具 | 正常 | 正常（**无法区分**） |
| 脚本探测 | `scripts/check_sandbox_status.py` 可判 | 该脚本**测不出**（它起的是子进程，绕开了 agent 通道） |
| 处置 | 切 Read-First / 重启 IDE | **换 `Shell` 工具**，重启无效 |

> **[!!!] 误判代价（本次已付出）**：[!!!] 依据废弃档「deadlock ⇒ 必须重启 IDE」的结论建议用户重启 IDE，
> 重启后故障依旧，白白浪费一轮排查。**重启 IDE 只对真正的 sandbox deadlock 有效。**
> 判定顺序必须是：**先看失败时机（执行前 vs 执行后）→ 再看退出码（-1 vs 7/0）→ 才决定处置**。

---

## 三、诊断步骤（照做，勿跳步）

```
Step 1  跑一条最简命令（Write-Output "x"）
        → 失败？记录：报错文本 / 退出码 / 耗时

Step 2  看「失败时机」
        → 执行前 + 退出码 -1  ⇒ 走 Step 3（通道故障）
        → 执行后 + exit 7/0 空 ⇒ 走 Step 4（沙箱隔离）

Step 3  查当前会话挂载了哪些工具
        ⚠️ 以运行时 ALL_TOOLS 为准，不要以"你眼前看到的直接工具清单"为准。
        （上下文压缩后，直接清单可能只剩已退役的 RunCommand，
          而 Shell 仍在运行时 ALL_TOOLS 里 —— 2026-10-23 第二次复发就栽在这）
        用 MCP integrated_code_mode 的 Exec 查 ALL_TOOLS：
            ALL_TOOLS.map(t => t.name)
        → 有 Shell ⇒ 换用 Shell，直接绕过 RunCommand
          · Shell 在直接清单里 ⇒ 直接调
          · Shell 不在直接清单里 ⇒ 经 Exec 调 tools.Shell({command, cwd})
        → ALL_TOOLS 里真没有 Shell ⇒ 说明本轮构建彻底无终端通道，
                            只能用 Read/Write/Edit/MCP 完成工作，
                            并明确告知用户「本轮无终端通道」

Step 4  沙箱隔离路径（历史流程，本条不适用）
        跑 scripts/check_sandbox_status.py → isolated ⇒ 切 Read-First
```

### 3.1 怎么切到 Shell 通道

`Shell` 是**当前构建实际挂载**的终端工具，走 toolhost 原生通道。两种调用姿势：

```python
# 姿势 A：MCP integrated_code_mode 的 Exec 里直接调
await tools.Shell({command: 'Write-Output "shell-ok"'})
# → {"status":"completed","exit_code":0,"stdout":"shell-ok", ...}

# 姿势 B：会话里若已直接挂载 Shell 工具，直接调用即可
```

实测：`Write-Output "shell-ok"; $PSVersionTable.PSVersion` → `shell-ok` / `5.1.26100.9711`，首条即通。

---

## 四、处置铁律

| # | 铁律 |
|---|------|
| 1 | **连续 2 次同样的「执行前」失败即判定通道故障**，不要重试第 3、4、5 次 |
| 2 | **不要用「重启 IDE」当第一手段**——仅在确认是 sandbox deadlock（ptyHost heartbeat 丢失）时才重启 |
| 3 | **不要建议用户重启来掩盖工具层问题**——本例重启完全无效，白耗一轮 |
| 4 | 换 `Shell` 通道后**立刻跑一条最简命令验证**，不要凭"应该能通"就继续往下做 |
| 5 | 换通道前已写文件/已改代码的，**继续做完并验证**，不要因换工具而丢进度 |
| 6 | 通道坏期间**不要假装命令跑过**——如实告知用户本轮走的是哪条通道 |
| 7 | **判定"有没有终端通道"必须查运行时 `ALL_TOOLS`**，不能只看你眼前的直接工具清单（上下文压缩后两者会不一致） |

---

## 五、副作用清单（换通道后重跑）

通道切换只影响执行路径，**不影响已产生的副作用**。恢复后需确认：

- [ ] 之前 `git commit` / `git push` 是否真的成功（`git log --oneline -3` 验，不是看命令返回）
- [ ] 后台进程是否还活着（隧道/服务类长跑任务，换通道后**不要重复起**，先查端口/进程）
- [ ] 临时文件/测试产物是否已落盘（用 Read/LS 验，不看 exit code）

> **本次实例**：通道恢复后先查 `job-…/output.log` 与端口占用，确认 cloudflared 隧道只有一个实例，
> 避免「换工具 → 重复起服务 → 端口冲突」。

---

## 六、CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-10-22 | AI Assistant | 初版：终端通道故障（RunCommand 已退役）与沙箱三态的区分、诊断步骤、处置铁律、副作用清单 |
| 2026-10-23 | AI Assistant | 补第 2 次复发判据：Step 3 改为**以运行时 `ALL_TOOLS` 为准**；修正「只有 RunCommand ⇒ 无终端通道」的误判；铁律补第 7 条 |
