# sync-integration-db.ps1 - v3.2 O10 实施
# 从 release 拉最新 DB 到 integration, 安全停 3018 → cp → 重启 3018
#
# 用法:
#   pwsh -File D:\filework\scripts\sync-integration-db.ps1            # 标准流程
#   pwsh -File D:\filework\scripts\sync-integration-db.ps1 -SkipRestart # 只 cp, 不重启 (高级)
#   pwsh -File D:\filework\scripts\sync-integration-db.ps1 -Force      # 跳过确认
#
# 触发时机 (SOP §4.2 T1/T2):
#   - release 有新 BUG cherry-pick 后
#   - worktrees/integration 落后 release > 1 commit
#   - 试跑期新 BUG 报告
#
# 行为:
#   1. Pre-check: release / integration DB 都存在, integration DB 不在 cp 中
#   2. (非 -SkipRestart) 停 integration 后端 (3018)
#   3. 等锁文件释放 (5 秒)
#   4. cp 前先 integrity_check release DB
#   5. 备份旧 integration DB 到 .bak
#   6. cp release DB → integration DB (overwrite)
#   7. cp 后 integrity_check integration DB, 失败自动回滚
#   8. (非 -SkipRestart) 重启 3018
#
# 注意:
#   - 此脚本只同步 DB, 不动代码. 代码同步见 SOP §4.2.
#   - 不影响前端 3007 (vite dev HMR 自动感知).
#   - [FIX 2026-07-04] 加 integrity_check 防止坏 DB 被覆盖 (历史事故: 246MB 坏 DB 静默写入)

[CmdletBinding()]
param(
    [string]$ReleasePath = "D:\filework\worktrees/release-prep",
    [string]$IntegrationPath = "D:\filework\worktrees/integration",
    [string]$PythonExe = "C:\Users\Administrator\AppData\Local\Python\pythoncore-3.14-64\python.exe",
    [int]$BackendPort = 3018,
    [int]$WaitTimeoutSec = 30,
    [switch]$SkipRestart,
    [switch]$Force
)

# 防中文乱码
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Host "=========================================="
Write-Host "Integration DB Sync (triggered: $timestamp)"
Write-Host "=========================================="

$releaseDb = "$ReleasePath\meta\architecture.db"
$integrationDb = "$IntegrationPath\meta\architecture.db"
$integrationLock = "$IntegrationPath\meta\.architecture.lock"
$backendLogOut = "$IntegrationPath\integration_3018_stdout.log"
$backendLogErr = "$IntegrationPath\integration_3018_stderr.log"

# --- Pre-checks ---

Write-Host "[1/6] Pre-checks: release DB / integration DB paths..."
if (-not (Test-Path $releaseDb)) {
    Write-Host "  [ERROR] Release DB not found: $releaseDb" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $IntegrationPath)) {
    Write-Host "  [ERROR] Integration-worktree not found: $IntegrationPath" -ForegroundColor Red
    Write-Host "  [HINT] Run setup-integration.ps1 first" -ForegroundColor Yellow
    exit 1
}
$releaseSize = [Math]::Round((Get-Item $releaseDb).Length / 1MB, 1)
$integrationSize = if (Test-Path $integrationDb) { [Math]::Round((Get-Item $integrationDb).Length / 1MB, 1) } else { 0 }
Write-Host "  [OK] release DB: $releaseSize MB" -ForegroundColor Green
Write-Host "  [INFO] integration DB (before): $integrationSize MB"

Write-Host "[2/6] Pre-checks: integration lock file..."
if (Test-Path $integrationLock) {
    $lockPidRaw = Get-Content $integrationLock -First 1 -ErrorAction SilentlyContinue
    $lockPid = if ($lockPidRaw -match '^\d+$') { [int]$lockPidRaw } else { $null }
    if ($lockPid) {
        $lockProc = Get-Process -Id $lockPid -ErrorAction SilentlyContinue
        if ($lockProc) {
            Write-Host "  [INFO] Lock held by live PID $lockPid ($($lockProc.ProcessName))" -ForegroundColor Yellow
            Write-Host "  [INFO] Will stop backend in step 3 to release lock" -ForegroundColor Yellow
        } else {
            Write-Host "  [WARN] Stale lock (PID $lockPid dead), will clean up" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [WARN] Lock file has invalid/empty PID content, will clean up" -ForegroundColor Yellow
    }
} else {
    Write-Host "  [OK] No lock file present" -ForegroundColor Green
}

# --- Confirm ---

if (-not $Force) {
    Write-Host ""
    Write-Host "[CONFIRM] About to overwrite integration DB with release DB" -ForegroundColor Cyan
    Write-Host "  From: $releaseDb ($releaseSize MB)"
    Write-Host "  To:   $integrationDb ($integrationSize MB)"
    $confirm = Read-Host "Proceed? (yes/no)"
    if ($confirm -ne "yes") {
        Write-Host "[CANCELLED] No DB sync performed" -ForegroundColor Yellow
        exit 0
    }
}

# --- Stop backend (if not SkipRestart) ---

if (-not $SkipRestart) {
    Write-Host "[3/6] Stopping integration backend (port $BackendPort)..."
    $backendConn = Get-NetTCPConnection -State Listen -LocalPort $BackendPort -ErrorAction SilentlyContinue
    if ($backendConn) {
        $backendPid = $backendConn.OwningProcess
        Write-Host "  Backend PID=$backendPid, killing..."
        try {
            Stop-Process -Id $backendPid -Force -ErrorAction Stop
            Write-Host "  [OK] Killed PID=$backendPid" -ForegroundColor Green
        } catch {
            Write-Host "  [ERROR] Failed to kill PID=$backendPid : $_" -ForegroundColor Red
            exit 1
        }
        Write-Host "  Waiting for port $BackendPort release..."
        $waited = 0
        while ($waited -lt $WaitTimeoutSec) {
            $c = Get-NetTCPConnection -State Listen -LocalPort $BackendPort -ErrorAction SilentlyContinue
            if (-not $c) {
                Write-Host "  [OK] Port $BackendPort released (waited ${waited}s)" -ForegroundColor Green
                break
            }
            Start-Sleep -Seconds 1
            $waited++
        }
        if ($waited -ge $WaitTimeoutSec) {
            Write-Host "  [ERROR] Port not released after ${WaitTimeoutSec}s" -ForegroundColor Red
            exit 1
        }
    } else {
        Write-Host "  [SKIP] Backend not running" -ForegroundColor Yellow
    }

    # Clean stale lock if exists
    if (Test-Path $integrationLock) {
        $lockPidRaw = Get-Content $integrationLock -First 1 -ErrorAction SilentlyContinue
        $lockPid = if ($lockPidRaw -match '^\d+$') { [int]$lockPidRaw } else { $null }
        $lockProc = if ($lockPid) { Get-Process -Id $lockPid -ErrorAction SilentlyContinue } else { $null }
        if (-not $lockProc) {
            Remove-Item $integrationLock -Force -ErrorAction SilentlyContinue
            Write-Host "  [OK] Stale lock removed" -ForegroundColor Green
        }
    }
} else {
    Write-Host "[3/6] (Skipped backend stop, -SkipRestart specified)" -ForegroundColor Yellow
}

# --- integrity_check helper ---

function Test-DbIntegrity {
    param([string]$DbPath)
    if (-not (Test-Path $DbPath)) { return @{ ok = $false; reason = "file not found" } }
    try {
        $output = & python -c "import sqlite3; conn = sqlite3.connect(r'$DbPath'); r = conn.execute('PRAGMA integrity_check').fetchone(); print('OK' if r and r[0] == 'ok' else 'FAIL: ' + (r[0] if r else 'no result'))" 2>&1
        $line = ($output | Select-Object -Last 1)
        if ($line -eq 'OK') { return @{ ok = $true; reason = $line } }
        else { return @{ ok = $false; reason = $line } }
    } catch {
        return @{ ok = $false; reason = "python check failed: $_" }
    }
}

# --- Pre-cp integrity check on release DB ---

if (-not $SkipIntegrityCheck) {
    Write-Host "[4/8] Pre-cp integrity check on release DB..."
    $releaseCheck = Test-DbIntegrity $releaseDb
    if (-not $releaseCheck.ok) {
        Write-Host "  [ERROR] Release DB integrity FAIL: $($releaseCheck.reason)" -ForegroundColor Red
        Write-Host "  [HINT] DO NOT sync a corrupt DB. Restore release DB first." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  [OK] release DB integrity OK" -ForegroundColor Green
} else {
    Write-Host "[4/8] (Skipped integrity check, -SkipIntegrityCheck specified)" -ForegroundColor Yellow
}

# --- Backup current integration DB ---

Write-Host "[5/8] Backing up current integration DB..."
$bakPath = "$integrationDb.bak.sync-$($timestamp -replace '[-: ]','')"
if (Test-Path $integrationDb) {
    try {
        Copy-Item -Path $integrationDb -Destination $bakPath -Force -ErrorAction Stop
        Write-Host "  [OK] Backup created: $bakPath" -ForegroundColor Green
    } catch {
        Write-Host "  [ERROR] Backup failed: $_" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "  [SKIP] No existing integration DB to backup" -ForegroundColor Yellow
    $bakPath = $null
}

# --- cp DB ---

Write-Host "[6/8] Copying DB from release → integration..."
try {
    Copy-Item -Path $releaseDb -Destination $integrationDb -Force -ErrorAction Stop
    Write-Host "  [OK] DB copied" -ForegroundColor Green
} catch {
    Write-Host "  [ERROR] cp failed: $_" -ForegroundColor Red
    if ($bakPath -and (Test-Path $bakPath)) {
        Write-Host "  [RECOVER] Rolling back to backup..." -ForegroundColor Yellow
        Copy-Item -Path $bakPath -Destination $integrationDb -Force -ErrorAction SilentlyContinue
        Write-Host "  [RECOVER] Rolled back to $bakPath" -ForegroundColor Yellow
    }
    exit 1
}

Write-Host "[7/8] Verifying copy + integrity..."
$newSize = [Math]::Round((Get-Item $integrationDb).Length / 1MB, 1)
if ($newSize -ne $releaseSize) {
    Write-Host "  [WARN] Size mismatch: $newSize MB vs release $releaseSize MB" -ForegroundColor Yellow
} else {
    Write-Host "  [OK] Sizes match ($newSize MB)" -ForegroundColor Green
}

if (-not $SkipIntegrityCheck) {
    $integrationCheck = Test-DbIntegrity $integrationDb
    if (-not $integrationCheck.ok) {
        Write-Host "  [ERROR] Integration DB integrity FAIL after cp: $($integrationCheck.reason)" -ForegroundColor Red
        if ($bakPath -and (Test-Path $bakPath)) {
            Write-Host "  [RECOVER] Rolling back to backup..." -ForegroundColor Yellow
            Copy-Item -Path $bakPath -Destination $integrationDb -Force -ErrorAction SilentlyContinue
            $rollbackCheck = Test-DbIntegrity $integrationDb
            if ($rollbackCheck.ok) {
                Write-Host "  [RECOVER] Rollback success. Integration DB restored to previous state." -ForegroundColor Green
                Write-Host "  [HINT] Original problem: cp produced corrupt DB (likely Windows cp + 246MB file race)" -ForegroundColor Yellow
                Write-Host "  [HINT] Try again or use ROBOCOPY instead of Copy-Item" -ForegroundColor Yellow
            } else {
                Write-Host "  [RECOVER] Rollback FAILED. Backup may also be corrupt." -ForegroundColor Red
                Write-Host "  [HINT] Run: python d:\filework\test.py --force-recover-db" -ForegroundColor Yellow
            }
        } else {
            Write-Host "  [HINT] No backup available. Manual recovery needed." -ForegroundColor Yellow
        }
        exit 1
    }
    Write-Host "  [OK] Integration DB integrity OK" -ForegroundColor Green
} else {
    Write-Host "  [SKIP] Post-cp integrity check (flag set)" -ForegroundColor Yellow
}

# --- Restart backend (if not SkipRestart) ---

if (-not $SkipRestart) {
    Write-Host "[6/6] Restarting integration backend (port $BackendPort)..."
    $env:AGENT_PORT = "$BackendPort"
    $backendProc = Start-Process -FilePath $PythonExe `
        -ArgumentList "waitress_server.py" `
        -RedirectStandardOutput $backendLogOut `
        -RedirectStandardError $backendLogErr `
        -WorkingDirectory $IntegrationPath `
        -PassThru -WindowStyle Hidden
    Write-Host "  [OK] Backend started, PID=$($backendProc.Id)" -ForegroundColor Green
    Write-Host "  Waiting for port $BackendPort LISTEN..."
    $waited = 0
    while ($waited -lt $WaitTimeoutSec) {
        $c = Get-NetTCPConnection -State Listen -LocalPort $BackendPort -ErrorAction SilentlyContinue
        if ($c) {
            Write-Host "  [OK] Backend port $BackendPort LISTEN (PID=$($c.OwningProcess), waited ${waited}s)" -ForegroundColor Green
            break
        }
        Start-Sleep -Seconds 1
        $waited++
    }
    if ($waited -ge $WaitTimeoutSec) {
        Write-Host "  [ERROR] Port not LISTEN after ${WaitTimeoutSec}s" -ForegroundColor Red
        Write-Host "  [HINT] Check $backendLogErr" -ForegroundColor Yellow
        exit 1
    }
} else {
    Write-Host "[8/8] (Skipped backend restart, -SkipRestart specified)" -ForegroundColor Yellow
    Write-Host "  [REMINDER] You must restart backend manually for new DB to load" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=========================================="
Write-Host "[OK] Integration DB synced"
Write-Host "  Source: $releaseDb ($releaseSize MB)"
Write-Host "  Target: $integrationDb ($newSize MB)"
if (-not $SkipRestart) {
    Write-Host "  Backend restarted on port $BackendPort"
}
Write-Host "  Verify: pwsh -File D:\filework\scripts\status-integration.ps1"
Write-Host "=========================================="