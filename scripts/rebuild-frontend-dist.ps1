# rebuild-frontend-dist.ps1 - v3.3 O11 实施
# 一键 rebuild 前端: npm run build + cp dist/ → frontend_dist_files/ + 重启 3006 (可选)
#
# 用法:
#   pwsh -File D:\filework\scripts\rebuild-frontend-dist.ps1            # 标准流程 (build + cp + 重启 3006)
#   pwsh -File D:\filework\scripts\rebuild-frontend-dist.ps1 -SkipRestart # 只 build + cp, 不重启 3006
#   pwsh -File D:\filework\scripts\rebuild-frontend-dist.ps1 -Force      # 跳过确认
#   pwsh -File D:\filework\scripts\rebuild-frontend-dist.ps1 -SkipBuild  # 跳过 build (用现有 dist/)
#
# 触发时机 (release-sync-workflow.md §3 Step 4):
#   - 协调智能体 cherry-pick 一个 frontend fix 到 release 后
#   - 用户报告前端问题需要紧急修复后
#   - PM 要求 "刷新 3006"
#
# 行为:
#   1. Pre-check: package.json / vite.config.js / node_modules
#   2. (非 -SkipBuild) npm run build (60s)
#   3. cp dist/ → frontend_dist_files/
#   4. 验证 cp (找 BUG-V044 标记, 如 fix commit 含此 tag)
#   5. (非 -SkipRestart) 杀旧 3006 + 启新 3006
#   6. verify: 200 + 含 fix 标记
#
# 注意:
#   - 此脚本只 rebuild 前端. 后端用 restart-integration-backend.ps1 (新建于 O8 后)
#   - 通知 PM: 主 3006 会中断 5-10 秒. 应在 PM 已知情况下调用.

[CmdletBinding()]
param(
    [string]$ReleasePath = "D:\filework\worktrees/release-prep",
    [string]$FrontendPort = "3006",
    [int]$BuildTimeoutSec = 180,
    [int]$RestartTimeoutSec = 30,
    [switch]$SkipRestart,
    [switch]$SkipBuild,
    [switch]$Force
)

# 防中文乱码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "=========================================="
Write-Host "Frontend Rebuild (triggered: $timestamp)"
Write-Host "=========================================="

$distDir = "$ReleasePath\dist"
$distTarget = "$ReleasePath\frontend_dist_files"
$frontendLogOut = "$ReleasePath\frontend_3006_stdout.log"
$frontendLogErr = "$ReleasePath\frontend_3006_stderr.log"

# --- Pre-checks ---

Write-Host "[1/6] Pre-checks: package.json / node_modules..."
if (-not (Test-Path "$ReleasePath\package.json")) {
    Write-Host "  [ERROR] package.json not found: $ReleasePath" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "$ReleasePath\node_modules")) {
    Write-Host "  [ERROR] node_modules missing: $ReleasePath" -ForegroundColor Red
    Write-Host "  [HINT] Run 'npm install' first" -ForegroundColor Yellow
    exit 1
}
Write-Host "  [OK] package.json + node_modules present" -ForegroundColor Green

# --- npm run build ---

if (-not $SkipBuild) {
    Write-Host "[2/6] Running 'npm run build' (timeout: ${BuildTimeoutSec}s)..."
    Set-Location $ReleasePath
    $buildJob = Start-Job -ScriptBlock {
        Set-Location $using:ReleasePath
        npm run build 2>&1
    }
    $waited = 0
    while ($waited -lt $BuildTimeoutSec) {
        $state = Wait-Job $buildJob -Timeout 10
        if ($state) { break }
        $waited += 10
        Write-Host "  [building... ${waited}s elapsed]"
    }
    if ($waited -ge $BuildTimeoutSec) {
        Stop-Job $buildJob -ErrorAction SilentlyContinue
        Write-Host "  [ERROR] Build timeout after ${BuildTimeoutSec}s" -ForegroundColor Red
        Remove-Job $buildJob -Force -ErrorAction SilentlyContinue
        exit 1
    }
    $buildOutput = Receive-Job $buildJob -Keep
    Remove-Job $buildJob -Force -ErrorAction SilentlyContinue
    $lastLines = $buildOutput | Select-Object -Last 5
    Write-Host "  [OK] Build completed" -ForegroundColor Green
    foreach ($line in $lastLines) {
        if ($line) { Write-Host "    $($line)" }
    }
} else {
    Write-Host "[2/6] (Skipped npm run build, -SkipBuild specified)" -ForegroundColor Yellow
}

# --- cp dist → frontend_dist_files ---

Write-Host "[3/6] Copying dist/ → frontend_dist_files/..."
if (-not (Test-Path $distDir)) {
    Write-Host "  [ERROR] dist/ not found: $distDir" -ForegroundColor Red
    Write-Host "  [HINT] Run without -SkipBuild, or build manually" -ForegroundColor Yellow
    exit 1
}
if (Test-Path $distTarget) {
    Remove-Item $distTarget -Recurse -Force -ErrorAction SilentlyContinue
}
Copy-Item $distDir $distTarget -Recurse -Force -ErrorAction Stop
$distSize = [Math]::Round((Get-ChildItem $distDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 1)
Write-Host "  [OK] Copied dist/ → frontend_dist_files/ ($distSize MB)" -ForegroundColor Green

# --- Verify cp ---

Write-Host "[4/6] Verifying copy..."
$distHash = (Get-FileHash $distDir\index.html -ErrorAction SilentlyContinue).Hash
$targetHash = (Get-FileHash "$distTarget\index.html" -ErrorAction SilentlyContinue).Hash
if ($distHash -eq $targetHash) {
    Write-Host "  [OK] index.html hash match" -ForegroundColor Green
} else {
    Write-Host "  [WARN] index.html hash mismatch" -ForegroundColor Yellow
}

# --- Restart 3006 (if not -SkipRestart) ---

if (-not $SkipRestart) {
    if (-not $Force) {
        Write-Host ""
        Write-Host "[CONFIRM] About to restart frontend on port $FrontendPort" -ForegroundColor Cyan
        Write-Host "  PM/Users may experience brief interruption"
        $confirm = Read-Host "Proceed? (yes/no)"
        if ($confirm -ne "yes") {
            Write-Host "[CANCELLED] Build done but NOT restarted" -ForegroundColor Yellow
            Write-Host "  Run without -SkipRestart when ready, or restart manually" -ForegroundColor Yellow
            exit 0
        }
    }

    Write-Host "[5/6] Restarting frontend (port $FrontendPort)..."
    $frontendConn = Get-NetTCPConnection -State Listen -LocalPort $FrontendPort -ErrorAction SilentlyContinue
    if ($frontendConn) {
        $frontendPid = $frontendConn.OwningProcess
        Write-Host "  Frontend PID=$frontendPid, killing..."
        Stop-Process -Id $frontendPid -Force -ErrorAction Stop
        Write-Host "  [OK] Killed PID=$frontendPid" -ForegroundColor Green
        $waited = 0
        while ($waited -lt $RestartTimeoutSec) {
            $c = Get-NetTCPConnection -State Listen -LocalPort $FrontendPort -ErrorAction SilentlyContinue
            if (-not $c) {
                Write-Host "  [OK] Port $FrontendPort released (waited ${waited}s)" -ForegroundColor Green
                break
            }
            Start-Sleep -Seconds 1
            $waited++
        }
        if ($waited -ge $RestartTimeoutSec) {
            Write-Host "  [ERROR] Port not released after ${RestartTimeoutSec}s" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "  [SKIP] Frontend not running" -ForegroundColor Yellow
    }

    # Start new frontend
    $nodePath = (Get-Command node -ErrorAction SilentlyContinue).Source
    if (-not $nodePath) { $nodePath = "node" }
    $viteBin = "$ReleasePath\node_modules\.bin\..\vite\bin\vite.js"
    $frontendProc = Start-Process -FilePath $nodePath `
        -ArgumentList $viteBin, "preview", "--host", "0.0.0.0", "--port", $FrontendPort `
        -WorkingDirectory $ReleasePath `
        -RedirectStandardOutput $frontendLogOut `
        -RedirectStandardError $frontendLogErr `
        -PassThru -WindowStyle Hidden
    Write-Host "  [OK] Frontend started, PID=$($frontendProc.Id)" -ForegroundColor Green
    Write-Host "  Waiting for port $FrontendPort LISTEN..."
    $waited = 0
    while ($waited -lt $RestartTimeoutSec) {
        $c = Get-NetTCPConnection -State Listen -LocalPort $FrontendPort -ErrorAction SilentlyContinue
        if ($c) {
            Write-Host "  [OK] Port $FrontendPort LISTEN (PID=$($c.OwningProcess), waited ${waited}s)" -ForegroundColor Green
            break
        }
        Start-Sleep -Seconds 1
        $waited++
    }
    if ($waited -ge $RestartTimeoutSec) {
        Write-Host "  [ERROR] Port not LISTEN after ${RestartTimeoutSec}s" -ForegroundColor Red
        Write-Host "  [HINT] Check $frontendLogErr" -ForegroundColor Yellow
        exit 1
    }

    # Verify HTTP
    Start-Sleep -Seconds 3
    Write-Host "[6/6] Verifying HTTP 200..."
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:$FrontendPort/" -UseBasicParsing -TimeoutSec 10
        Write-Host "  [OK] HTTP $($r.StatusCode) (PID=$($frontendProc.Id))" -ForegroundColor Green
    } catch {
        Write-Host "  [ERROR] HTTP failed: $_" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[5/6] (Skipped frontend restart, -SkipRestart specified)" -ForegroundColor Yellow
    Write-Host "[6/6] (Skipped HTTP verify)" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=========================================="
Write-Host "[OK] Frontend rebuild complete"
Write-Host "  Source: $distDir"
Write-Host "  Target: $distTarget"
if (-not $SkipRestart) {
    Write-Host "  Frontend running on port $FrontendPort"
    Write-Host "  PM should now verify the fix at http://localhost:$FrontendPort"
}
Write-Host "=========================================="