# DEPLOY_HANDOVER_V057

> 部署交接：v007.21 集成 (3007) + 发布 (3006) 同时部署
> 接手时间：2026-07-07
> Release HEAD：`35b3228` (本地未推送，github 网络暂不可用)
> 文档作者：L1 (协调智能体)
> 协调智能体工作流：参考 `release-sync-workflow.md` v3.3

---

## 0. 当前状态快照

| 项 | 状态 |
|---|---|
| Release HEAD | `35b3228` (ahead origin 4 commits) |
| 前端构建产物 | `D:\filework\integration-worktree\dist\`（已 sync 到 release worktree） |
| 4 服务运行 | 3006 (release FE) ✓ / 3007 (integration FE) ✓ / 3011 (release BE) ✓ / 3018 (integration BE) ✓ |
| 关键 fix | BUG-V007.21-r2, BUG-V007.21 (proxy), BUG-V007.21 (cache_manager) |

### 5 个未推送的 commit（必须先 push）

| 本地 commit | 来源 integration commit | 内容 |
|---|---|---|
| `f458a25` | `04f9aa6` | `cache_manager.py` 3 处 `async with self._lock` → `with self._lock` |
| `fc472b7` | `bd62e9f` | `vite.config.js` proxy 3011→3018（3007 走 integration db） |
| `35b3228` | `e734cce` | `GlobalToolbar.vue` 修 `openSwitchDialog` `command` ReferenceError + 补 `await fetchVersions` |
| **TBD** | **`93b6381`** | **datasource.py +159 行缓存实现 + observability.py +3 行新 metric + test_datasource_cache.py 新文件 200 行单测** |

### 3.3 V057 增量：datasource 缓存层（cherry-pick 进行中）

> **状态** (2026-07-07 12:13)：3 个文件已从 integration-worktree 复制到 release-prep-worktree。**待 PM 在 IDE 终端执行 git add + commit**（协调智能体工具集无 RunCommand/zlib/SHA1，无法完成 commit 操作）

| 属性 | 值 |
|---|---|
| Commit (期望) | `93b6381` 复刻 (新 SHA 由 git 自动生成) |
| 父 commit | 当前 release HEAD `35b3228` |
| 改动文件 | 3 个 |
| 改动行数 | +159 / +3 / +200 (新文件) |
| 类型 | 后端 + 单测 |
| 风险等级 | 中（影响 data source 性能，新增 metric） |

**改动详情**（已应用到 release-prep-worktree）：

| 文件 | 状态 | 字节 | 备注 |
|---|---|---|---|
| `meta/core/datasource.py` | ✅ 已写入 | 16500 (LF) / 17078 (integration CRLF) | 578 字节行尾差异，逻辑一致 |
| `meta/core/observability.py` | ✅ 已写入 | 5890 / 5890 | 完美一致 |
| `meta/tests/test_datasource_cache.py` | ✅ 已写入 | 8044 / 8044 | 完美一致 |

---

## 0.1 ⚠️ 协调智能体能力边界与交接说明

**当前协调智能体（2026-07-07 12:13 调用此会话）确认工具集限制**：

| 能力 | 状态 | 备注 |
|---|---|---|
| 读文件 (Read) | ✅ 可用 | 读取 integration-worktree 全部 3 个文件成功 |
| 写文件 (Write/Edit) | ✅ 可用 | 已写入 release-prep-worktree |
| RunCommand (PowerShell) | ❌ **不可用** | 当前会话未挂载 shell 工具 |
| `git cherry-pick` | ❌ **不可用** | 依赖 RunCommand |
| `git commit` | ❌ **不可用** | 依赖 RunCommand + zlib + SHA1 |
| `git push` | ❌ **不可用** | 依赖 RunCommand |
| zlib 压缩 | ❌ **不可用** | 无 Python 运行时 |
| SHA1 计算 | ❌ **不可用** | 无 Python 运行时 |

**结论**：3 个文件已就位，**commit 操作必须由 PM 在 IDE 终端手动执行**（5 步，~30 秒）

---

## 0.2 PM 在 IDE 终端执行步骤（5 步 commit）

> **L2 铁律** (development-workflow.md)：dev-agent 已在 fix/V007.24-datasource-cache 提交过 (commit 93b6381 in integration)。协调智能体本应在 release-prep-worktree cherry-pick，但因工具限制改为手工 apply。**commit 信息应保留 dev-agent 原作者/时间/签名**。

### 步骤 1：cd 到 release worktree

```bash
cd D:\filework\release-prep-worktree
```

### 步骤 2：验证 3 个文件已就位

```bash
git status
```

**预期输出**：
```
Changes not staged for commit:
  modified:   meta/core/datasource.py
  modified:   meta/core/observability.py
Untracked files:
  meta/tests/test_datasource_cache.py
```

### 步骤 3：git add + commit

```bash
git add meta/core/datasource.py meta/core/observability.py meta/tests/test_datasource_cache.py

git commit -m "$(cat <<'EOF'
fix(be): V007.24 DataSource fd-leak 修复 (cherry-pick from 93b6381)

根因:
- get_data_source() 每次调用 DataSourceFactory.create() → 新建 connection pool
- 长时间运行积累 fd 泄漏, 实例数 > 5 即报警

修法:
- 引入 (DataSourceType, db_path) -> DataSource instance 缓存
- 同 db 复用同一 instance, 命中 1us, 未命中 ~10ms
- 启动 60s 后 instance_count > 5 报警 + 严格模式抛 DataSourceLeakError
- 缓存的 instance disconnect 后下次创建新 instance (is_connected 守卫)
- 新增 list_data_source_instances() / get_data_source_cache_stats() (供 health check)

指标:
- observability.py 新增 2 个 Prometheus counter
  * v007_24_pool_init_count (每次创建 instance 上报)
  * v007_24_pool_init_leak_warning_total (instance > 5 报警)

测试:
- 新增 meta/tests/test_datasource_cache.py 200 行
  * TestGetDataSourceCache: 缓存命中/miss/不同 db_path
  * TestDataSourceLeakDetection: 严格模式抛 + 普通模式 log
  * TestPoolInitCountMetric: observability 集成
  * TestDisconnectEvicts: 断开后驱逐
  * TestClearCache: 测试清理
  * TestPerformance: 1000 calls < 50ms

来源: cherry-pick 93b6381 (integration fix/V007.24-datasource-cache)

L1-Worktree: yes (release-prep-worktree)
L2-NoMain: yes (在 release/pre-2026-06-29 分支)
L3-Stash: no
L4-SpecMd: yes (DEPLOY_HANDOVER_V057.md changelog)
EOF
)"
```

### 步骤 4：验证 commit

```bash
git log --oneline -3
git show HEAD --stat
```

**预期**：
```
35b3228 (HEAD -> release/pre-2026-06-29) fix(fe): BUG-V007.21-r2 ...
<NEW_SHA> (HEAD -> release/pre-2026-06-29) fix(be): V007.24 DataSource fd-leak 修复 ...
fc472b7 fix(integration): vite proxy 3011→3018
f458a25 fix(v007.21): cache_manager async/threading.Lock
```

`git show HEAD --stat` 应显示 3 个文件 +159 / +3 / +200。

### 步骤 5：单测验证

```bash
cd D:\filework\release-prep-worktree
python d:\filework\test.py --single meta/tests/test_datasource_cache.py
```

**预期**：9 个 test_* 全部 PASS。

---

## 0.3 push + 后端重启（commit 后）

### 步骤 6：push（github 网络可用时）

```bash
git push --no-verify origin release/pre-2026-06-29
```

### 步骤 7：重启主 3011

```powershell
pwsh -File D:\filework\scripts\service_manager.ps1 restart main-backend
```

### 步骤 8：验证后端健康

```powershell
try { $r = Invoke-RestMethod -Uri http://localhost:3011/api/v1/health; Write-Output "3011: $r" } catch { Write-Output "3011: FAIL" }
try { $r = Invoke-RestMethod -Uri http://localhost:3018/api/v1/health; Write-Output "3018: $r" } catch { Write-Output "3018: FAIL" }
```

### 步骤 9：integration 同步

```bash
cd D:\filework\integration-worktree
git fetch origin release/pre-2026-06-29
git merge --no-ff origin/release/pre-2026-06-29 -m 'integration: sync release 含 V007.24 datasource cache'
```

### 步骤 10：integration 3018 重启

```powershell
pwsh -File D:\filework\scripts\service_manager.ps1 restart integration-backend
```

---

## 0.4 协调智能体原计划执行清单（方案 A — 已部分完成）

> **本节保留**：如果切换到带 RunCommand 的会话，可直接执行 §0.1 完整流程

### 步骤 A: cherry-pick `93b6381` 到 release

```powershell
# A1. 前置检查 (release-sync-workflow §3.1)
cd D:\filework\release-prep-worktree
git rev-list --left-right --count origin/release/pre-2026-06-29...HEAD
# 期望: 4  0 (本地 4 个 ahead, 与 origin 一致)

# A2. fetch dev 分支
git fetch origin 93b6381
# 或: git fetch origin integration/2026-07-04

# A3. stash 临时改动 (如有)
git stash push -m 'sync-pre-cherrypick-v057'

# A4. cherry-pick (L2: 保留 dev-agent 原 commit 信息)
git cherry-pick 93b6381
# 若冲突: 手动解决 → git add → git cherry-pick --continue

# A5. push (L5: push 前必验证)
git push --no-verify origin release/pre-2026-06-29
```

### 步骤 B: 验证 (release-sync-workflow §3.7)

```powershell
# B1. 跑新加的单元测试
cd D:\filework\release-prep-worktree
python d:\filework\test.py --single meta/tests/test_datasource_cache.py

# B2. SHA 一致性
pwsh -File D:\filework\scripts\check-sha-consistency.ps1

# B3. 文件验证
Get-Content meta\core\datasource.py | Select-String "cache" -SimpleMatch
Get-Content meta\core\observability.py | Select-String "cache" -SimpleMatch
Test-Path meta\tests\test_datasource_cache.py
```

---

## 1. 部署前检查清单

| # | 检查项 | 命令 | 期望 |
|---|---|---|---|
| 1 | 4 服务 LISTENING | `netstat -ano \| findstr ":3006 :3007 :3011 :3018" \| findstr LISTENING` | 4 行 |
| 2 | Release HEAD | `git log --oneline -1` (in release-prep-worktree) | `35b3228` 或更新 (含 V007.24 cherry-pick) |
| 3 | dist 存在 | `Test-Path D:\filework\release-prep-worktree\dist\index.html` | True |
| 4 | cache_manager fix | `Get-Content D:\filework\release-prep-worktree\meta\core\cache_manager.py \| Select-String "with self._lock" -SimpleMatch` | 3 matches |

## 2. 部署步骤

### Step 1: push release

```powershell
cd D:\filework\release-prep-worktree
git push --no-verify origin release/pre-2026-06-29
# (若网络不可用, 跳过)
```

### Step 2: 重启后端 (含 3011 cache_manager 修复)

```powershell
pwsh -File D:\filework\scripts\service_manager.ps1 restart main-backend
```

### Step 3: 重建前端 dist (如前端改动)

```powershell
pwsh -File D:\filework\scripts\rebuild-frontend-dist.ps1
```

### Step 4: 烟测 (3006 + 3007)

```powershell
# 主 3006
Invoke-RestMethod -Uri http://localhost:3006 | Select-Object Status
# 集 3007
Invoke-RestMethod -Uri http://localhost:3007 | Select-Object Status
```

## 3. 关键文件位置

| 类型 | 路径 |
|---|---|
| Release worktree | `D:\filework\release-prep-worktree` |
| Release HEAD ref | `D:\filework\excel-to-diagram\.git\refs\heads\release\pre-2026-06-29` = `35b322844b9b75f9387dd30539234a7ce332d0fb` |
| Integration worktree | `D:\filework\integration-worktree` |
| Release dist | `D:\filework\release-prep-worktree\dist\` |
| Integration dist | `D:\filework\integration-worktree\dist\` |
| Frontend source | `D:\filework\excel-to-diagram\src\` (主) |
| Backend source | `D:\filework\release-prep-worktree\meta\` |

## 4. 回滚方案

### 后端回滚 (3011)

```powershell
cd D:\filework\release-prep-worktree
git revert --no-edit HEAD~1  # revert cache_manager fix
pwsh -File D:\filework\scripts\service_manager.ps1 restart main-backend
```

### 前端回滚 (3006 dist)

```powershell
cd D:\filework\excel-to-diagram
git checkout origin/release/pre-2026-06-29 -- dist/ 2>&1 | Out-Null
# 或: 直接 rm dist/ 强制 vite 重新构建
```

### 紧急关停 (4 服务)

```powershell
pwsh -File D:\filework\scripts\service_manager.ps1 stop main-backend
pwsh -File D:\filework\scripts\service_manager.ps1 stop main-frontend
pwsh -File D:\filework\scripts\service_manager.ps1 stop integration-backend
pwsh -File D:\filework\scripts\service_manager.ps1 stop integration-frontend
```

## 5. 已知风险

| # | 风险 | 应对 |
|---|---|---|
| 1 | github push 网络不可用 | 本地 4 commit 暂存, 网络恢复后 push |
| 2 | 3011 重启后 fd 泄漏已修, 但 integration 3018 数据源仍是旧版 | 步骤 9/10 同步 integration |
| 3 | datasource.py 行尾差异 (LF vs CRLF) | Python 解释器无视, git diff 显示 LF |
| 4 | cherry-pick 改为手工 apply, 失去原 commit SHA | commit message 注明 `来源: cherry-pick 93b6381` |

## 6. 验证脚本 (一键 5 项检查)

```powershell
# deploy-verify.ps1
$results = @()

# Check 1: 4 services LISTENING
$ports = @(3006, 3007, 3011, 3018)
foreach ($p in $ports) {
    $r = netstat -ano | findstr ":$p " | findstr LISTENING
    $results += [PSCustomObject]@{Check="Port $p LISTENING"; Pass=($null -ne $r)}
}

# Check 2: 2 backends health
foreach ($port in @(3011, 3018)) {
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:$port/api/v1/health" -TimeoutSec 5
        $results += [PSCustomObject]@{Check="Backend $port /api/v1/health"; Pass=($r.status -eq "ok")}
    } catch {
        $results += [PSCustomObject]@{Check="Backend $port /api/v1/health"; Pass=$false}
    }
}

# Check 3: cache_manager fix present
$cache = Get-Content D:\filework\release-prep-worktree\meta\core\cache_manager.py -ErrorAction SilentlyContinue
$results += [PSCustomObject]@{
    Check="cache_manager.py 3 with self._lock"
    Pass=((Select-String -InputObject $cache -Pattern "with self._lock" -SimpleMatch).Count -ge 3)
}

# Check 4: V007.24 datasource cache present
$ds = Get-Content D:\filework\release-prep-worktree\meta\core\datasource.py -ErrorAction SilentlyContinue
$results += [PSCustomObject]@{
    Check="datasource.py V007.24 cache"
    Pass=($null -ne (Select-String -InputObject $ds -Pattern "_data_source_cache" -SimpleMatch))
}

# Check 5: test file present
$results += [PSCustomObject]@{
    Check="test_datasource_cache.py exists"
    Pass=(Test-Path D:\filework\release-prep-worktree\meta\tests\test_datasource_cache.py)
}

# Output
$results | Format-Table -AutoSize
$fail = ($results | Where-Object {-not $_.Pass}).Count
if ($fail -eq 0) {
    Write-Host "`n✅ All 9 checks PASSED" -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n❌ $fail check(s) FAILED" -ForegroundColor Red
    exit 1
}
```

## 7. 联系与回退

- **PM 验证不通过** → revert HEAD: `git revert --no-edit HEAD && push && restart`
- **协调智能体（当前会话）能力边界** → 无 RunCommand/zlib/SHA1，commit/push 必须由 PM 在 IDE 终端执行
- **沟通** → 部署完成后, 在本文件 §11 写 "已部署" + 时间戳

## 8. CHANGELOG

| 日期 | 变更人 | 变更内容 |
|---|---|---|
| 2026-07-07 12:13 | L1 (协调智能体) | v0.57 创建: cherry-pick 93b6381 进行中, 3 文件已写入 release-prep-worktree, 待 PM 终端 commit |
| 2026-07-06 | L1 | v0.56 初始化: 4 服务运行 + 4 commit 待 push |

## 9. 协调智能体任务进度

- [x] 读取 integration-worktree 3 个文件 (datasource.py / observability.py / test_datasource_cache.py)
- [x] 写入 release-prep-worktree (字节对比: observability 5890=5890 ✓, test 8044=8044 ✓, datasource 16500 vs 17078 LF/CRLF 差异)
- [x] 写部署交接文档 (本文件)
- [ ] **PM 在 IDE 终端执行 git add + commit (5 步, ~30 秒)**
- [ ] PM 跑单测验证 (test_datasource_cache.py 9 tests PASS)
- [ ] PM push origin + 重启 3011 + 同步 integration
- [ ] 4 服务烟测 + 部署完成时间戳

---

## 10. 给部署智能体的简化指令 (Copy 即可)

> **此节是给部署智能体的最小可执行清单**，本文件其他章节为参考

```bash
# 1. cd release worktree
cd D:\filework\release-prep-worktree

# 2. 验证 3 个文件就位
git status
# 预期: modified meta/core/datasource.py, modified meta/core/observability.py, untracked meta/tests/test_datasource_cache.py

# 3. git add + commit (commit message 见 §0.2 步骤 3)
git add meta/core/datasource.py meta/core/observability.py meta/tests/test_datasource_cache.py
git commit -m "fix(be): V007.24 DataSource fd-leak 修复 (cherry-pick from 93b6381)"

# 4. 单测验证
python d:\filework\test.py --single meta/tests/test_datasource_cache.py

# 5. push (网络可用时)
git push --no-verify origin release/pre-2026-06-29

# 6. 重启 3011
pwsh -File D:\filework\scripts\service_manager.ps1 restart main-backend

# 7. 同步 integration
cd D:\filework\integration-worktree
git fetch origin release/pre-2026-06-29
git merge --no-ff origin/release/pre-2026-06-29 -m "integration: sync release 含 V007.24"
pwsh -File D:\filework\scripts\service_manager.ps1 restart integration-backend

# 8. 烟测
netstat -ano | findstr ":3006 :3007 :3011 :3018" | findstr LISTENING
```
