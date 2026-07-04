# Integration Scripts README

> 最后更新: 2026-07-04
> 适用范围: 协调智能体 (PM) 日常维护 integration 环境 (3007/3018)
> 上游文档: [../INFRA_HANDOVER.md](../INFRA_HANDOVER.md) (SOP v3.2)

---

## 1. 脚本清单 (5 件套)

| 脚本 | O 编号 | 功能 | 何时用 |
|---|---|---|---|
| [`setup-integration.ps1`](./setup-integration.ps1) | (基线) | 一键准备/重置 integration-worktree | 首次部署 / 大改前 |
| [`start-integration.ps1`](./start-integration.ps1) | O7 | 一键启 integration (3018 + 3007) | 平时启停 |
| [`stop-integration.ps1`](./stop-integration.ps1) | O8 | 一键停 integration + 清锁 | 平时启停 |
| [`status-integration.ps1`](./status-integration.ps1) | O9 | 一键查 4 端口/进程/DB/锁/Git 同步 | **随时** |
| [`sync-integration-db.ps1`](./sync-integration-db.ps1) | O10 | 从 release 拉最新 DB → integration | release 有新 BUG cherry-pick 后 |
| [`check-sha-consistency.ps1`](./check-sha-consistency.ps1) | O12 | 上线前 SHA 一致性检查 (PASS/FAIL) | 并行 BUG 上线前 checklist |

---

## 2. 速查表 (Cheatsheet)

### 2.1 日常操作

```powershell
# 看当前状态 (推荐先跑)
pwsh -File D:\filework\scripts\status-integration.ps1

# 启 integration
pwsh -File D:\filework\scripts\start-integration.ps1

# 停 integration (会询问确认)
pwsh -File D:\filework\scripts\stop-integration.ps1

# 停 integration (脚本化, 跳过确认)
pwsh -File D:\filework\scripts\stop-integration.ps1 -Force
```

### 2.2 BUG 修复后同步流程

```powershell
# Step 1: 同步代码 (主仓库 → release → integration)
cd D:\filework\release-prep-worktree
git cherry-pick <commit-sha>          # 或 git pull (看场景)
# 此时 release 有新 commit

# Step 2: 同步 DB 到 integration
pwsh -File D:\filework\scripts\sync-integration-db.ps1
# 默认: 停 3018 → cp DB → 重启 3018 (含确认)
# -Force: 跳过确认

# Step 3: 验证 SHA 一致
pwsh -File D:\filework\scripts\check-sha-consistency.ps1
# Exit 0 = PASS, Exit 1 = FAIL (禁止部署)
```

### 2.3 上线前 checklist (v3.2 §8 阶段 6)

```powershell
# 1. SHA 一致性 (关键!)
pwsh -File D:\filework\scripts\check-sha-consistency.ps1
# 必须 exit 0 (无 FAIL)

# 2. 全局状态
pwsh -File D:\filework\scripts\status-integration.ps1
# 检查所有 4 个服务在跑, 2 个 DB 时间新鲜

# 3. (可选) JSON 输出给 CI 解析
pwsh -File D:\filework\scripts\check-sha-consistency.ps1 -Json | Out-File check.json
```

### 2.4 出问题时的快速恢复

```powershell
# 场景 A: integration 启不来 (端口占用)
pwsh -File D:\filework\scripts\stop-integration.ps1 -Force
pwsh -File D:\filework\scripts\start-integration.ps1

# 场景 B: integration 整个坏了 (代码/DB 都乱)
pwsh -File D:\filework\scripts\setup-integration.ps1 -Action reset
# (会自动重建 worktree + cp DB + cp node_modules)
pwsh -File D:\filework\scripts\start-integration.ps1

# 场景 C: 锁文件残留 (start 报 P0 lock 冲突)
# 看是哪个 PID 持有, 死了就删锁文件
Get-Content D:\filework\integration-worktree\meta\.architecture.lock
# 假设 PID 27460
Get-Process -Id 27460 -ErrorAction SilentlyContinue
# 如果不存在 (返回空), 删锁:
Remove-Item D:\filework\integration-worktree\meta\.architecture.lock
```

---

## 3. 端口 / 路径速查

### 3.1 端口

| 端口 | 服务 | 用途 |
|---|---|---|
| **3006** | vite preview (主前端) | 用户访问 |
| **3011** | waitress (主后端) | 用户访问 |
| **3007** | vite dev (integration 前端) | Agent 验证 |
| **3018** | waitress (integration 后端) | Agent 验证 |

### 3.2 路径

| 路径 | 说明 |
|---|---|
| `D:\filework\excel-to-diagram\` | 主仓库 (主工作台) |
| `D:\filework\release-prep-worktree\` | release worktree (3006/3011) |
| `D:\filework\integration-worktree\` | integration worktree (3007/3018) |
| `D:\filework\scripts\` | 本目录 (脚本) |
| `D:\filework\INFRA_HANDOVER.md` | 完整 SOP 文档 |
| `D:\filework\excel-to-diagram\PARALLEL_DEV_SOP.md` | v3.2 并行开发 SOP |

### 3.3 日志

启动后日志会写到 integration-worktree 根目录:

```
D:\filework\integration-worktree\integration_3018_stdout.log
D:\filework\integration-worktree\integration_3018_stderr.log
D:\filework\integration-worktree\integration_3007_stdout.log
D:\filework\integration-worktree\integration_3007_stderr.log
```

出问题先看 stderr。

---

## 4. 各脚本详细参数

### 4.1 start-integration.ps1

```powershell
pwsh -File D:\filework\scripts\start-integration.ps1
    [-IntegrationPath <path>]    # 默认 D:\filework\integration-worktree
    [-BackendPort <port>]       # 默认 3018
    [-FrontendPort <port>]      # 默认 3007
    [-PythonExe <path>]         # 默认 pythoncore-3.14-64
    [-WaitTimeoutSec <sec>]     # 默认 30 秒
```

**前置检查**: 端口空闲、文件就位、锁文件状态。
**自动顺序**: 启后端 → 等 3018 → 启前端 → 等 3007。

### 4.2 stop-integration.ps1

```powershell
pwsh -File D:\filework\scripts\stop-integration.ps1
    [-Force]                    # 跳过确认
    [-IntegrationPath <path>]
    [-WaitTimeoutSec <sec>]     # 默认 10 秒
```

**自动顺序**: 停前端 → 等 3007 → 停后端 → 等 3018 → 清理 stale 锁。
**会询问**: `Stop these processes? (yes/no)` (非 `-Force`)。

### 4.3 status-integration.ps1

```powershell
pwsh -File D:\filework\scripts\status-integration.ps1
```

**无参数**。固定查 4 端口/2 DB/2 锁 + Git SHA 比对。**最常用的脚本, 建议每改一处就跑一次**。

### 4.4 sync-integration-db.ps1

```powershell
pwsh -File D:\filework\scripts\sync-integration-db.ps1
    [-SkipRestart]              # 只 cp, 不停/启 3018
    [-Force]                    # 跳过确认
    [-BackendPort <port>]       # 默认 3018
    [-WaitTimeoutSec <sec>]     # 默认 30 秒
```

**触发时机** (SOP §4.2):
- T1: release 有新 BUG cherry-pick 后
- T2: integration-worktree 落后 release > 1 commit
- T3: 试跑期新 BUG 报告

**注意**: 此脚本**只同步 DB, 不同步代码**。代码同步见 SOP §4.2 (cherry-pick / merge / setup reset)。

### 4.5 check-sha-consistency.ps1

```powershell
pwsh -File D:\filework\scripts\check-sha-consistency.ps1
    [-DbStaleThresholdMinutes <min>]   # 默认 60
    [-RequireFrontend]                 # 额外检查前端 dist SHA 文件
    [-Json]                            # 输出 JSON (CI 用)
```

**Exit code**:
- `0` = PASS 或 WARN (可继续, WARN 建议 review)
- `1` = FAIL (**禁止部署**)

**检查项**:
1. Git HEAD SHA: release == integration
2. DB sync recency: integration DB 时间 vs release DB 时间 (默认 60 分钟阈值)
3. (可选) Frontend dist SHA 文件

---

## 5. 常见问题 (FAQ)

### Q1: status 显示 SHA 一致, 但 check-sha 显示 FAIL?

A: status 只看 Git SHA, check-sha 还看 DB 时间。
- 如果 DB 时间落后超过阈值, 即使代码同步也会 FAIL。
- 解决: 跑 `sync-integration-db.ps1`。

### Q2: start 报 "Port 3018 already LISTEN" 怎么办?

A: 端口被占, 通常是之前的 integration 没干净停。
- 先跑: `stop-integration.ps1 -Force`
- 再跑: `start-integration.ps1`

### Q3: 锁文件 `.architecture.lock` 残留怎么办?

A: 锁文件存的是持有 DB 的 PID。
```powershell
# 看锁内容
Get-Content D:\filework\integration-worktree\meta\.architecture.lock
# 看 PID 是否活着
Get-Process -Id <PID> -ErrorAction SilentlyContinue
# 死了就删
Remove-Item D:\filework\integration-worktree\meta\.architecture.lock
# 注意: 必须是 integration 的锁, 不是主 3011 的锁!
```

### Q4: 中文乱码(标题显示成 [1] 绔)

A: 这是 PowerShell 控制台 GBK 编码问题, 不是脚本 bug。
- 脚本已强制 UTF-8 输出 (`[Console]::OutputEncoding`)
- 在 Windows Terminal / VSCode 终端看就正常
- 在老 PowerShell ISE 看会乱, 不影响功能

### Q5: 启停顺序错了会怎样?

A: start 必须先启后端, stop 必须先停前端。
- 顺序错会导致依赖关系断 (前端连不到后端)
- 5 个脚本都内置了正确的顺序和超时保护, 不需要手动管

---

## 6. 维护记录 (CHANGELOG)

| 日期 | 变更人 | 内容 |
|---|---|---|
| 2026-07-04 | 协调智能体 | 创建 README.md, 汇总 5 脚本用法 |
| 2026-07-04 | 协调智能体 | O7/O8/O9/O10/O12 完成 |
| 2026-07-04 | 协调智能体 | sync-integration-db 加固: integrity_check + auto-rollback (历史事故: 246MB 坏 DB 静默写入) |
| 2026-07-04 | 开发智能体 | INFRA_HANDOVER.md v2 (4 遗漏已修) |

---

## 7. 相关文件

- [INFRA_HANDOVER.md](../INFRA_HANDOVER.md) - 完整 SOP (含 C1-C4 约束、6 步准备、10 优化项、故障排查)
- [PARALLEL_DEV_SOP.md](../excel-to-diagram/PARALLEL_DEV_SOP.md) - v3.2 并行开发规范
- [DEPLOY_HANDOVER_BUG_V###.md](../excel-to-diagram/) - 各 BUG 的部署交接文档

---

**快速入口**: 不知道干啥就先跑 `status-integration.ps1` 看现状。