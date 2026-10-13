#Requires -Version 5.1
<#
.SYNOPSIS
    启动手机可访问的生产预览 + cloudflared 公网隧道。

.NOTES
    本文件必须存为 UTF-8 with BOM。Windows PowerShell 5.1 用 -File 执行时
    按 ANSI 解码无 BOM 的 UTF-8，中文变乱码并导致语法解析失败
    (实测报 Missing expression after ',' 与 string is missing the terminator)。
    PowerShell 7+ 无此问题，但本仓库默认走 5.1，故必须带 BOM。

.DESCRIPTION
    为什么用生产构建而不是 dev server:
      Vite dev server 首屏要并发加载几十个 ES module，免费隧道带宽扛不住，
      手机端表现为永久白屏（#app 内容为空且无 console 输出）。
      打包后首屏仅数个文件，能完整加载。代价是无热更新。

    为什么用 cloudflared 而不是 SSH 隧道:
      2026-10-12 实测 localhost.run 与 serveo.net 均不可用——
      localhost.run 首屏 6.65MB 约需 40 秒且经常传不完；
      serveo.net 存在 HTTP/2 协议错误。
      同期实测 cloudflared 传 5.09MB 仅需 3.33 秒（1.53 MB/s），
      全量首屏约 9.3 秒，差距约 4 倍。

    隧道地址每次重启都会变:
      cloudflared quick tunnel 不绑定固定域名，断开后旧域名不再解析。
      因此地址只存在于本次运行的日志中，不要写死在任何地方。

.EXAMPLE
    powershell -File scripts/start-mobile.ps1
    powershell -File scripts/start-mobile.ps1 -SkipBuild
#>
[CmdletBinding()]
param(
    # 跳过构建，复用现有 dist/。改过代码则不要用。
    [switch]$SkipBuild,

    [int]$PreviewPort = 4173,

    # 0 = 从 scripts/ports.json 读取
    [int]$BackendPort = 0,

    # cloudflared 可执行文件。不存在时脚本会给出下载指引。
    [string]$CloudflaredPath = ''
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

if ($BackendPort -eq 0) {
    # 必须显式 UTF-8 读：ports.json 无 BOM，
    # Get-Content 在 PowerShell 5.1 下按 ANSI 解码，中文注释变乱码导致
    # ConvertFrom-Json 直接报 "Invalid object passed in"。
    $portsPath = Join-Path $RepoRoot 'scripts/ports.json'
    $portsJson = [System.IO.File]::ReadAllText($portsPath, [System.Text.UTF8Encoding]::new($false))
    $ports = $portsJson | ConvertFrom-Json
    $BackendPort = [int]$ports.backend
}

$runtimeDir = Join-Path $RepoRoot '.runtime'
New-Item -ItemType Directory -Force $runtimeDir | Out-Null

if (-not $CloudflaredPath) {
    $CloudflaredPath = Join-Path $RepoRoot '.tools/cloudflared.exe'
}

Write-Host ''
Write-Host '=== 手机访问 · cloudflared 隧道 ===' -ForegroundColor Cyan
Write-Host "仓库      : $RepoRoot"
Write-Host "后端端口  : $BackendPort"
Write-Host "预览端口  : $PreviewPort"
Write-Host ''

# --- 1. 前置检查 ---
if (-not (Test-Path $CloudflaredPath)) {
    Write-Host "未找到 cloudflared: $CloudflaredPath" -ForegroundColor Red
    Write-Host ''
    Write-Host '请先下载到 .tools/ 目录（该目录已在 .gitignore 中）：' -ForegroundColor Yellow
    Write-Host '  New-Item -ItemType Directory -Force .tools' -ForegroundColor Gray
    Write-Host '  Invoke-WebRequest -Uri https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe -OutFile .tools/cloudflared.exe' -ForegroundColor Gray
    Write-Host ''
    Write-Host '或改用 -CloudflaredPath 指定本机已安装的 cloudflared。' -ForegroundColor Yellow
    exit 1
}

# 后端存活检查：不通则隧道只会返回 502，白排查
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
    Write-Warning "请先启动后端再运行本脚本。日志可查 .runtime/backend.err.log"
}

# --- 2. 构建 ---
if ($SkipBuild) {
    if (-not (Test-Path (Join-Path $RepoRoot 'dist/index.html'))) {
        throw 'dist/ 不存在，无法跳过构建。去掉 -SkipBuild 重试。'
    }
    Write-Host '[1/3] 复用现有 dist/ ...' -ForegroundColor Yellow
} else {
    Write-Host '[1/3] 构建生产产物 (约 40s) ...' -ForegroundColor Yellow
    & npm run build:raw
    if ($LASTEXITCODE -ne 0) { throw "构建失败，exit=$LASTEXITCODE" }
}

# --- 3. 启动 preview ---
Write-Host "[2/3] 启动 preview: http://127.0.0.1:$PreviewPort ..." -ForegroundColor Yellow
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

# --- 4. 启动 cloudflared 隧道 ---
$tunnelOut = Join-Path $runtimeDir 'mobile-tunnel.out.log'
$tunnelErr = Join-Path $runtimeDir 'mobile-tunnel.err.log'
Remove-Item $tunnelOut, $tunnelErr -ErrorAction SilentlyContinue

Write-Host '[3/3] 启动 cloudflared 隧道 ...' -ForegroundColor Yellow
$tunnelProc = Start-Process -FilePath $CloudflaredPath `
                              -ArgumentList 'tunnel', '--url', "http://localhost:$PreviewPort", '--no-autoupdate' `
                              -WorkingDirectory $RepoRoot `
                              -RedirectStandardOutput $tunnelOut `
                              -RedirectStandardError $tunnelErr `
                              -PassThru -WindowStyle Hidden

# quick tunnel 的分配地址打在 stderr，形如
#   https://carpet-accounting-critics-citations.trycloudflare.com
$urlPattern = 'https://[a-z0-9-]+\.trycloudflare\.com'

Write-Host '等待隧道分配地址 ...' -ForegroundColor Yellow
$publicUrl = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    if ($tunnelProc.HasExited) {
        $e = Get-Content $tunnelErr -Raw -ErrorAction SilentlyContinue
        Stop-Process -Id $previewProc.Id -Force -ErrorAction SilentlyContinue
        throw "cloudflared 已退出 (exit=$($tunnelProc.ExitCode))。stderr: $e"
    }
    $log = Get-Content $tunnelErr -Raw -ErrorAction SilentlyContinue
    if ($log) {
        $m = [regex]::Match($log, $urlPattern)
        if ($m.Success) { $publicUrl = $m.Value; break }
    }
}

if (-not $publicUrl) {
    Stop-Process -Id $previewProc.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $tunnelProc.Id -Force -ErrorAction SilentlyContinue
    throw "60s 内未解析到公网地址。日志: $tunnelErr"
}

# --- 5. 连通性自检---
# 不自检的话，隧道通了但 Vite Host 白名单没放行时，用户只会看到 403。
# 注意: 本机 DNS 可能解析不了 trycloudflare.com(公司网络拦截)，
# 此时手机用流量不受影响。所以解析失败不等于隧道有问题，
# 需回退到「向 8.8.8.8 查 IP + Host 头」再测一次。
$probeStatus = '未通过'
$probeHint = '请在浏览器中打开上面的地址确认'
try {
    # 超时给短一些：本机 DNS 解析失败时通常几秒就返回错误，
    # 不需要 30s。留出余量给后面的 IP 回退探测。
    $resp = Invoke-WebRequest -Uri $publicUrl -UseBasicParsing -TimeoutSec 10
    if ($resp.StatusCode -eq 200) { $probeStatus = '通过'; $probeHint = '' }
} catch {
    # 疑似本机 DNS 问题, 换公共 DNS 取 IPv4 后再试。
    # 必须筛 IPv4: 8.8.8.8 通常把 AAAA 记录排在前面，
    # 而本机 IPv6 不可达，取到 v6 地址会探测失败并误判为隧道不通。
    $host_ = ([uri]$publicUrl).Host
    try {
        $ip4 = (Resolve-DnsName -Name $host_ -Server 8.8.8.8 -Type A -ErrorAction Stop |
                Where-Object { $_.IPAddress -and $_.IPAddress -notmatch ':' } |
                Select-Object -First 1).IPAddress
        if ($ip4) {
            $r2 = Invoke-WebRequest -Uri "https://$ip4/" -Headers @{ Host = $host_ } `
                                     -UseBasicParsing -TimeoutSec 20
            if ($r2.StatusCode -eq 200) {
                $probeStatus = '通过(本机 DNS 被拦截)'
                $probeHint = '本机解析不了该域名属正常，手机用流量可正常访问'
            }
        }
    } catch { }
}

# --- 6. 输出结果 ---
Write-Host ''
Write-Host '============================================' -ForegroundColor Cyan
Write-Host ' 手机访问地址 (公网，手机用流量可直接打开)' -ForegroundColor Green
Write-Host ''
Write-Host "   $publicUrl" -ForegroundColor White
Write-Host ''
Write-Host " 本机: http://127.0.0.1:$PreviewPort"
Write-Host '============================================' -ForegroundColor Cyan
Write-Host ''
Write-Host " 连通性自检: $probeStatus" -ForegroundColor $(if ($probeStatus -eq '未通过') { 'Red' } else { 'Green' })
if ($probeHint) { Write-Host "   $probeHint" -ForegroundColor DarkGray }
Write-Host ''
Write-Host ' 需要先登录账号，隧道不会自动登录。' -ForegroundColor Yellow
Write-Host ' 首次加载需 30-60 秒(隧道带宽限制)，请勿提前刷新。' -ForegroundColor Yellow
Write-Host ' 生产构建，无热更新：改代码后需重跑本脚本。' -ForegroundColor Yellow
Write-Host ' 地址每次重启都会变，不要保存到书签。' -ForegroundColor Yellow
Write-Host ' 这是公网地址，拿到链接的人都能访问，调试完请 Ctrl+C。' -ForegroundColor Red
Write-Host ''
Write-Host " preview PID=$($previewProc.Id)   tunnel PID=$($tunnelProc.Id)" -ForegroundColor DarkGray
Write-Host " 日志: $tunnelErr" -ForegroundColor DarkGray
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