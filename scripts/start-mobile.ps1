#Requires -Version 5.1
<#
.SYNOPSIS
    启动手机可访问的生产预览 + 公网隧道。

.DESCRIPTION
    为什么不用 dev server (3006):
      Vite dev server 首屏要并发加载几十个 ES module，免费隧道带宽扛不住，
      手机端表现为永久白屏（#app 内容为 0，无 console 输出）。
      实测 2026-10-12：localhost.run 与 serveo.net 均失败。

    改用生产构建产物 (dist/):
      打包后首屏仅数个文件，1MB 的 vendor chunk 约 30s 传完，能完整加载。
      代价是无热更新，改代码后需重新运行本脚本。

    前置条件:
      - 后端已启动 (waitress，端口读 scripts/ports.json)
      - Windows OpenSSH 客户端可用 (ssh -V)

.EXAMPLE
    powershell -File scripts/start-mobile.ps1
    powershell -File scripts/start-mobile.ps1 -SkipBuild
    powershell -File scripts/start-mobile.ps1 -TunnelHost serveo.net
#>
[CmdletBinding()]
param(
    # 跳过构建，复用现有 dist/。改过代码则不要用。
    [switch]$SkipBuild,

    # 隧道服务。localhost.run 对大文件容错更好；serveo.net 有警告页且易断大文件。
    [ValidateSet('localhost.run', 'serveo.net')]
    [string]$TunnelHost = 'localhost.run',

    # SSH 私钥，仅 serveo.net 用（去掉广告警告页）。localhost.run 走 nokey@。
    [string]$TunnelKey = "$env:USERPROFILE\.ssh\serveo_key",

    [int]$PreviewPort = 4173,

    # 0 = 从 scripts/ports.json 读取
    [int]$BackendPort = 0
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if ($BackendPort -eq 0) {
    # [FIX 2026-10-12] 必须显式 UTF-8 读：ports.json 无 BOM，
    #   Get-Content 在 PowerShell 5.1 下按 ANSI 解码，中文注释变乱码导致
    #   ConvertFrom-Json 直接报 "Invalid object passed in"。
    $portsPath = Join-Path $RepoRoot 'scripts/ports.json'
    $portsJson = [System.IO.File]::ReadAllText($portsPath, [System.Text.UTF8Encoding]::new($false))
    $ports = $portsJson | ConvertFrom-Json
    $BackendPort = [int]$ports.backend
}

$runtimeDir = Join-Path $RepoRoot '.runtime'
New-Item -ItemType Directory -Force $runtimeDir | Out-Null

Write-Host ''
Write-Host '=== 手机访问 · 生产预览隧道 ===' -ForegroundColor Cyan
Write-Host "仓库    : $RepoRoot"
Write-Host "后端端口: $BackendPort"
Write-Host "预览端口: $PreviewPort"
Write-Host "隧道服务: $TunnelHost"
Write-Host ''

# --- 1. 后端存活检查（不通则隧道只会返回 502，白排查）---
$backendAlive = $false
try {
    $null = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/api/v1/auth/dev-login?username=admin" `
                              -UseBasicParsing -TimeoutSec 5
    $backendAlive = $true
} catch {
    # 401/403 说明后端在跑只是没鉴权，同样算存活
    if ($_.Exception.Response) { $backendAlive = $true }
}
if (-not $backendAlive) {
    Write-Warning "后端 $BackendPort 无响应，隧道会返回 502。"
    Write-Warning '请先启动后端 (npm run dev:python) 再运行本脚本。'
    $ans = Read-Host '仍要继续？(y/N)'
    if ($ans -ne 'y') { exit 1 }
}

# --- 2. 构建 ---
if ($SkipBuild) {
    if (-not (Test-Path (Join-Path $RepoRoot 'dist/index.html'))) {
        throw 'dist/ 不存在，无法跳过构建。去掉 -SkipBuild 重试。'
    }
    Write-Host '[1/2] 复用现有 dist/ ...' -ForegroundColor Yellow
} else {
    Write-Host '[1/2] 构建生产产物 (约 40s) ...' -ForegroundColor Yellow
    & npm run build:raw
    if ($LASTEXITCODE -ne 0) { throw "构建失败，exit=$LASTEXITCODE" }
}

# --- 3. 启动 preview ---
Write-Host "[2/2] 启动 preview: http://127.0.0.1:$PreviewPort ..." -ForegroundColor Yellow
$env:VITE_PREVIEW_PORT = "$PreviewPort"

# stdout/stderr 必须分文件，同一文件 Start-Process 会报错
$previewOut = Join-Path $runtimeDir 'mobile-preview.out.log'
$previewErr = Join-Path $runtimeDir 'mobile-preview.err.log'

$previewProc = Start-Process -FilePath 'npm.cmd' `
                              -ArgumentList 'run', 'preview' `
                              -WorkingDirectory $RepoRoot `
                              -RedirectStandardOutput $previewOut `
                              -RedirectStandardError $previewErr `
                              -PassThru -WindowStyle Hidden

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if ($previewProc.HasExited) {
        $err = Get-Content $previewErr -Raw -ErrorAction SilentlyContinue
        Stop-Process -Id $previewProc.Id -Force -ErrorAction SilentlyContinue
        throw "preview 进程已退出。stderr: $err"
    }
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$PreviewPort/" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
}
if (-not $ready) {
    Stop-Process -Id $previewProc.Id -Force -ErrorAction SilentlyContinue
    throw "preview 未在 30s 内就绪。日志: $previewErr"
}
Write-Host "preview 就绪 (PID $($previewProc.Id))" -ForegroundColor Green

# --- 4. 启动隧道 ---
$sshArgs = @(
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'ServerAliveInterval=30',
    '-o', 'ServerAliveCountMax=3'
)
if ($TunnelHost -eq 'serveo.net') {
    if (Test-Path $TunnelKey) {
        $sshArgs += @('-i', $TunnelKey)
    } else {
        Write-Warning "未找到私钥 $TunnelKey，serveo 会显示警告页（需手动点一下）。"
    }
    $sshTarget = 'serveo.net'
} else {
    # localhost.run 无 key 时必须走 nokey@，否则会要求注册
    $sshTarget = 'nokey@localhost.run'
}
$sshArgs += @('-R', "80:localhost:$PreviewPort", $sshTarget)

$tunnelOut = Join-Path $runtimeDir 'mobile-tunnel.out.log'
$tunnelErr = Join-Path $runtimeDir 'mobile-tunnel.err.log'
Remove-Item $tunnelOut, $tunnelErr -ErrorAction SilentlyContinue

Write-Host "启动隧道 ($sshTarget) ..." -ForegroundColor Yellow
$tunnelProc = Start-Process -FilePath 'ssh.exe' `
                              -ArgumentList $sshArgs `
                              -WorkingDirectory $RepoRoot `
                              -RedirectStandardOutput $tunnelOut `
                              -RedirectStandardError $tunnelErr `
                              -PassThru -WindowStyle Hidden

# --- 5. 从 ssh 输出解析公网地址 ---
# localhost.run: "e18f2ecd843336.lhr.life tunneled with tls termination, https://e18f2ecd843336.lhr.life"
# serveo.net   : "Forwarding HTTP traffic from https://xxx-yyy-yyy.serveousercontent.com"
# 注意 localhost.run 的欢迎横幅里也有其他 https:// 链接（admin.localhost.run 等），
# 所以正则必须锚定隧道域名，不能只匹配 https://\S+
$urlPattern = 'https://[A-Za-z0-9.-]+\.(?:lhr\.life|serveousercontent\.com)'

Write-Host '等待隧道分配地址 ...' -ForegroundColor Yellow
$publicUrl = $null
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 2
    if ($tunnelProc.HasExited) {
        $e = Get-Content $tunnelErr -Raw -ErrorAction SilentlyContinue
        Stop-Process -Id $previewProc.Id -Force -ErrorAction SilentlyContinue
        throw "ssh 进程已退出 (exit=$($tunnelProc.ExitCode))。stderr: $e"
    }
    $log = Get-Content $tunnelOut -Raw -ErrorAction SilentlyContinue
    if ($log) {
        $m = [regex]::Match($log, $urlPattern)
        if ($m.Success) { $publicUrl = $m.Value; break }
    }
}

if (-not $publicUrl) {
    Stop-Process -Id $previewProc.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $tunnelProc.Id -Force -ErrorAction SilentlyContinue
    throw "60s 内未解析到公网地址。日志: $tunnelOut"
}

# --- 6. 输出结果 ---
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 |
          Where-Object { $_.IPAddress -like '10.*' -or $_.IPAddress -like '192.168.*' } |
          Select-Object -First 1 -ExpandProperty IPAddress)

Write-Host ''
Write-Host '============================================' -ForegroundColor Cyan
Write-Host ' 手机访问地址 (公网，手机用流量可直接打开)' -ForegroundColor Green
Write-Host ''
Write-Host "   $publicUrl" -ForegroundColor White
Write-Host ''
Write-Host " 本机       : http://127.0.0.1:$PreviewPort"
if ($lanIp) { Write-Host " 局域网     : http://${lanIp}:$PreviewPort" }
Write-Host '============================================' -ForegroundColor Cyan
Write-Host ''
Write-Host ' 首次加载约需 60 秒(隧道带宽限制)，请勿提前刷新。' -ForegroundColor Yellow
Write-Host ' 生产构建，无热更新：改代码后需重跑本脚本。' -ForegroundColor Yellow
Write-Host ' 这是公网地址，拿到链接的人都能访问，调试完请 Ctrl+C。' -ForegroundColor Red
Write-Host ''
Write-Host " preview PID=$($previewProc.Id)   tunnel PID=$($tunnelProc.Id)" -ForegroundColor DarkGray
Write-Host " 日志: $tunnelOut" -ForegroundColor DarkGray
Write-Host ''

# --- 7. 常驻，Ctrl+C 清理 ---
try {
    while (-not $tunnelProc.HasExited) { Start-Sleep -Seconds 3 }
    Write-Warning "隧道进程已退出 (exit=$($tunnelProc.ExitCode))"
} finally {
    Write-Host '正在清理 ...'
    Stop-Process -Id $previewProc.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $tunnelProc.Id -Force -ErrorAction SilentlyContinue
}