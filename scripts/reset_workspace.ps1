<#
.SYNOPSIS
    Reset / cleanup AI temporary debug files (v5.0 service governance)
.DESCRIPTION
    Cleans .tmp/ directory + scripts/_* temp files + root _* temp files
    By default only files older than -DaysOld are removed, to avoid deleting active session temp files
.PARAMETER List
    Only list files that match the cleanup criteria, do not delete
.PARAMETER Clean
    Execute cleanup
.PARAMETER DaysOld
    Delete files older than the specified number of days (default 7)
.PARAMETER Force
    Force delete all temporary files (even those < DaysOld)
.EXAMPLE
    powershell -File scripts/reset_workspace.ps1 -List
    # List temp files older than 7 days
.EXAMPLE
    powershell -File scripts/reset_workspace.ps1 -Clean
    # Clean temp files older than 7 days
.EXAMPLE
    powershell -File scripts/reset_workspace.ps1 -Clean -Force
    # Force clean all temp files
.NOTES
    v5.0 (2026-09-02) - Companion to service governance v5.0
#>

param(
    [switch]$List,
    [switch]$Clean,
    [int]$DaysOld = 7,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host "=== reset_workspace.ps1 v5.0 (2026-09-02) ===" -ForegroundColor Cyan
Write-Host "Project: $ProjectRoot"
Write-Host "Mode: $(if ($List) { 'LIST ONLY' } elseif ($Clean) { 'CLEAN' } else { 'LIST ONLY (default)' })"
Write-Host "DaysOld: $DaysOld $(if ($Force) { '(FORCE)' } else { '' })"
Write-Host ""

# 收集临时文件路径
$patterns = @(
    @{ Path = "$ProjectRoot\.tmp"; Pattern = '*'; Recurse = $true; Description = ".tmp/" }
    @{ Path = "$ProjectRoot\scripts"; Pattern = '_*.py'; Recurse = $false; Description = "scripts/_*.py" }
    @{ Path = "$ProjectRoot\scripts"; Pattern = '_*.txt'; Recurse = $false; Description = "scripts/_*.txt" }
    @{ Path = "$ProjectRoot\scripts"; Pattern = '_*.log'; Recurse = $false; Description = "scripts/_*.log" }
    @{ Path = "$ProjectRoot\scripts"; Pattern = '_*.ps1'; Recurse = $false; Description = "scripts/_*.ps1" }
    @{ Path = "$ProjectRoot\scripts"; Pattern = '_*.sh'; Recurse = $false; Description = "scripts/_*.sh" }
    @{ Path = "$ProjectRoot\scripts"; Pattern = '_*.bat'; Recurse = $false; Description = "scripts/_*.bat" }
    @{ Path = "$ProjectRoot\scripts"; Pattern = '_tmp_*'; Recurse = $true; Description = "scripts/_tmp_*" }
    @{ Path = "$ProjectRoot"; Pattern = '_*.py'; Recurse = $false; Description = "root/_*.py" }
    @{ Path = "$ProjectRoot"; Pattern = '_*.txt'; Recurse = $false; Description = "root/_*.txt" }
    @{ Path = "$ProjectRoot"; Pattern = '_*.log'; Recurse = $false; Description = "root/_*.log" }
    @{ Path = "$ProjectRoot"; Pattern = '_*.png'; Recurse = $false; Description = "root/_*.png" }
)

# Whitelist (preserve)
$whitelist = @(
    # Already .gitignore exempt (historical preserved scripts, do not clean)
    'scripts/_start_frontend.ps1',
    'scripts/_start_frontend_3004.ps1',
    'scripts/_start_frontend_3005.ps1',
    'scripts/_start_backend.ps1',
    # [2026-09-05] _start_backend_3010.ps1 已删除 (端口漂移源头: 裸启动 meta/server.py 到 3010,
    #   绕过 service_manager; 端口真源统一为 scripts/ports.json)
    'scripts/_start_all.py',
    'scripts/_find_vite.py',
    'scripts/_probe_ports.ps1',
    'scripts/_probe_ports_py.py',
    'scripts/_probe_ports_v2.ps1',
    'scripts/_probe_backend_py.ps1',
    'scripts/_manual_start.py',
    'scripts/_check_3010.py',
    'scripts/_wt_startup_probe.py',
    'scripts/_wt_service.py',
    'scripts/_wt_lifecycle.py',
    'scripts/_v33_state.py',
    'scripts/_v33_panel.py',
    'scripts/_sync_scripts.py',
    'scripts/_sync_precommit.py',
    'scripts/_session_cleanup.py',
    'scripts/_ports_sync.py',
    'scripts/_events.py',
    'scripts/_coord_log.py',
    'scripts/_coord_commit_guard.py',
    'scripts/_config_backup.py',
    '.tmp/.gitkeep',
    '.tmp/README.md'
)

function Get-CandidateFiles {
    $candidates = @()
    $now = Get-Date
    $cutoff = $now.AddDays(-$DaysOld)

    foreach ($p in $patterns) {
        if (-not (Test-Path $p.Path)) { continue }
        $files = Get-ChildItem -Path $p.Path -Filter $p.Pattern -Recurse:$p.Recurse -ErrorAction SilentlyContinue
        foreach ($f in $files) {
            $rel = $f.FullName.Substring($ProjectRoot.Length + 1) -replace '\\', '/'
            if ($whitelist -contains $rel) { continue }

            # .tmp/.gitkeep 和 .tmp/README.md Always skip
            if ($f.Name -eq '.gitkeep' -or $f.Name -eq 'README.md') { continue }

            # Date check
            $age = $now - $f.LastWriteTime
            $isOld = $age.TotalDays -ge $DaysOld

            if ($Force -or $isOld) {
                $candidates += [PSCustomObject]@{
                    Path = $f.FullName
                    Rel = $rel
                    LastWrite = $f.LastWriteTime
                    AgeDays = [int]$age.TotalDays
                    Size = $f.Length
                    Description = $p.Description
                }
            }
        }
    }
    return $candidates
}

$candidates = Get-CandidateFiles

if ($candidates.Count -eq 0) {
    Write-Host "[OK] No temp files older than $DaysOld days." -ForegroundColor Green
    exit 0
}

# Statistics
$totalSize = ($candidates | Measure-Object -Property Size -Sum).Sum
Write-Host "Found $($candidates.Count) temp file(s) totaling $($totalSize / 1KB.ToString('F2')) KB:" -ForegroundColor Yellow
Write-Host ""

# Group by directory
$grouped = $candidates | Group-Object Description
foreach ($g in $grouped) {
    Write-Host "--- $($g.Name) ($($g.Count) files) ---" -ForegroundColor Magenta
    foreach ($f in $g.Group | Select-Object -First 10) {
        Write-Host "  $($f.Rel) ($($f.AgeDays)d, $($f.Size)B)"
    }
    if ($g.Count -gt 10) {
        Write-Host "  ... and $($g.Count - 10) more" -ForegroundColor DarkGray
    }
    Write-Host ""
}

if ($List -or -not $Clean) {
    Write-Host "Use -Clean to delete these files." -ForegroundColor Cyan
    exit 0
}

if ($Clean) {
    Write-Host "Cleaning $($candidates.Count) files..." -ForegroundColor Yellow
    $deleted = 0
    $failed = 0
    foreach ($f in $candidates) {
        try {
            Remove-Item $f.Path -Force -Recurse -ErrorAction Stop
            $deleted++
        } catch {
            Write-Host "  [FAIL] $($f.Rel): $_" -ForegroundColor Red
            $failed++
        }
    }
    Write-Host ""
    Write-Host "[DONE] Deleted: $deleted, Failed: $failed" -ForegroundColor Green
}