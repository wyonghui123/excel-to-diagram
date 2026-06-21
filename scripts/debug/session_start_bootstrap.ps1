# SessionStart bootstrap script for Trae IDE
# This runs at the start of every Trae session to:
# 1. Detect sandbox L5 health
# 2. Write environment status to .trae/debug/
# 3. Auto-start watchdog if not running
# 4. Surface key info to the AI via status files

$ErrorActionPreference = "Continue"

# Find project root
$p = $env:TRAE_PROJECT_DIR
if (-not $p) {
    $p = (Get-Location).Path
    # Walk up to find .trae directory
    $check = $p
    while ($check -and -not (Test-Path (Join-Path $check ".trae"))) {
        $parent = Split-Path -Parent $check
        if ($parent -eq $check) { break }
        $check = $parent
    }
    if (Test-Path (Join-Path $check ".trae")) {
        $p = $check
    }
}

if (-not $p) {
    Write-Host "[SessionStart] Cannot determine project root"
    exit 0
}

$debugDir = Join-Path $p ".trae\debug"
$statusFile = Join-Path $debugDir "session_start_status.json"

# Ensure debug dir exists
if (-not (Test-Path $debugDir)) {
    New-Item -ItemType Directory -Path $debugDir -Force | Out-Null
}

# Collect environment status
$status = @{
    timestamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    project_root = $p
}

# Backend port check (3010)
$backendConn = Get-NetTCPConnection -LocalPort 3010 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($backendConn) {
    $status.backend = @{
        status = "running"
        pid = $backendConn.OwningProcess
        port = 3010
    }
} else {
    $status.backend = @{
        status = "down"
        port = 3010
    }
}

# Frontend port check (3004)
$frontendConn = Get-NetTCPConnection -LocalPort 3004 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($frontendConn) {
    $status.frontend = @{
        status = "running"
        pid = $frontendConn.OwningProcess
        port = 3004
    }
} else {
    $status.frontend = @{
        status = "down"
        port = 3004
    }
}

# Git status (short)
$gitStatus = & git -C $p status --short 2>&1
$status.git = @{
    clean = ($gitStatus -eq "")
    file_count = if ($gitStatus) { ($gitStatus | Measure-Object).Count } else { 0 }
}

# Git branch
$branch = & git -C $p branch --show-current 2>&1
$status.git.branch = $branch

# Worktree list
$worktrees = & git -C $p worktree list 2>&1
$status.worktrees = @()
if ($LASTEXITCODE -eq 0 -and $worktrees) {
    foreach ($wt in $worktrees) {
        $status.worktrees += $wt
    }
}

# Write status file
$json = $status | ConvertTo-Json -Depth 3
Set-Content -Path $statusFile -Value $json -Encoding UTF8 -Force

# Print short summary (visible to AI)
Write-Host "[SessionStart] Backend: $($status.backend.status), Frontend: $($status.frontend.status), Branch: $branch, Uncommitted: $($status.git.file_count) files"
Write-Host "[SessionStart] Status file: $statusFile"
