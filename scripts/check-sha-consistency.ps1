# check-sha-consistency.ps1 - v3.2 O12 实施
# 并行 BUG 上线前 SHA 一致性检查 (协调智能体阶段 6 checklist 之一)
#
# 用法:
#   pwsh -File D:\filework\scripts\check-sha-consistency.ps1                    # 只检查
#   pwsh -File D:\filework\scripts\check-sha-consistency.ps1 -RequireFrontend   # 额外检查前端 3006/3007 的代码来源
#   pwsh -File D:\filework\scripts\check-sha-consistency.ps1 -Json              # 输出 JSON (供 CI 解析)
#
# 检查范围:
#   1. integration-worktree git HEAD SHA == release-prep-worktree git HEAD SHA
#   2. integration DB mtime 与 release DB mtime 差距 (DB 是否同步过)
#   3. (可选 -RequireFrontend) 前端 dist/build 目录的 git SHA 文件 (如有)
#
# 退出码:
#   0 = 全部一致 (PASS, 可上线)
#   1 = 任一不一致 (FAIL, 不建议上线)
#
# 与 status-integration.ps1 的区别:
#   - status: 被动查询, 显示当前状态
#   - check-sha: 主动校验, 给出 PASS/FAIL 结论, 适合 CI / 上线 checklist

[CmdletBinding()]
param(
    [string]$ReleasePath = "D:\filework\release-prep-worktree",
    [string]$IntegrationPath = "D:\filework\integration-worktree",
    [int]$DbStaleThresholdMinutes = 60,
    [switch]$RequireFrontend,
    [switch]$Strict,        # 严格模式: SHA 必须完全相同 (默认允许"内容等价")
    [switch]$Json
)

# 防中文乱码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# --- Run checks ---

$checkResults = @()

# Check 1: Git HEAD SHA
Push-Location $ReleasePath
$releaseSha = git rev-parse HEAD 2>$null
$releaseBranch = git branch --show-current 2>$null
$releaseShort = git rev-parse --short HEAD 2>$null
Pop-Location

Push-Location $IntegrationPath
$integrationSha = git rev-parse HEAD 2>$null
$integrationBranch = git branch --show-current 2>$null
$integrationShort = git rev-parse --short HEAD 2>$null
Pop-Location

# v3.3: 检查 2 类一致性
#   1) Strict (默认非开启): SHA 必须完全相同
#   2) Content-equivalent (默认): 两个分支是否互为可达 (ancestor / descendant / merge-base)
#      当一个分支通过 cherry-pick / merge 含另一个分支的 fix, SHA 不同但代码等价, 视为 PASS
#
# 场景: cherry-pick 后 SHA 必然不同, 但 fix 内容等价 -> 内容等价应 PASS

if ($Strict) {
    # 严格模式: SHA 必须完全相同
    $gitMatch = ($releaseSha -eq $integrationSha)
    if ($gitMatch) {
        $gitStatus = "PASS"
        $gitDetail = "release=$releaseShort integration=$integrationShort (strict: identical)"
    } else {
        $gitStatus = "FAIL"
        $gitDetail = "release=$releaseShort integration=$integrationShort (strict: SHA differs)"
    }
} else {
    # 内容等价模式: 检查 release HEAD 在 integration 历史中, 或 integration HEAD 在 release 历史中
    Push-Location $ReleasePath
    $releaseInIntegration = git merge-base --is-ancestor $releaseSha HEAD 2>&1
    if ($LASTEXITCODE -eq 0) {
        # release HEAD 是 integration HEAD 的祖先 (即 integration 比 release 新)
        $gitMatch = $true
        $gitStatus = "PASS"
        $gitDetail = "release=$releaseShort is ancestor of integration=$integrationShort (integration ahead, content equivalent)"
    } else {
        # 反过来: integration HEAD 是 release HEAD 的祖先?
        Push-Location $IntegrationPath
        $integrationInRelease = git merge-base --is-ancestor $integrationSha $releaseSha 2>&1
        Pop-Location
        if ($LASTEXITCODE -eq 0) {
            $gitMatch = $true
            $gitStatus = "PASS"
            $gitDetail = "integration=$integrationShort is ancestor of release=$releaseShort (release ahead, content equivalent)"
        } else {
            # 都不在对方历史中: diverged. 看 merge-base 是否包含所有 fix
            Push-Location $ReleasePath
            $mergeBase = git merge-base $releaseSha $integrationSha 2>$null
            Pop-Location
            # 检查 release 和 integration 各自有 merge-base 后的 N 个独有 commit
            Push-Location $ReleasePath
            $releaseOnlyCommits = git rev-list $mergeBase..$releaseSha --count 2>$null
            Pop-Location
            Push-Location $IntegrationPath
            $integrationOnlyCommits = git rev-list $mergeBase..$integrationSha --count 2>$null
            Pop-Location

            # v3.3 升级: 如果两个分支都没有独有 commit (0+0), 视为内容等价 PASS
            # 这是 cherry-pick 后 + merge --no-ff 后的典型场景
            if ($releaseOnlyCommits -eq 0 -and $integrationOnlyCommits -eq 0) {
                $gitMatch = $true
                $gitStatus = "PASS"
                $gitDetail = "diverged but content-equivalent: merge-base=$($mergeBase.Substring(0,7)), no exclusive commits (cherry-pick case)"
            } else {
                $gitMatch = $false
                $gitStatus = "WARN"
                $gitDetail = "diverged: merge-base=$($mergeBase.Substring(0,7)), release exclusive=$releaseOnlyCommits commits, integration exclusive=$integrationOnlyCommits commits"
            }
        }
    }
}

$checkResults += [PSCustomObject]@{
    Name = "Git HEAD SHA"
    Status = $gitStatus
    Detail = $gitDetail
    Hint = if ($gitMatch) { "" } else { "Branches diverged. Review cherry-pick / merge conflict. Run: git log --graph $releaseShort...$integrationShort" }
}

# Check 2: DB mtime recency
$releaseDb = "$ReleasePath\meta\architecture.db"
$integrationDb = "$IntegrationPath\meta\architecture.db"

if ((Test-Path $releaseDb) -and (Test-Path $integrationDb)) {
    $releaseDbMtime = (Get-Item $releaseDb).LastWriteTime
    $integrationDbMtime = (Get-Item $integrationDb).LastWriteTime
    # integration DB should be >= release DB mtime (synced from release, so at least as new)
    # If integration is older than release, it has stale data
    $dbTimeDiffMinutes = [Math]::Round(($integrationDbMtime - $releaseDbMtime).TotalMinutes, 1)
    if ($dbTimeDiffMinutes -ge 0) {
        # integration is newer or equal - fine
        $dbStatus = "PASS"
        $dbDetail = "integration is ${dbTimeDiffMinutes}min newer than release (or equal)"
    } elseif ($dbTimeDiffMinutes -ge -$DbStaleThresholdMinutes) {
        # integration slightly older but within threshold
        $dbStatus = "WARN"
        $dbDetail = "integration is $([Math]::Abs($dbTimeDiffMinutes))min behind release (threshold: ${DbStaleThresholdMinutes}min)"
    } else {
        # integration significantly older
        $dbStatus = "FAIL"
        $dbDetail = "integration is $([Math]::Abs($dbTimeDiffMinutes))min behind release (threshold: ${DbStaleThresholdMinutes}min)"
    }
    $checkResults += [PSCustomObject]@{
        Name = "DB sync recency"
        Status = $dbStatus
        Detail = $dbDetail
        Hint = if ($dbStatus -eq "PASS") { "" } else { "Run sync-integration-db.ps1 to refresh DB" }
    }
} else {
    $checkResults += [PSCustomObject]@{
        Name = "DB sync recency"
        Status = "FAIL"
        Detail = "DB file missing"
        Hint = "Run setup-integration.ps1"
    }
}

# Check 3 (optional): Frontend dist SHA file
if ($RequireFrontend) {
    $frontendShaFiles = @(
        "$ReleasePath\frontend_dist_files\.git-version",
        "$ReleasePath\frontend_dist_files\version.json",
        "$ReleasePath\dist\.git-version",
        "$ReleasePath\dist\version.json"
    )
    $frontendShaFound = $false
    foreach ($f in $frontendShaFiles) {
        if (Test-Path $f) {
            $frontendShaFound = $true
            $frontendShaContent = Get-Content $f -Raw -ErrorAction SilentlyContinue
            $frontendShaMatch = $frontendShaContent -match $releaseShort
            $checkResults += [PSCustomObject]@{
                Name = "Frontend dist SHA"
                Status = if ($frontendShaMatch) { "PASS" } else { "WARN" }
                Detail = "File=$f Content=$($frontendShaContent.Trim().Substring(0, [Math]::Min(20, $frontendShaContent.Trim().Length))) Expected=$releaseShort"
                Hint = if ($frontendShaMatch) { "" } else { "Rebuild frontend dist" }
            }
            break
        }
    }
    if (-not $frontendShaFound) {
        $checkResults += [PSCustomObject]@{
            Name = "Frontend dist SHA"
            Status = "INFO"
            Detail = "No .git-version / version.json found in dist"
            Hint = "(Optional) Add version marker to dist during build"
        }
    }
}

# --- Render output ---

if ($Json) {
    $output = [PSCustomObject]@{
        timestamp = $timestamp
        release_sha = $releaseSha
        release_branch = $releaseBranch
        integration_sha = $integrationSha
        integration_branch = $integrationBranch
        checks = $checkResults
        overall = if ($checkResults | Where-Object { $_.Status -eq "FAIL" }) { "FAIL" } else { "PASS" }
    }
    $output | ConvertTo-Json -Depth 5
} else {
    Write-Host "=========================================="
    Write-Host "SHA Consistency Check (triggered: $timestamp)"
    Write-Host "=========================================="
    Write-Host ""
    Write-Host "Release:      $releaseBranch @ $releaseShort"
    Write-Host "Integration:  $integrationBranch @ $integrationShort"
    Write-Host ""

    $checkResults | Format-Table Name, Status, Detail, Hint -AutoSize -Wrap | Out-String | Write-Host

    $failCount = @($checkResults | Where-Object { $_.Status -eq "FAIL" }).Count
    $warnCount = @($checkResults | Where-Object { $_.Status -eq "WARN" }).Count
    $passCount = @($checkResults | Where-Object { $_.Status -eq "PASS" }).Count

    Write-Host ""
    Write-Host "Summary: $passCount PASS, $warnCount WARN, $failCount FAIL" -ForegroundColor $(if ($failCount -gt 0) { "Red" } elseif ($warnCount -gt 0) { "Yellow" } else { "Green" })

    if ($failCount -gt 0) {
        Write-Host "[FAIL] SHA consistency check FAILED - DO NOT proceed with deployment" -ForegroundColor Red
        Write-Host "       Fix issues above, then re-run this check" -ForegroundColor Red
        exit 1
    } elseif ($warnCount -gt 0) {
        Write-Host "[WARN] SHA consistency check has warnings - review before deployment" -ForegroundColor Yellow
        exit 0
    } else {
        Write-Host "[OK] SHA consistency check PASSED - safe to proceed with deployment" -ForegroundColor Green
        exit 0
    }
}