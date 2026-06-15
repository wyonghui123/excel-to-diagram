# agent_run.ps1
# [P0 v3.18.5+] AI Agent 统一运行入口 (拦截违规命令, 自动合规)

param(
    [Parameter(Position=0)]
    [ValidateSet('run','service','status','stop','restart','ports')]
    [string]$Command = 'run',

    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$RestArgs
)

$ErrorActionPreference = 'Continue'

# ===== 全路径常量 =====
$RootDir    = 'd:/filework/excel-to-diagram'
$TestPyPath = 'd:/filework/test.py'
$SmPath     = 'd:/filework/excel-to-diagram/scripts/service_manager.ps1'

# ===== 1. 端口自动分配 =====
function Initialize-AgentPort {
    if ($env:AGENT_PORT) { return }

    $assignedPort = $null
    foreach ($p in 3011..3019) {
        $sf = Join-Path $RootDir (".service_status_$p.json")
        $lf = Join-Path $RootDir (".service_manager_$p.lock")
        if ((Test-Path $sf) -or (Test-Path $lf)) { continue }
        $assignedPort = $p
        break
    }
    if ($assignedPort) {
        $env:AGENT_PORT = $assignedPort
        Write-Host "[AUTO-PORT] $assignedPort" -ForegroundColor Cyan
    } else {
        $env:AGENT_PORT = 3010
        Write-Host "[AUTO-PORT-WARN] 3011-3019 全占, fallback 3010" -ForegroundColor Yellow
    }
}

# ===== 2. service_manager 调用 =====
function Invoke-Sm {
    param([string]$SmCmd)
    & powershell.exe -File $SmPath @($SmCmd, '-Port', $env:AGENT_PORT)
    return $LASTEXITCODE
}

function Invoke-SmNoPort {
    param([string]$SmCmd)
    & powershell.exe -File $SmPath @($SmCmd)
    return $LASTEXITCODE
}

# ===== 3. 调度命令 =====
function Do-Status   { exit (Invoke-Sm 'status') }
function Do-Service  { exit (Invoke-Sm 'start') }
function Do-Stop     { exit (Invoke-Sm 'stop') }
function Do-Restart  { exit (Invoke-Sm 'restart') }
function Do-Ports    { exit (Invoke-SmNoPort 'list-locks') }

function Do-Run {
    if (-not $RestArgs -or $RestArgs.Count -eq 0) {
        Write-Host "用法: agent_run.ps1 run [--all|--file|--single|--unit|--integration]" -ForegroundColor Yellow
        Write-Host "    或: agent_run.ps1 run npx playwright test <spec>" -ForegroundColor Yellow
        Write-Host "    或: agent_run.ps1 run pytest <path>" -ForegroundColor Yellow
        exit 1
    }

    # 拦截 1: npx playwright test -> python test.py --file
    $isPlaywright = ($RestArgs.Count -ge 3 -and $RestArgs[0] -eq 'npx' -and $RestArgs[1] -eq 'playwright' -and $RestArgs[2] -eq 'test')
    if ($isPlaywright) {
        Write-Host "[REWRITE] npx playwright test -> python test.py --file" -ForegroundColor Yellow
        $specFiles = @()
        $otherArgs = @()
        for ($i = 3; $i -lt $RestArgs.Count; $i++) {
            $arg = $RestArgs[$i]
            if ($arg -match '\.spec\.js$') { $specFiles += $arg }
            else { $otherArgs += $arg }
        }

        $failed = 0
        foreach ($spec in $specFiles) {
            $normalized = $spec -replace '^e2e/', '' -replace '\.spec\.js$', ''
            $testPath = "e2e/$normalized.spec.js"
            Write-Host ""
            Write-Host "=== spec: $testPath ===" -ForegroundColor Cyan
            & python $TestPyPath --port $env:AGENT_PORT --file $testPath @otherArgs
            if ($LASTEXITCODE -ne 0) { $failed++ }
        }
        exit $failed
    }

    # 拦截 2: pytest / python -m pytest -> python test.py
    $isPytest = ($RestArgs[0] -eq 'pytest')
    $isPytestModule = ($RestArgs.Count -ge 3 -and $RestArgs[0] -eq 'python' -and $RestArgs[1] -eq '-m' -and $RestArgs[2] -eq 'pytest')
    if ($isPytest -or $isPytestModule) {
        Write-Host "[REWRITE] pytest -> python test.py" -ForegroundColor Yellow
        $startIdx = if ($isPytest) { 1 } else { 3 }
        $pytestArgs = @()
        if ($startIdx -lt $RestArgs.Count) {
            $pytestArgs = $RestArgs[$startIdx..($RestArgs.Count - 1)]
        }
        $hasMode = $false
        foreach ($a in $pytestArgs) {
            if ($a -match '^--(all|failed|file|single|unit|integration|skip)$') { $hasMode = $true; break }
        }
        if (-not $hasMode) { $pytestArgs = @('--unit') + $pytestArgs }
        & python $TestPyPath --port $env:AGENT_PORT @pytestArgs
        exit $LASTEXITCODE
    }

    # 拦截 3: python test.py 不带 --port -> 自动补
    $testPyWin = $TestPyPath.Replace('/', '\')
    $isTestPy = ($RestArgs.Count -ge 2 -and $RestArgs[0] -eq 'python' -and $RestArgs[1] -eq $testPyWin)
    if ($isTestPy) {
        if ($RestArgs -notcontains '--port') {
            Write-Host "[AUTO-INJECT] --port $env:AGENT_PORT" -ForegroundColor Cyan
            & python @RestArgs --port $env:AGENT_PORT
        } else {
            & python @RestArgs
        }
        exit $LASTEXITCODE
    }

    # 拦截 4: python agent_test.py 不带 --port -> 自动补
    $isAgentTestPy = ($RestArgs.Count -ge 2 -and $RestArgs[0] -eq 'python' -and ($RestArgs[1] -like '*agent_test.py'))
    if ($isAgentTestPy) {
        if ($RestArgs -notcontains '--port') {
            Write-Host "[AUTO-INJECT] --port $env:AGENT_PORT" -ForegroundColor Cyan
            & python @RestArgs --port $env:AGENT_PORT
        } else {
            & python @RestArgs
        }
        exit $LASTEXITCODE
    }

    # 默认透传
    $cmdLine = $RestArgs -join ' '
    Write-Host ('[PASSTHROUGH] ' + $cmdLine) -ForegroundColor Gray
    & $RestArgs[0] @($RestArgs[1..($RestArgs.Count - 1)])
    exit $LASTEXITCODE
}

# ===== Main =====
Initialize-AgentPort

if ($Command -eq 'run')      { Do-Run }
elseif ($Command -eq 'service')  { Do-Service }
elseif ($Command -eq 'status')   { Do-Status }
elseif ($Command -eq 'stop')     { Do-Stop }
elseif ($Command -eq 'restart')  { Do-Restart }
elseif ($Command -eq 'ports')    { Do-Ports }
else {
    Write-Host "[ERROR] Unknown command: $Command" -ForegroundColor Red
    exit 1
}