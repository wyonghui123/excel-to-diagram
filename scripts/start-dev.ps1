# ArchWorkspace Dev Server - Windows One-Click Start
# Usage: .\scripts\start-dev.ps1 [-BackendOnly] [-Stop]

param(
    [switch]$BackendOnly,
    [switch]$Stop,
    [int]$FlaskPort = 5000,
    [int]$VitePort = 3004
)

$ROOT_DIR = Split-Path -Parent $PSScriptRoot

if ($Stop) {
    Write-Host "[STOP] Stopping all dev servers..." -ForegroundColor Yellow
    Get-Process -Name "python" -ErrorAction SilentlyContinue | ForEach-Object {
        $_.Kill()
        Write-Host "  Killed Python PID $($_.Id)" -ForegroundColor Green
    }
    Get-Process -Name "node" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.CommandLine -match "vite") {
            $_.Kill()
            Write-Host "  Killed Vite PID $($_.Id)" -ForegroundColor Green
        }
    }
    Write-Host "[DONE]" -ForegroundColor Green
    return
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "   ArchWorkspace Dev Environment" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

Set-Location $ROOT_DIR

# Clean up old processes
$oldFlask = Get-NetTCPConnection -LocalPort $FlaskPort -ErrorAction SilentlyContinue | Select-Object -First 1
if ($oldFlask) {
    $oldPid = $oldFlask.OwningProcess
    if ($oldPid -and $oldPid -gt 0) {
        $proc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Host "[CLEAN] Killing old Flask (PID $oldPid)..." -ForegroundColor Yellow
            $proc.Kill()
            Start-Sleep -Milliseconds 500
        }
    }
}

if (-not $BackendOnly) {
    $oldVite = Get-NetTCPConnection -LocalPort $VitePort -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($oldVite) {
        $oldPid = $oldVite.OwningProcess
        if ($oldPid -and $oldPid -gt 0) {
            $proc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
            if ($proc) {
                Write-Host "[CLEAN] Killing old Vite (PID $oldPid)..." -ForegroundColor Yellow
                $proc.Kill()
                Start-Sleep -Milliseconds 500
            }
        }
    }
}

# Set JWT Secret Key if not already set
if (-not $env:JWT_SECRET_KEY) {
    $jwtSecret = "dev-secret-key-archworkspace-$(Get-Random -Minimum 100000 -Maximum 999999)"
    [Environment]::SetEnvironmentVariable("JWT_SECRET_KEY", $jwtSecret, "Process")
    Write-Host "[CONFIG] JWT_SECRET_KEY set for this session" -ForegroundColor DarkGray
}

# Start Flask
Write-Host "[1/2] Starting Flask backend on port $FlaskPort..." -ForegroundColor Cyan
$flaskJob = Start-Job -ScriptBlock {
    param($dir, $jwtKey)
    Set-Location $dir
    $env:JWT_SECRET_KEY = $jwtKey
    python meta/server.py
} -ArgumentList $ROOT_DIR, $env:JWT_SECRET_KEY

Write-Host "      Backend starting in background..." -ForegroundColor DarkGray

$vitePid = 0
if (-not $BackendOnly) {
    Write-Host ""
    Write-Host "[2/2] Starting Vite frontend on port $VitePort..." -ForegroundColor Cyan
    Start-Sleep -Milliseconds 1000
    
    $viteJob = Start-Job -ScriptBlock {
        param($dir)
        Set-Location $dir
        npm run dev
    } -ArgumentList $ROOT_DIR
    
    Write-Host "      Frontend starting in background..." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  STARTED!" -ForegroundColor Green
Write-Host ""
Write-Host "  Frontend: http://localhost:$VitePort" -ForegroundColor Cyan
Write-Host "  Backend:  http://localhost:$FlaskPort" -ForegroundColor Cyan
Write-Host ""
Write-Host "  To stop: .\scripts\start-dev.ps1 -Stop" -ForegroundColor Gray
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Waiting for servers to be ready..." -ForegroundColor DarkGray

# Wait for Flask
$maxWait = 60
$elapsed = 0
while ($elapsed -lt $maxWait) {
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:$FlaskPort/health" -TimeoutSec 1 -ErrorAction Stop
        Write-Host "[OK] Backend ready! (${elapsed}s)" -ForegroundColor Green
        break
    } catch {
        Start-Sleep -Seconds 2
        $elapsed += 2
    }
}

if ($elapsed -ge $maxWait) {
    Write-Host "[WARN] Backend taking long time, but it's running" -ForegroundColor Yellow
}

# Wait for Vite
$elapsed = 0
while ($elapsed -lt 30) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:$VitePort" -TimeoutSec 1 -ErrorAction Stop
        Write-Host "[OK] Frontend ready! (${elapsed}s)" -ForegroundColor Green
        break
    } catch {
        Start-Sleep -Seconds 2
        $elapsed += 2
    }
}

Write-Host ""
Write-Host "Ready! Open http://localhost:$VitePort in browser" -ForegroundColor Green
