---
alwaysApply: false
description: "AI 在 Trae IDE 中启动长驻服务（vite / cloudflared 隧道 / waitress / watchdog 等）导致终端调用挂住数十分钟到数十小时、或会话出现长时间空转时查阅此规则。给出根因（终端等待整棵后代进程树退出）、诊断取证方法、以及用 launch_detached.ps1 脱离 job object 启动的解法。"
---

# 终端调用被长驻服务拖死（v2026.10.24）

> **来源**：2026-10-24 实战排查（用户报「老是跑很久 430 分钟」→ 定位到工具层等待机制 + 内存耗尽）
> **性质**：**平台侧终端行为 + 本地资源问题**，不是业务代码问题
> **影响面**：所有需要起长驻服务（前端 dev/preview、隧道、后端、watchdog）的任务

---

## 一、现象

| 现象 | 实测值 |
|------|--------|
| 单次终端调用挂住时长 | 最长 **1353.8 分钟**（22.6 小时），另有 1209 / 1026 / 983 / 959 / 898 分钟多例 |
| 累计滞留时长 | **9146 分钟**（约 152 小时） |
| 会话空转 | 单次连续 **439 分钟**零命令（用户看到的「430 分钟」） |
| 表面症状 | 脚本早就跑完了、输出也早就落盘了，但终端调用不返回 |

---

## 二、根因

Trae 终端工具在 `agent-tool-host.exe` 下以 **job object** 方式派生进程，并等待 **整棵后代进程树** 退出，才把该次调用标记为完成。

```
agent-tool-host.exe
  └─ powershell.exe          ← 本次终端调用的 shell
       └─ Start-Process 起的子进程   ← 父级仍是本 powershell.exe ⇒ 仍在同一个 job 内
            └─ vite / cloudflared / waitress ...
```

关键点：**`Start-Process` 不会脱离 job**。子进程的父级仍是当前 `powershell.exe`，因此长驻服务只要还活着，这次终端调用就永远不会结束。

### 附带根因：内存耗尽会把挂死放大成数小时

10-22 22:29–22:43 连续 7 次 Windows Event 2004（低虚拟内存），`chrome.exe` 占 2.39 GB、`node.exe` 占 2.15 GB。此时 toolhost 派生进程直接失败：

```
toolhost-host-direct_spawn-*.log: [stderr] memory allocation of 18000 bytes failed
```

包装器进入半死状态（`output.log` 满是 `System.OutOfMemoryException`），进程既不退出也不报错——**一直挂到机器重启**。

该机器 `AutomaticManagedPagefile = False` 且注册表 `PagingFiles` 为空 ⇒ **根本没有页面文件**，提交上限 31.69 GB ≈ 纯物理内存。

---

## 三、诊断取证方法

> 全部可在只读前提下完成，**不要**先重启 IDE（重启会清掉现场）。

### 3.1 看终端 job 的历史耗时

toolhost 的每个命令都在磁盘留了 job 目录，含权威时间戳：

```
C:\Users\Administrator\AppData\Local\Temp\trae-agent-toolhost\jobs\<job-id>\state.json
```

```powershell
Get-ChildItem "$env:LOCALAPPDATA\Temp\trae-agent-toolhost\jobs" -Directory |
  Where-Object { $_.Name -ne '.pool' } | ForEach-Object {
    $s = Get-Content (Join-Path $_.FullName 'state.json') -Raw | ConvertFrom-Json
    [pscustomobject]@{
      Minutes = [math]::Round(([int64]$s.finished_at - [int64]$s.created_at) / 60, 1)
      Created = [DateTimeOffset]::FromUnixTimeSeconds([int64]$s.created_at).ToLocalTime()
      Cmd     = "$($s.command)".Substring(0, 90)
    }
  } | Sort-Object Minutes -Descending | Select-Object -First 20
```

### 3.2 区分「排队拥塞」与「进程不退出」

- `started_at - created_at` ≈ 0 ⇒ **不是排队问题**（实测最大仅 1 秒，`.pool` 有 32 槽位）
- `finished_at - output.log 的最后写入时间` 很大 ⇒ **进程赖着不退出**（本例 24 例，累计 9146 分钟）

### 3.3 看内存与页面文件

```powershell
Get-CimInstance Win32_ComputerSystem | Select-Object AutomaticManagedPagefile, TotalPhysicalMemory
Get-CimInstance Win32_PageFileUsage | Select-Object Name, AllocatedBaseSize, CurrentUsage
Get-WinEvent -FilterHashtable @{LogName='System'; Id=2004; StartTime=(Get-Date).AddDays(-6)}
```

Event 2004 = 低虚拟内存；Event 26 = 「虚拟内存不足」弹窗。

---

## 四、解法：脱离 job 启动长驻服务

已落地：**`d:\filework\excel-to-diagram\scripts\launch_detached.ps1`**

原理：用 WMI `Win32_Process.Create` 创建进程，父进程是 **`WmiPrvSE.exe`（系统服务）**，因此**不在调用方的 job object 内**。终端调用立即返回，长驻服务独立存活。

```powershell
# 启动长驻服务（立即返回）
pwsh -File d:\filework\excel-to-diagram\scripts\launch_detached.ps1 `
    -CommandLine 'npx vite preview --port 4173' `
    -WorkingDirectory 'd:\filework\excel-to-diagram' `
    -StdOut '.runtime\pv.out.log' -StdErr '.runtime\pv.err.log' `
    -WaitPort 4173
```

### 已在仓库中改造的调用点

| 文件 | 改造内容 |
|------|---------|
| `scripts/start-mobile.ps1` | preview / cloudflared 隧道改用 `launch_detached.ps1`；**删掉末尾 `while (-not $tunnelProc.HasExited)` 常驻等待**，脚本输出 PID 后直接返回 |
| `scripts/service_manager.ps1` | frontend / backend / watchdog 的启动改用 `launch_detached.ps1` |

### 实现要点（均为实测踩坑后固化）

| 要点 | 说明 |
|------|------|
| **单层 `powershell.exe`** | 不要在 WMI 进程内再套 `Start-Process`：嵌套会打断转义链，子进程拿不到参数、秒退且不写日志 |
| **命令体走 `-EncodedCommand`** | Base64 / UTF-16LE，避免引号与特殊字符转义问题 |
| **禁止 `cmd /c`** | toolhost 安全策略明确拦截 `cmd /c`；重定向用 PowerShell 的 `1>` / `2>` |
| **stdout / stderr 分开落盘** | 不要用 `*>`（合并流）。cloudflared 的公网地址打在 **stderr**，合并后调用方读不到 |
| **日志文件被占用要 fallback，不能硬写** | PowerShell 的 `1>` 以 `FileShare.Read` 打开目标文件。若日志仍被上一轮遗留进程持有（实测：10-23 的旧 `npm run dev` 一直握着 `frontend.out`），重定向直接失败 ⇒ 脱离启动的子进程**秒退且不写任何日志**，唯一症状只是「spawned but port not responding」。`launch_detached.ps1` 现在先探测可写，被占则自动改写到 `name.yyyyMMdd-HHmmss.out`，**不要**为此去杀持锁进程 |
| **脚本内只用 ASCII 字面量** | Windows PowerShell 5.1 把无 BOM 的 `.ps1` 按 GBK 读，中文字面量会变成乱码、破坏引号导致解析失败。带中文的 `.ps1` 必须存为 **UTF-8 with BOM**（仓库现有约定） |
| **无 BOM + 行尾全角标点会吃掉换行** | 更隐蔽的一种：GBK 误解码时行尾「。」的尾字节会吞掉后面的 CRLF，**把下一行并进注释**。实测后果是 `service_manager.ps1` 的 `$services` 里 `frontend` 键凭空消失（解析 0 错误，但 `start-fe` 报 `$cfg` 为 null / `You cannot call a method on a null-valued expression`）。判定方法：用 `[System.Management.Automation.Language.Parser]::ParseFile()` 打印 `$services` 赋值语句的原文，看下一行是否被并进注释。修法同上：**存为 UTF-8 with BOM** |

---

## 五、禁止行为

| 禁止 | 后果 |
|------|------|
| 用 `Start-Process` 启动长驻服务 | 终端调用被拖住数十分钟到数十小时 |
| 在脚本末尾 `while (-not $proc.HasExited)` 常驻等待 | 同上，且服务不退出就不返回 |
| 直接 `npx vite preview` / `cloudflared tunnel` 当前台命令 | 同上（历史单次 1353.8 分钟） |
| 用 `cmd /c` 做重定向 | toolhost 直接拦截：`The use of 'cmd /c' is blocked on Windows for safety` |
| 依赖 `Start-Process` 出来的进程「能扛住 OOM」 | 内存耗尽时进程半死不活，挂到机器重启 |
| 看到长耗时就直接重启 IDE | 会清掉现场，且对 job-hang 无效（重启只对真沙箱 deadlock 有效，见 `terminal-channel-failure.md`） |

---

## 六、配套动作（治本）

| # | 动作 | 备注 |
|---|------|------|
| 1 | **开启系统托管页面文件**（或手动设 48–64 GB） | 消除 Event 2004/26 与 OOM 根因。需管理员权限；当前会话 `IS_ADMIN=False` 时不可执行，需用户手动操作 |
| 2 | 定期清理**真正脱离业务**的旧长驻进程 | 判定标准：**没有活跃连接**（`Get-NetTCPConnection -State Established` 为 0）。**不要**杀 IDE 自身的 `Trae CN` / `node`（MCP server）/ `msedgewebview2` / 用户自己的 chrome —— 那些是当前 IDE 窗口的正常子进程 |
| 3 | 长驻服务统一走 `service_manager.ps1` / `launch_detached.ps1` | 见场景 3 `service-management-rules.md` |

---

## 七、CHANGELOG

| 日期 | 变更 |
|------|------|
| 2026-10-24 | 验证闭环：修 status.json 记「实际监听者 PID」（消除 LISTENER MISMATCH 误判）、前端等待 8→20 秒、`launch_detached` 日志占用自动 fallback；补两条踩坑（日志文件被遗留进程占用、无 BOM 行尾全角标点吃掉换行） |
| 2026-10-24 | 初版。定位「430 分钟」根因（终端等待后代进程树 + 页面文件缺失导致 OOM），落地 `launch_detached.ps1` 并改造 `start-mobile.ps1` / `service_manager.ps1` |
