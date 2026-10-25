﻿﻿﻿#Requires -Version 5.1
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

# [FIX 2026-10-24] 先清理端口占用。
#   历史故障：旧 preview 仍占 4173 时，新进程静默失败，而探活打到旧进程上，
#   脚本误报"就绪"，实际服务的还是上一次构建 —— 本轮排查中就踩到过一次，
#   表现为"改完代码但页面行为没变"，白费一整轮构建与验证。
$busy = Get-NetTCPConnection -LocalPort $PreviewPort -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    foreach ($c in $busy) {
        Write-Host "  [清理] 端口 $PreviewPort 被 PID $($c.OwningProcess) 占用，先终止" -ForegroundColor Yellow
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    for ($i = 0; $i -lt 20; $i++) {
        Start-Sleep -Milliseconds 500
        if (-not (Get-NetTCPConnection -LocalPort $PreviewPort -State Listen -ErrorAction SilentlyContinue)) { break }
    }
    if (Get-NetTCPConnection -LocalPort $PreviewPort -State Listen -ErrorAction SilentlyContinue) {
        throw "端口 $PreviewPort 清理失败，仍有进程监听，请手工处理后重试。"
    }
}

$env:VITE_PREVIEW_PORT = "$PreviewPort"
# [FIX 2026-10-19] 必须显式把本次探活的后端端口注入 preview 进程。
#   历史: 进程环境里残留的 BACKEND_PORT (如被 setx 持久化的 3011) 会覆盖
#   vite.config.js 读 ports.json 的默认值 → /api 代理全部 500 (3011 无监听)。
#   此处注入与第 90 行探活端口一致的 $BackendPort, 消除对继承环境的依赖。
#   (与 service_manager.py SERVICES.frontend.env 的 BACKEND_PORT 注入同理)
$env:BACKEND_PORT = "$BackendPort"

# stdout/stderr 必须分文件，同一文件 Start-Process 会报错
# [FIX 2026-10-24] 日志名带本次运行时间戳。
#   历史问题：固定文件名会被上一轮 cloudflared/preview 进程占着，launch_detached
#   只能回退到带时间戳的新文件；但本脚本仍会去读旧的固定文件，于是把**上一次**
#   的隧道地址当成这次的地址打印出来（本轮实测连打三次同一个旧域名）。
#   让两边都用同一个带时间戳的名字，朗读路径与实际输出路径就一致了。
$runStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$previewOut = Join-Path $runtimeDir "mobile-preview.$runStamp.out.log"
$previewErr = Join-Path $runtimeDir "mobile-preview.$runStamp.err.log"

# [FIX 2026-10-24] 改用 launch_detached.ps1 拉起，而不是本进程内的 Start-Process。
#   原因：Trae 终端工具在 agent-tool-host.exe 的 job object 下派生进程，并等待
#   **整棵后代进程树** 退出才判定本次调用完成。Start-Process 出的子进程父级仍是
#   当前 powershell.exe，仍在同一个 job 内，于是 preview / cloudflared 这类长驻
#   进程会把终端调用一直拖住（实测单次最长 1353.8 分钟，累计滞留 9146 分钟）。
#   launch_detached.ps1 走 WMI Win32_Process.Create，父进程为 WmiPrvSE.exe
#   （系统服务），完全脱离 job，终端调用立即返回。
$launchDetached = Join-Path $RepoRoot 'scripts/launch_detached.ps1'

$previewCmd = 'npm.cmd run preview'
$previewProcId = & $launchDetached -CommandLine $previewCmd -WorkingDirectory $RepoRoot `
    -StdOut $previewOut -StdErr $previewErr -PassThruPid | Select-Object -Last 1

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 1
    if (-not (Get-Process -Id $previewProcId -ErrorAction SilentlyContinue)) {
        $err = Get-Content $previewErr -Raw -ErrorAction SilentlyContinue
        throw "preview 进程已退出。stderr: $err"
    }
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:$PreviewPort/" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
}
if (-not $ready) {
    Stop-Process -Id $previewProcId -Force -ErrorAction SilentlyContinue
    throw "preview 未在 30s 内就绪。日志: $previewErr"
}
Write-Host "preview 就绪 (PID $previewProcId)" -ForegroundColor Green

# [FIX 2026-10-24] 校验「服务的确实是本次构建」。
#   仅凭端口 200 无法区分新旧进程（见上一步注释）。dist/index.html 里引用的
#   入口 JS 文件名带内容哈希，逐轮构建都会变；若对外返回的 HTML 里找不到它，
#   就说明命中的是旧服务，必须直接失败，不能继续浪费一轮验证。
$distIndexPath = Join-Path $RepoRoot 'dist/index.html'
$distIndex = [System.IO.File]::ReadAllText($distIndexPath, [System.Text.UTF8Encoding]::new($false))
$servedHtml = (Invoke-WebRequest -Uri "http://127.0.0.1:$PreviewPort/" -UseBasicParsing -TimeoutSec 5).Content
if ($distIndex -match 'assets/(index-[A-Za-z0-9_-]+\.js)') {
    $entryAsset = $matches[1]
    if ($servedHtml -notmatch [regex]::Escape($entryAsset)) {
        throw "preview 返回的不是最新构建（缺少入口 $entryAsset）。请检查端口占用后重试。"
    }
    Write-Host "  [校验] 服务端已是本次构建 ($entryAsset)" -ForegroundColor DarkGray
}

# --- 4. 启动 cloudflared 隧道 ---
# [FIX 2026-10-24] 启动前清理本项目遗留的 cloudflared 进程。
#   为什么必须自动做：脚本现在脱离 job 运行，进程不会随终端调用结束而退出，
#   每次重跑都会多留一条隧道（实测 20 分钟内累积 4 条）。旧隧道指向同一个
#   localhost 端口，仍能访问、仍在占用免费隧道带宽，且地址已不再打印，
#   留在机器上只会造成「到底哪个链接才是当前环境」的混乱。
#   只清理 CommandLine 里带本项目 cloudflared 路径的进程，不碰其他项目/系统的隧道。
$staleTunnels = @(Get-CimInstance Win32_Process -Filter "Name='cloudflared.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*$CloudflaredPath*" -and $_.CommandLine -like '*--url*' })
if ($staleTunnels.Count -gt 0) {
    foreach ($p in $staleTunnels) {
        $tpid = [int]$p.ProcessId
        Write-Host "  [清理] 遗留隧道 PID $tpid，先终止" -ForegroundColor Yellow
        Stop-Process -Id $tpid -Force -ErrorAction SilentlyContinue
    }
    for ($i = 0; $i -lt 10; $i++) {
        Start-Sleep -Milliseconds 300
        $still = @(Get-Process -Id ($staleTunnels | ForEach-Object { [int]$_.ProcessId }) -ErrorAction SilentlyContinue)
        if ($still.Count -eq 0) { break }
    }
    $still = @(Get-Process -Id ($staleTunnels | ForEach-Object { [int]$_.ProcessId }) -ErrorAction SilentlyContinue)
    if ($still.Count -gt 0) {
        Write-Warning "有 $($still.Count) 个遗留隧道未能终止（PID: $($still.Id -join ', ')），继续启动新隧道。"
    }
}

# [FIX 2026-10-24] 同 preview：隧道日志也必须带本次运行时间戳。
#   否则上一轮 cloudflared 还占着固定名文件时，本次输出会被写到新文件，
#   而这里读的仍是旧文件 → 把上一次的域名当成这次的地址打印出去。
$tunnelOut = Join-Path $runtimeDir "mobile-tunnel.$runStamp.out.log"
$tunnelErr = Join-Path $runtimeDir "mobile-tunnel.$runStamp.err.log"

Write-Host '[3/3] 启动 cloudflared 隧道 ...' -ForegroundColor Yellow
# [FIX 2026-10-24] 同 preview：走脱离 job 的启动方式，避免隧道进程把终端调用拖住。
$tunnelCmd = '& ''' + $CloudflaredPath + ''' tunnel --url http://localhost:' + $PreviewPort + ' --no-autoupdate'
$tunnelProcId = & $launchDetached -CommandLine $tunnelCmd -WorkingDirectory $RepoRoot `
    -StdOut $tunnelOut -StdErr $tunnelErr -PassThruPid | Select-Object -Last 1

# quick tunnel 的分配地址打在 stderr，形如
#   https://carpet-accounting-critics-citations.trycloudflare.com
$urlPattern = 'https://[a-z0-9-]+\.trycloudflare\.com'

Write-Host '等待隧道分配地址 ...' -ForegroundColor Yellow
$publicUrl = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Seconds 2
    if (-not (Get-Process -Id $tunnelProcId -ErrorAction SilentlyContinue)) {
        $e = Get-Content $tunnelErr -Raw -ErrorAction SilentlyContinue
        Stop-Process -Id $previewProcId -Force -ErrorAction SilentlyContinue
        throw "cloudflared 已退出。stderr: $e"
    }
    $log = Get-Content $tunnelErr -Raw -ErrorAction SilentlyContinue
    if ($log) {
        $m = [regex]::Match($log, $urlPattern)
        if ($m.Success) { $publicUrl = $m.Value; break }
    }
}

if (-not $publicUrl) {
    Stop-Process -Id $previewProcId -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $tunnelProcId -Force -ErrorAction SilentlyContinue
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
Write-Host ' 这是公网地址，拿到链接的人都能访问，调试完请停掉隧道进程。' -ForegroundColor Red
Write-Host ''
Write-Host " preview PID=$previewProcId   tunnel PID=$tunnelProcId" -ForegroundColor DarkGray
Write-Host " 日志: $tunnelErr" -ForegroundColor DarkGray
Write-Host ''

# --- 7. 退出（不阻塞常驻）---
# [FIX 2026-10-24] 原来这里 while (-not $tunnelProc.HasExited) 常驻阻塞，
#   脚本要等隧道退出才返回。隧道现在是脱离 job 的独立进程，脚本无需再等；
#   常驻等待会把终端调用拖住（实测单次最长 1353.8 分钟）。
#   清理方式：按上面打印的 PID 手动 Stop-Process，或跑 scripts/stop-*.ps1。
Write-Host ' preview 与隧道已在后台运行，本脚本直接返回。' -ForegroundColor DarkGray
Write-Host ' 需要停止时按上面的 PID 执行 Stop-Process，或运行 scripts/service_manager.ps1。' -ForegroundColor DarkGray
Write-Host ''