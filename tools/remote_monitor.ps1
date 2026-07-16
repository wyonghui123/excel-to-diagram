﻿﻿﻿﻿﻿﻿﻿﻿﻿# remote_monitor.ps1 - yonaa 远程监控 (SSH-less, 纯 HTTP)
# 用法:
#   powershell -ExecutionPolicy Bypass -File remote_monitor.ps1 -Mode once
#   powershell -ExecutionPolicy Bypass -File remote_monitor.ps1 -Mode watch -Interval 60
#   powershell -ExecutionPolicy Bypass -File remote_monitor.ps1 -Mode alerts

param(
    [string]$BE = "http://172.20.59.7:5001",
    [string]$LogService = "http://172.20.59.7:9101",
    [string]$Mode = "once",            # once | watch | alerts
    [int]$Interval = 60,               # watch 模式轮询间隔(秒)
    [string]$Token = "",               # admin token (可空, 内部获取)
    [string]$AdminUser = "admin",
    [string]$AdminPass = "admin123",
    [string]$ReportFile = ""           # 报告文件路径 (可选)
)

$ErrorActionPreference = "Continue"
$global:AlertLevel = 0
$global:Alerts = @()

# ─── 工具函数 ───────────────────────
function Write-Section($title) {
    Write-Host ""
    Write-Host "════════════════════════════════════════════" -ForegroundColor Cyan
    Write-Host "  $title" -ForegroundColor Cyan
    Write-Host "════════════════════════════════════════════" -ForegroundColor Cyan
}

function Add-Alert($level, $msg) {
    $global:Alerts += [PSCustomObject]@{Level=$level; Time=Get-Date -Format "HH:mm:ss"; Msg=$msg}
    if ($level -gt $global:AlertLevel) { $global:AlertLevel = $level }
}

function Get-Token {
    if ($Token) { return $Token }
    try {
        $r = Invoke-RestMethod -Uri "$BE/api/v2/action/user.authenticate" `
            -Method Post -ContentType "application/json" `
            -Body (@{username=$AdminUser; password=$AdminPass} | ConvertTo-Json) -TimeoutSec 10
        if ($r.success) { return $r.data.token }
    } catch {}
    return $null
}

# ─── 监控项 ─────────────────────────
function Test-BackendHealth {
    $r = [PSCustomObject]@{ok=$false; http=0; msg=""}
    try {
        $code = (Invoke-WebRequest "$BE/api/v1/health" -TimeoutSec 5 -UseBasicParsing).StatusCode
        $r.http = $code
        $r.ok = $code -in 200, 401, 410   # 410 = alive 但 db 未 init
        $r.msg = "HTTP $code"
    } catch {
        $r.msg = $_.Exception.Message
        Add-Alert 3 "❌ backend 不可达: $($r.msg)"
    }
    return $r
}

function Test-LogService {
    $r = [PSCustomObject]@{ok=$false; uptime=$null; total_fds=$null; load=$null}
    try {
        $h = Invoke-RestMethod "$LogService/api/health" -TimeoutSec 5
        $r.ok = $true
        $r.uptime = $h.uptime
        $sys = Invoke-RestMethod "$LogService/api/system" -TimeoutSec 10
        $r.total_fds = $sys.total_fds
        $r.load = $sys.load[0]
        if ($r.total_fds -gt 5000) {
            Add-Alert 2 "⚠️ total_fds=$($r.total_fds) 偏高 (泄漏嫌疑)"
        } elseif ($r.total_fds -gt 1000) {
            Add-Alert 1 "ℹ️ total_fds=$($r.total_fds)"
        }
        if ($r.load -gt 5) {
            Add-Alert 2 "⚠️ load_1m=$($r.load) 高"
        }
    } catch {
        Add-Alert 1 "ℹ️ log_service 不可达 (可能未启动/未放行 9101): $($_.Exception.Message)"
    }
    return $r
}

function Test-BOAction {
    $r = [PSCustomObject]@{ok=$false; success=0; fail=0; errors=@()}
    for ($i=1; $i -le 5; $i++) {
        try {
            $resp = Invoke-RestMethod -Uri "$BE/api/v2/action/user.authenticate" `
                -Method Post -ContentType "application/json" `
                -Body (@{username=$AdminUser; password=$AdminPass} | ConvertTo-Json) -TimeoutSec 10
            if ($resp.success) {
                $r.success++
            }
            if (-not $resp.success) {
                $r.fail++
                $r.errors += "[$i] $($resp.message)"
            }
        } catch {
            $r.fail++
            $r.errors += "[$i] $($_.Exception.Message)"
        }
    }
    $r.ok = ($r.fail -eq 0)
    if ($r.fail -gt 0) { Add-Alert 3 "❌ v2 BOAction 失败 $r.fail/5: $($r.errors -join '; ')" }
    return $r
}

function Test-BusinessLoad {
    param($token, [int]$count=100)
    $r = [PSCustomObject]@{ok=$false; success=0; fail=0}
    if (-not $token) { $r.ok=$false; $r.fail=$count; return $r }
    for ($i=1; $i -le $count; $i++) {
        try {
            $code = (Invoke-WebRequest "$BE/api/v2/bo/product?pageSize=5" `
                -Headers @{Authorization="Bearer $token"} -TimeoutSec 5 -UseBasicParsing).StatusCode
            if ($code -eq 200) {
                $r.success++
            }
            if ($code -ne 200) {
                $r.fail++
            }
        } catch { $r.fail++ }
    }
    $r.ok = ($r.fail -eq 0)
    if ($r.fail -gt 0) { Add-Alert 2 "⚠️ 业务请求失败 $r.fail/$count" }
    return $r
}

function Get-DiskIOErrors {
    if (-not (Test-Path "/opt/app/shared/logs" 2>$null)) {
        # 远端不能直接 ls, 跳过
        return $null
    }
    return $null
}

function Get-RecentErrorsFromLogService {
    param([int]$lines=50, [string]$grep="disk")
    if (-not $LogService) { return $null }
    try {
        $ub = New-Object System.UriBuilder($LogService)
        $ub.Path = "/api/log"
        $q = 'file=/opt/app/shared/logs/backend-v20260725_002.log&lines=' + $lines + '&grep=' + $grep
        $ub.Query = $q
        $r = Invoke-RestMethod $ub.Uri.AbsoluteUri -TimeoutSec 10
        return $r.output
    } catch { return $null }
}

# ─── 报告生成 ───────────────────────
function New-Report {
    param($BE, $logSvc, $boaction, $biz, $token)
    Write-Section "V007.35 远程监控报告 - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    Write-Host "Backend:    $BE"
    Write-Host "LogService: $LogService"
    Write-Host ""

    Write-Section "1. Backend 健康"
    if ($BE.ok) {
        Write-Host "  ✅ $($BE.msg)" -ForegroundColor Green
    }
    if (-not $BE.ok) {
        Write-Host "  ❌ $($BE.msg)" -ForegroundColor Red
    }

    Write-Section "2. log_service (9101)"
    if ($logSvc.ok) {
        Write-Host "  ✅ uptime: $($logSvc.uptime)s" -ForegroundColor Green
        Write-Host "  total_fds: $($logSvc.total_fds), load_1m: $($logSvc.load)"
    } else {
        Write-Host "  ❌ 不可达" -ForegroundColor Red
    }

    Write-Section "3. v2 BOAction 5 次 (V007.24 修复验证)"
    Write-Host "  成功 $($boaction.success)/5, 失败 $($boaction.fail)/5"
    if ($boaction.fail -gt 0) { Write-Host "  错误: $($boaction.errors -join '; ')" -ForegroundColor Red }

    Write-Section "4. 业务请求 100 个 (fd 缓存验证)"
    Write-Host "  成功 $($biz.success)/100, 失败 $($biz.fail)/100"
    if ($biz.fail -gt 0) {
        Write-Host "  业务异常!" -ForegroundColor Red
    }
    if ($biz.fail -eq 0) {
        Write-Host "  ✅ 业务完全可用" -ForegroundColor Green
    }

    Write-Section "5. 告警汇总"
    $noAlerts = $true
    foreach ($a in $global:Alerts) {
        $color = "Gray"
        if ($a.Level -ge 3) { $color = "Red" }
        if ($a.Level -eq 2) { $color = "Yellow" }
        Write-Host ("  [{0} L{1}] {2}" -f $a.Time, $a.Level, $a.Msg) -ForegroundColor $color
        $noAlerts = $false
    }
    if ($noAlerts) { Write-Host "  ✅ 无告警" -ForegroundColor Green }
    return $global:AlertLevel
}

# ─── 主流程 ─────────────────────────
$token = Get-Token
$backendRes = Test-BackendHealth
$logSvc = Test-LogService
$boaction = Test-BOAction
$biz = Test-BusinessLoad -token $token -count 100

$alertLevel = New-Report -backend $backendRes -logSvc $logSvc -boaction $boaction -biz $biz -token $token

# watch 模式
if ($Mode -eq "watch") {
    Write-Host ""
    Write-Host "进入 watch 模式 (每 $Interval 秒轮询一次, Ctrl+C 停止)" -ForegroundColor Cyan
    while ($true) {
        Start-Sleep -Seconds $Interval
        $global:Alerts = @()
        $global:AlertLevel = 0
        $token = Get-Token
        $backendRes = Test-BackendHealth
        $logSvc = Test-LogService
        $boaction = Test-BOAction
        $biz = Test-BusinessLoad -token $token -count 50
        $alertLevel = New-Report -backend $backendRes -logSvc $logSvc -boaction $boaction -biz $biz -token $token
    }
}

# 报告写到文件
if ($ReportFile) {
    $global:Alerts | ConvertTo-Json | Out-File -FilePath $ReportFile -Append
    Write-Host ""
    Write-Host "告警已追加到: $ReportFile"
}

# exit code: 0=OK, 1=warn, 2=error, 3=critical
exit [Math]::Min($alertLevel, 3)
