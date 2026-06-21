#!/usr/bin/env pwsh
# ============================================================================
# Agent Bootstrap Script v1.1 (2026-06-21)
# ============================================================================
# [UPGRADE v1.1] 非交互式 + Doctor 模式
#   - 新增 -Doctor 参数 (只报告不创建)
#   - 新增 -SkipConfirm 参数 (跳过主工作树确认)
#   - 新增 -AutoPort 参数 (自动分配可用端口)
#   - AgentName/Port 在 -Doctor 模式下不再 Mandatory
# ============================================================================
# Usage (interactive):
#   powershell -File scripts/agent_bootstrap.ps1 -AgentName <name> -Port <3011-3019>
#
# Usage (non-interactive, for AI agents):
#   powershell -File scripts/agent_bootstrap.ps1 -AgentName agent-A -Port 3011 -SkipConfirm
#
# Usage (Doctor mode - just report environment):
#   powershell -File scripts/agent_bootstrap.ps1 -Doctor
#
# Port Allocation:
#   3010 = main (reserved)
#   3011-3019 = agent worktrees
# ============================================================================

param(
    [string]$AgentName,

    [int]$Port,

    [string]$BaseBranch = "main",

    [switch]$Doctor = $false,

    [switch]$SkipConfirm = $false,

    [switch]$AutoPort = $false
)

# =====  echo =====
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  AGENT BOOTSTRAP v1.1 -  5 " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  L1:  commit ( worktree)" -ForegroundColor Yellow
Write-Host "  L2:  stash" -ForegroundColor Yellow
Write-Host "  L3:  stash@{0}" -ForegroundColor Yellow
Write-Host "  L4: commit  .agent-status.json" -ForegroundColor Yellow
Write-Host "  L5: ,  (-Port)" -ForegroundColor Yellow
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# ===== [NEW v1.1] Doctor 模式 =====
# 仅输出环境报告，不创建 worktree. 用于 AI Agent 启动前 SOP.
if ($Doctor) {
    Write-Host "[DOCTOR MODE]  Report only, no changes" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "[1/5]  repo root ..." -ForegroundColor Cyan
    $repoRoot = git rev-parse --show-toplevel 2>$null
    if (-not $repoRoot) {
        Write-Host "[ERROR] Not in a git repository" -ForegroundColor Red
        exit 1
    }
    $repoRoot = $repoRoot.Trim()
    Write-Host "      $repoRoot" -ForegroundColor White
    Write-Host ""

    Write-Host "[2/5]  worktree ..." -ForegroundColor Cyan
    $worktreesRaw = git worktree list --porcelain 2>&1
    $count = 0
    $currentPath = ($repoRoot).Replace("\","/")
    foreach ($line in $worktreesRaw) {
        if ($line -match '^worktree ') {
            $count++
            $wtPath = $line.Substring(9)
            $marker = ""
            if ($wtPath.Replace("\","/") -eq $currentPath) {
                $marker = " <-- [CURRENT]"
            }
            Write-Host "      [$count] $wtPath$marker" -ForegroundColor White
        } elseif ($line -match '^branch ') {
            Write-Host "          $($line.Substring(7))" -ForegroundColor Gray
        }
    }
    Write-Host ""

    Write-Host "[3/5]  port ..." -ForegroundColor Cyan
    $coordDir = Join-Path (Split-Path -Parent $repoRoot) ".coord"
    $portsFile = Join-Path $coordDir "ports.json"
    if (Test-Path $portsFile) {
        $portsData = Get-Content $portsFile -Raw | ConvertFrom-Json
        Write-Host "      Allocated:" -ForegroundColor White
        if ($portsData.allocated) {
            $portsData.allocated.PSObject.Properties | ForEach-Object {
                Write-Host "        $($_.Name) -> $($_.Value.owner) ($($_.Value.status))" -ForegroundColor White
            }
        }
        Write-Host "      Reserved:" -ForegroundColor White
        if ($portsData.reserved) {
            $portsData.reserved.PSObject.Properties | ForEach-Object {
                Write-Host "        $($_.Name) -> $($_.Value.owner) ($($_.Value.status))" -ForegroundColor White
            }
        }
    } else {
        Write-Host "      (no .coord/ports.json yet)" -ForegroundColor Gray
    }
    Write-Host ""

    Write-Host "[4/5]  worktree ..." -ForegroundColor Cyan
    Set-Location $repoRoot
    $statusOutput = git status --short 2>&1
    $statusLines = @($statusOutput | Where-Object { $_ -match '\S' })
    Write-Host "      : $($statusLines.Count) " -ForegroundColor White
    if ($statusLines.Count -gt 0) {
        Write-Host "      : " -ForegroundColor Yellow
        $statusLines | Select-Object -First 10 | ForEach-Object {
            Write-Host "        $_" -ForegroundColor Gray
        }
        if ($statusLines.Count -gt 10) {
            Write-Host "        ...  $($statusLines.Count - 10) " -ForegroundColor Gray
        }
    }
    Write-Host ""

    Write-Host "[5/5]  pre-commit hook ..." -ForegroundColor Cyan
    $hookPath = Join-Path $repoRoot ".git/hooks/pre-commit"
    if (Test-Path $hookPath) {
        $hookVer = "unknown"
        Get-Content $hookPath | Select-Object -First 10 | ForEach-Object {
            if ($_ -match 'v(\d+\.\d+)') { $hookVer = "v$($Matches[1])" }
        }
        Write-Host "      : $hookVer" -ForegroundColor White
    } else {
        Write-Host "      [WARN]  pre-commit hook  " -ForegroundColor Red
    }

    # ===== [NEW v1.2] V2.1 P2-4: PowerShell Redirection Risk Check =====
    Write-Host ""
    Write-Host "[6/6 V2.1]  PowerShell redirection risk (V2.1 P2-4) ..." -ForegroundColor Cyan
    $psCheckScript = Join-Path $repoRoot "scripts/check_powershell_redirection.py"
    if (Test-Path $psCheckScript) {
        try {
            $env:PYTHONIOENCODING = "utf-8"
            $psOutput = python $psCheckScript check 2>&1
            Write-Host "      [OK] PS redirection check tool available" -ForegroundColor Green
            Write-Host "      See: scripts/PS_REDIRECTION_RISKS.md" -ForegroundColor Gray
        } catch {
            Write-Host "      [WARN] PS redirection check failed" -ForegroundColor Yellow
        }
    } else {
        Write-Host "      [WARN] scripts/check_powershell_redirection.py not found" -ForegroundColor Yellow
    }

    # ===== [NEW v1.4] Worktree 状态检查 =====
    Write-Host ""
    Write-Host "[0/7 WORKTREE] Checking worktree status (v1.4 v2026.06.21) ..." -ForegroundColor Cyan
    try {
        $mainHead = (git -C $repoRoot rev-parse --short main 2>$null)
        $currentHead = (git -C $repoRoot rev-parse --short HEAD 2>$null)
        if ($mainHead -and $currentHead -and $mainHead -ne $currentHead) {
            $behindCount = (git -C $repoRoot log --oneline HEAD..main 2>$null | Measure-Object).Count
            if ($behindCount -gt 0) {
                Write-Host "      [WARN] 当前 worktree 落后 main $behindCount commits" -ForegroundColor Yellow
                Write-Host "      [INFO] 升级步骤: git fetch origin && git rebase main" -ForegroundColor Gray
            } else {
                Write-Host "      [OK] 当前 HEAD = $currentHead (main: $mainHead)" -ForegroundColor Green
            }
        } else {
            Write-Host "      [OK] worktree 已同步 main ($currentHead)" -ForegroundColor Green
        }
    } catch {
        Write-Host "      [INFO] 跳过 worktree 检查 (非 git 仓库)" -ForegroundColor Gray
    }

    # ===== [NEW v1.3] V1 Debug Infrastructure: Comprehensive Diagnose =====
    Write-Host ""
    Write-Host "[7/7 V1 DEBUG] Comprehensive debug environment diagnose (v2026.06.21) ..." -ForegroundColor Cyan
    $diagnoseScript = Join-Path $repoRoot "scripts/debug/env/diagnose.py"
    if (Test-Path $diagnoseScript) {
        try {
            $env:PYTHONIOENCODING = "utf-8"
            $diagnoseOutput = python $diagnoseScript 2>&1
            # 诊断脚本自己会输出，这里只需要提示完成
            Write-Host "      [OK] diagnose completed - see output above" -ForegroundColor Green
            Write-Host "      See: .trae/rules/debug-infrastructure-v20260621.md" -ForegroundColor Gray
        } catch {
            Write-Host "      [WARN] diagnose failed" -ForegroundColor Yellow
        }
    } else {
        Write-Host "      [WARN] scripts/debug/env/diagnose.py not found" -ForegroundColor Yellow
    }

    # ===== [NEW v1.4] 根目录调试脚本检测 =====
    Write-Host ""
    Write-Host "[V1.4] Checking root debug scripts ..." -ForegroundColor Cyan
    $checkDebug = Join-Path $repoRoot "scripts/debug/check_debug_script_in_root.py"
    if (Test-Path $checkDebug) {
        try {
            $env:PYTHONIOENCODING = "utf-8"
            python $checkDebug 2>&1 | Select-Object -First 5
        } catch {
            Write-Host "      [WARN] check_debug_script_in_root.py failed" -ForegroundColor Yellow
        }
    }

    Write-Host ""
    Write-Host "[DOCTOR COMPLETE]" -ForegroundColor Green
    exit 0
}

# ===== [NEW v1.1] AutoPort =====
if ($AutoPort -and -not $Port) {
    $coordDir = Join-Path (Split-Path -Parent (git rev-parse --show-toplevel)) ".coord"
    $portsFile = Join-Path $coordDir "ports.json"
    $usedPorts = @{}
    if (Test-Path $portsFile) {
        $portsData = Get-Content $portsFile -Raw | ConvertFrom-Json
        if ($portsData.allocated) {
            $portsData.allocated.PSObject.Properties | ForEach-Object { $usedPorts[$_.Name] = $true }
        }
    }
    for ($tryPort = 3011; $tryPort -le 3019; $tryPort++) {
        if (-not $usedPorts.ContainsKey("$tryPort")) {
            $Port = $tryPort
            Write-Host "[AutoPort]  port $Port" -ForegroundColor Cyan
            break
        }
    }
    if (-not $Port) {
        Write-Host "[ERROR]  3011-3019  " -ForegroundColor Red
        exit 1
    }
}

# ===== [v1.1]  param  (Doctor/AutoPort   ) =====
if (-not $Doctor -and -not $AutoPort) {
    if (-not $AgentName) {
        Write-Host "[ERROR] -AgentName  " -ForegroundColor Red
        Write-Host "  Doctor : powershell -File scripts/agent_bootstrap.ps1 -Doctor" -ForegroundColor Yellow
        Write-Host "  : powershell -File scripts/agent_bootstrap.ps1 -AgentName agent-X -Port 3011" -ForegroundColor Yellow
        exit 1
    }
    if (-not $Port) {
        Write-Host "[ERROR] -Port  (-AutoPort )" -ForegroundColor Red
        exit 1
    }
}

# =====  =====
if ($Port -lt 3011 -or $Port -gt 3019) {
    Write-Host "[ERROR]  3011-3019  (main = 3010)" -ForegroundColor Red
    exit 1
}

if ($AgentName -match '[^a-zA-Z0-9_-]') {
    Write-Host "[ERROR] AgentName " -ForegroundColor Red
    exit 1
}

# =====  =====
$repoRoot = git rev-parse --show-toplevel
$repoRoot = $repoRoot.Trim()
$parentDir = Split-Path -Parent $repoRoot
$worktreePath = Join-Path $parentDir "${AgentName}-worktree"
$branchName = "$AgentName-$BaseBranch"

Set-Location $repoRoot

# =====  main  =====
Write-Host "[1/6] ..." -ForegroundColor Cyan
$mainStatus = git status --porcelain 2>&1
if ($mainStatus) {
    Write-Host "[WARN] :" -ForegroundColor Yellow
    Write-Host $mainStatus
    Write-Host ""
    # [FIX v1.1] 支持 -SkipConfirm 非交互模式
    if ($SkipConfirm) {
        Write-Host "[SkipConfirm]  " -ForegroundColor Yellow
    } else {
        $confirm = Read-Host "? (y/N)"
        if ($confirm -ne 'y') {
            Write-Host "[ERROR] " -ForegroundColor Red
            exit 1
        }
    }
}

# =====  worktree =====
Write-Host "[2/6]  worktree: $worktreePath (: $branchName, : $Port)" -ForegroundColor Cyan
$worktreeResult = git worktree add -b $branchName $worktreePath $BaseBranch 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Worktree :" -ForegroundColor Red
    Write-Host $worktreeResult
    exit 1
}

Set-Location $worktreePath

# =====  .env.agent =====
Write-Host "[3/6]  .env.agent ()" -ForegroundColor Cyan
$envContent = @"
# Generated by agent_bootstrap.ps1 v1.0 on $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
AGENT_NAME=$AgentName
AGENT_PORT=$Port
AGENT_WORKTREE=$worktreePath
AGENT_BRANCH=$branchName
AGENT_BASE_BRANCH=$BaseBranch
AGENT_IN_WORKTREE=1

#  (3004 + offset)
VITE_PORT=$((3004 + ($Port - 3010)))
"@
$envPath = Join-Path $worktreePath ".env.agent"
Set-Content -Path $envPath -Value $envContent -Encoding UTF8

# =====  =====
Write-Host "[4/6]  .coord/ports.json" -ForegroundColor Cyan
$coordDir = Join-Path $parentDir ".coord"
$portsFile = Join-Path $coordDir "ports.json"

if (-not (Test-Path $coordDir)) {
    New-Item -ItemType Directory -Path $coordDir -Force | Out-Null
}

if (Test-Path $portsFile) {
    # Convert from JSON (PSCustomObject -> Hashtable via @())
    $jsonContent = Get-Content $portsFile -Raw | ConvertFrom-Json
    $ports = @{
        allocated = @{}
        reserved = @{}
    }
    if ($jsonContent.allocated) {
        foreach ($key in $jsonContent.allocated.PSObject.Properties) {
            $ports.allocated[$key.Name] = @{
                owner = $key.Value.owner
                role = $key.Value.role
                status = $key.Value.status
            }
            if ($key.Value.worktree) { $ports.allocated[$key.Name].worktree = $key.Value.worktree }
            if ($key.Value.branch) { $ports.allocated[$key.Name].branch = $key.Value.branch }
            if ($key.Value.allocated_at) { $ports.allocated[$key.Name].allocated_at = $key.Value.allocated_at }
        }
    }
    if ($jsonContent.reserved) {
        foreach ($key in $jsonContent.reserved.PSObject.Properties) {
            $ports.reserved[$key.Name] = @{
                owner = $key.Value.owner
                role = $key.Value.role
                status = $key.Value.status
            }
        }
    }
} else {
    $ports = @{
        allocated = @{}
        reserved = @{
            "3010" = @{ owner = "main"; role = "production"; status = "running" }
        }
    }
}

# 
$portStr = $Port.ToString()
if ($ports.allocated.$portStr -or $ports.reserved.$portStr) {
    Write-Host "[ERROR]  $Port " -ForegroundColor Red
    Write-Host " -Port  (3011-3019)" -ForegroundColor Red
    exit 1
}

$ports.allocated.$portStr = @{
    owner = $AgentName
    role = "agent-worktree"
    status = "active"
    worktree = $worktreePath
    branch = $branchName
    allocated_at = (Get-Date -Format "o")
}

$ports | ConvertTo-Json -Depth 5 | Set-Content -Path $portsFile -Encoding UTF8

# =====  =====
Write-Host "[5/6]  (,  npm install)" -ForegroundColor Cyan
Write-Host "  cd $worktreePath" -ForegroundColor Gray
Write-Host "  npm install" -ForegroundColor Gray

# =====  AGENT_GUIDELINES.md () =====
$guidelinesPath = Join-Path $parentDir "AGENT_GUIDELINES.md"
if (-not (Test-Path $guidelinesPath)) {
    Write-Host "  [WARN] AGENT_GUIDELINES.md , " -ForegroundColor Yellow
}

# =====  =====
Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host "  [OK] AGENT BOOTSTRAP " -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Agent : $AgentName" -ForegroundColor White
Write-Host "  Worktree:   $worktreePath" -ForegroundColor White
Write-Host "  :       $branchName" -ForegroundColor White
Write-Host "  :   $Port" -ForegroundColor White
Write-Host "  :   $((3004 + ($Port - 3010)))" -ForegroundColor White
Write-Host "  :   .coord/ports.json" -ForegroundColor White
Write-Host "  Env :   $worktreePath\.env.agent" -ForegroundColor White
Write-Host ""
Write-Host "  :" -ForegroundColor Cyan
Write-Host "    cd $worktreePath" -ForegroundColor White
Write-Host "    npm install" -ForegroundColor White
Write-Host "    cp d:\filework\spec_template.md .\spec.md  # " -ForegroundColor White
Write-Host "    # " -ForegroundColor White
Write-Host ""
Write-Host "  :" -ForegroundColor Cyan
Write-Host "    python test.py --port $Port --single <test_path>" -ForegroundColor White
Write-Host "    : http://localhost:$((3004 + ($Port - 3010)))/" -ForegroundColor White
Write-Host ""
Write-Host "  :" -ForegroundColor Cyan
Write-Host "    cd $worktreePath" -ForegroundColor White
Write-Host "    git add . && git commit -m '...'" -ForegroundColor White
Write-Host "    #  merge" -ForegroundColor White
Write-Host ""