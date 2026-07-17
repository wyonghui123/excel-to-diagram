# ============================================================
# Build deploy package - PowerShell version
# For worktrees/release-prep single-layer directory structure
# Usage: .\build-deploy-package.ps1 [-Version "20260630_001"]
# ============================================================

param(
    [string]$Version = "",
    [switch]$SkipFrontend,
    [switch]$SkipPythonDeps,
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Info($msg) { Write-Host "[i] $msg" -ForegroundColor Cyan }
function Write-Pass($msg) { Write-Host "[OK] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }
function Write-Fail($msg) { Write-Host "[X] $msg" -ForegroundColor Red }

# ============================================================
# Setup
# ============================================================
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Get-Item $ScriptDir).Parent.FullName
$BuildDir = Join-Path $ProjectRoot "build"
$Timestamp = Get-Date -Format "yyyyMMdd"

if (-not $Version) {
    $existing = Get-ChildItem "$ProjectRoot/deploy-v*.zip" -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match "\d{8}_\d{3}" } |
        ForEach-Object {
            if ($_.Name -match '(\d{8})_(\d{3})') {
                if ($Matches[1] -eq $Timestamp) { [int]$Matches[2] }
            }
        }
    $seq = if ($existing) { ($existing | Measure-Object -Maximum).Maximum + 1 } else { 1 }
    $Version = "${Timestamp}_$(($seq).ToString('000'))"
}

$PackageName = "deploy-v${Version}.zip"
$PackagePath = Join-Path $ProjectRoot $PackageName

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "       Build Deploy Package (PS)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Version:    v$Version"
Write-Host "Project:    $ProjectRoot"
Write-Host "Package:    $PackagePath"
Write-Host ""

if ($WhatIf) {
    Write-Warn "WhatIf mode - dry run only"
    return
}

# ============================================================
# Step 0: Clean old build
# ============================================================
Write-Info "Step 0: Clean old build..."
if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }
New-Item -ItemType Directory -Path $BuildDir | Out-Null

# ============================================================
# Step 1: Frontend (dist/)
# ============================================================
Write-Info "Step 1: Frontend..."
$FrontendSrc = $ProjectRoot
$FrontendDist = Join-Path $BuildDir "frontend_dist_files"
New-Item -ItemType Directory -Path $FrontendDist -Force | Out-Null

$DistPath = Join-Path $FrontendSrc "dist"
$SrcPath = Join-Path $FrontendSrc "src"

if (-not (Test-Path $DistPath) -or -not (Test-Path $SrcPath)) {
    Write-Warn "Frontend source not found (dist/ or src/), skipping"
    if (Test-Path $DistPath) {
        Copy-Item "$DistPath\*" $FrontendDist -Recurse -Force
        Write-Pass "Copied existing dist/"
    } else {
        Write-Warn "dist/ does not exist - frontend will be built on remote"
    }
} elseif ($SkipFrontend) {
    Write-Warn "Skip frontend build (SkipFrontend)"
    Copy-Item "$DistPath\*" $FrontendDist -Recurse -Force -ErrorAction SilentlyContinue
    Write-Pass "Copied existing dist/"
} else {
    Write-Info "Running npm install + npm run build..."
    Push-Location $FrontendSrc
    try {
        $npm = Get-Command npm -ErrorAction SilentlyContinue
        if ($npm) {
            npm install 2>&1 | Out-Null
            npm run build 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "npm run build failed, copying existing files"
                Copy-Item "$DistPath\*" $FrontendDist -Recurse -Force -ErrorAction SilentlyContinue
            } else {
                Copy-Item "$DistPath\*" $FrontendDist -Recurse -Force
                Write-Pass "Frontend build done"
            }
        } else {
            Write-Warn "npm not found, copying existing files"
            Copy-Item "$DistPath\*" $FrontendDist -Recurse -Force -ErrorAction SilentlyContinue
        }
    } finally {
        Pop-Location
    }
}

# Copy server.py (with proxy)
$ServerPy = Join-Path $FrontendSrc "server.py"
$FrontendDistRoot = Join-Path $BuildDir "frontend"
New-Item -ItemType Directory -Path $FrontendDistRoot -Force | Out-Null
if (Test-Path $ServerPy) {
    Copy-Item $ServerPy $FrontendDistRoot -Force
}

# ============================================================
# Step 2: Backend (meta/)
# ============================================================
Write-Info "Step 2: Backend code..."
$BackendSrc = Join-Path $ProjectRoot "meta"
$BackendDist = Join-Path $BuildDir "backend"
New-Item -ItemType Directory -Path $BackendDist -Force | Out-Null

if (-not (Test-Path $BackendSrc)) {
    Write-Fail "Backend source not found: $BackendSrc"
    exit 1
}

Get-ChildItem $BackendSrc -Recurse -File |
    Where-Object { $_.Extension -in @('.py', '.yaml', '.yml', '.json', '.md', '.txt') } |
    ForEach-Object {
        $rel = $_.FullName.Substring($BackendSrc.Length)
        $dest = Join-Path $BackendDist $rel
        New-Item -ItemType Directory -Path (Split-Path $dest -Parent) -Force | Out-Null
        Copy-Item $_.FullName $dest -Force
    }
Write-Pass "Backend code copied (meta/)"

# Root-level server files
$RootFiles = @('server.py', 'waitress_server.py')
foreach ($f in $RootFiles) {
    $src = Join-Path $ProjectRoot $f
    if (Test-Path $src) { Copy-Item $src $BackendDist -Force }
}

# ============================================================
# Step 3: Python dependencies (offline download)
# ============================================================
Write-Info "Step 3: Python dependencies..."
$depsDir = Join-Path $BuildDir "dependencies\python\packages"
New-Item -ItemType Directory -Path $depsDir -Force | Out-Null

$ReqTxt = Join-Path $BackendDist "requirements.txt"
if (-not (Test-Path $ReqTxt)) {
    Write-Warn "requirements.txt not found, skipping"
} elseif (-not $SkipPythonDeps) {
    $pip = Get-Command pip -ErrorAction SilentlyContinue
    if ($pip) {
        Write-Info "Downloading Python deps (manylinux2014_x86_64, py39)..."
        try {
            $out = & pip download -r $ReqTxt -d $depsDir `
                --platform manylinux2014_x86_64 `
                --python-version 39 `
                --only-binary :all: `
                --no-deps 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Warn "Binary download failed, trying source-only..."
                $null = & pip download -r $ReqTxt -d $depsDir --no-deps 2>&1
            }
        } catch {
            Write-Warn "pip download error: $($_.Exception.Message)"
        }
        $pkgCount = (Get-ChildItem $depsDir -File -ErrorAction SilentlyContinue).Count
        Write-Pass "Downloaded $pkgCount Python packages"
    } else {
        Write-Warn "pip not found, skipping"
    }
} else {
    Write-Warn "Skip Python deps (SkipPythonDeps)"
}

# ============================================================
# Step 4: Migrations
# ============================================================
Write-Info "Step 4: Migrations..."
$MigrationsSrc = Join-Path $ProjectRoot "migrations"
$MigrationsDist = Join-Path $BuildDir "migrations"
New-Item -ItemType Directory -Path $MigrationsDist -Force | Out-Null

if (Test-Path $MigrationsSrc) {
    Copy-Item "$MigrationsSrc\*" $MigrationsDist -Recurse -Force
    Write-Pass "Migrations copied"
} else {
    Write-Warn "Migrations dir not found, skipping"
}

# ============================================================
# Step 5: Scripts
# ============================================================
Write-Info "Step 5: Scripts..."
$ScriptsDist = Join-Path $BuildDir "scripts"
New-Item -ItemType Directory -Path $ScriptsDist -Force | Out-Null

$ScriptsSrc = Join-Path $ProjectRoot "scripts"
if (Test-Path $ScriptsSrc) {
    Get-ChildItem $ScriptsSrc -Filter "*.sh" | Copy-Item -Destination $ScriptsDist -Force
    Get-ChildItem $ScriptsSrc -Filter "*.ps1" | Copy-Item -Destination $ScriptsDist -Force
    Write-Pass "Scripts copied"
}

# ============================================================
# Step 6: Config
# ============================================================
Write-Info "Step 6: Config..."
$ConfigDist = Join-Path $BuildDir "config"
New-Item -ItemType Directory -Path $ConfigDist -Force | Out-Null

$ConfigSrc = Join-Path $ProjectRoot "config"
if (Test-Path $ConfigSrc) {
    Copy-Item "$ConfigSrc\*" $ConfigDist -Recurse -Force
    Write-Pass "Config copied"
}

# ============================================================
# Step 7: MANIFEST
# ============================================================
Write-Info "Step 7: MANIFEST..."

$gitDesc = git -C $ProjectRoot describe --tags --always --dirty 2>$null
$gitBranch = "release/pre-2026-06-29"
$commitCount = git -C $ProjectRoot rev-list --count HEAD 2>$null
$gitLogLines = git -C $ProjectRoot log --oneline -30 HEAD 2>$null

$MANIFEST = @"
# ============================================================
# MANIFEST - Deploy Package Manifest
# ============================================================
# Generated: $(Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz")
# Branch: $gitBranch
# HEAD:   $gitDesc
# Commits: $commitCount
#
# IMPORTANT: This package is for FRESH INIT deployment only.
# init_database.py --force will DROP the old database.
# For incremental upgrade, see docs/SOP-USER-DEPLOYMENT.md
# ============================================================

version: "v$Version"
released_at: "$(Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz")"
built_by: "build-deploy-package.ps1"
build_host: "$env:COMPUTERNAME"

git:
  branch: "$gitBranch"
  head: "$gitDesc"
  commits_count: "$commitCount"

deployment_type: "fresh_init"

changes:
$($gitLogLines | ForEach-Object { "  - ""$_""" })

requirements:
  python: ">=3.9,<3.14"
  python_tested: "3.9.25"
  disk_space: "2GB"

dependencies:
  python:
    note: "Run 'pip install -r meta/requirements.txt' on remote"

services:
  frontend:
    port: 8081
  backend:
    port: 5001

init_steps:
  1: "cd /opt/app/current/meta && python scripts/init_database.py --force"
  2: "cd /opt/app/current/meta && python scripts/init_and_seed.py --force"
  3: "cd /opt/app/current/meta && python scripts/init_auth.py"
  4: "cd /opt/app/current/meta && python scripts/init_role_permissions.py"
  5: "cd /opt/app/current/meta && python scripts/init_menu_permissions.py"
  6: "cd /opt/app/current/meta && python scripts/init_task_seed.py"
  7: "cd /opt/app/current/meta && python scripts/preload_hot_roles.py"
  8: "Start services (see docs/SOP-USER-DEPLOYMENT.md S12.7)"
"@

$MANIFESTPath = Join-Path $BuildDir "MANIFEST"
$MANIFEST | Out-File -FilePath $MANIFESTPath -Encoding UTF8
Write-Pass "MANIFEST created"

# ============================================================
# Step 8: Package (.zip)
# ============================================================
Write-Info "Step 8: Packaging..."
if (Test-Path $PackagePath) {
    Remove-Item $PackagePath -Force
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$tmpZip = Join-Path $env:TEMP "deploy-v${Version}.zip"
if (Test-Path $tmpZip) { Remove-Item $tmpZip -Force }

[System.IO.Compression.ZipFile]::CreateFromDirectory($BuildDir, $tmpZip) | Out-Null
Move-Item $tmpZip $PackagePath -Force

$size = "{0:N2} MB" -f ((Get-Item $PackagePath).Length / 1MB)
Write-Pass "Package created: $PackageName ($size)"

# ============================================================
# Step 9: README
# ============================================================
Write-Info "Step 9: README..."
$README = @"
================================================================================
                 Excel to Diagram - Deploy Package
                 Version: v$Version
                 Branch: $gitBranch
                 Date: $(Get-Date -Format "yyyy-MM-dd")
================================================================================

SCENARIO: Fresh init deployment (NOT incremental upgrade)
WARNING:  init_database.py --force will DROP the old database!

--- STEP 1: Unpack ---
cd /opt/app
mkdir -p deployments/v${Version}
unzip ${PackageName} -d deployments/v${Version}
cd deployments/v${Version}
ln -sfn `$(pwd) /opt/app/current

--- STEP 2: Init DB (6 steps) ---
cd /opt/app/current/meta

# 1. Init DB schema (DROP old, CREATE new)
python scripts/init_database.py --force

# 2. Seed data (4 domains, 8 sub-domains, 16 service modules)
python scripts/init_and_seed.py --force

# 3-7. Init auth + permissions + menus
python scripts/init_auth.py
python scripts/init_role_permissions.py
python scripts/init_menu_permissions.py
python scripts/init_task_seed.py
python scripts/preload_hot_roles.py

--- STEP 3: Start services ---
# Generate JWT_SECRET_KEY first:
JWT_SECRET_KEY=`$(python -c "import secrets; print(secrets.token_urlsafe(48))")

# Frontend (8081)
cd /opt/app/current
PORT=8081 FLASK_DEBUG=false FLASK_ENV=production \
  JWT_SECRET_KEY="`$JWT_SECRET_KEY" \
  CORS_ALLOWED_ORIGINS="http://172.20.59.7:8081,http://172.20.59.7:5001" \
  ADMIN_PASSWORD="ChangeMe@2026!" \
  nohup python server.py > /opt/app/shared/logs/deploy.log 2>&1 &

# Backend (5001)
cd /opt/app/current/meta
PORT=5001 FLASK_DEBUG=false FLASK_ENV=production \
  JWT_SECRET_KEY="`$JWT_SECRET_KEY" \
  CORS_ALLOWED_ORIGINS="http://172.20.59.7:8081,http://172.20.59.7:5001" \
  ADMIN_PASSWORD="ChangeMe@2026!" \
  nohup python server.py > /opt/app/shared/logs/backend.log 2>&1 &

--- STEP 4: Verify ---
sleep 15
curl -s http://localhost:8081/health
curl -s http://localhost:5001/api/v1/health

See docs/SOP-USER-DEPLOYMENT.md S12.8 for full checklist.

--- STEP 5: Rollback ---
/opt/app/scripts/rollback-enhanced.sh -a -f

================================================================================
Full guide: docs/SOP-USER-DEPLOYMENT.md S12
MANIFEST: included in package
================================================================================
"@

$READMEPPath = Join-Path $ProjectRoot "DEPLOY-README-${Version}.txt"
$README | Out-File -FilePath $READMEPPath -Encoding UTF8
Write-Pass "README created: DEPLOY-README-${Version}.txt"

# ============================================================
# Done
# ============================================================
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "       Build Complete" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Package:  $PackageName"
Write-Host "README:   DEPLOY-README-${Version}.txt"
Write-Host "Size:     $size"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. scp $PackageName root@172.20.59.7:/opt/app/"
Write-Host "  2. Follow DEPLOY-README-${Version}.txt"
Write-Host ""
