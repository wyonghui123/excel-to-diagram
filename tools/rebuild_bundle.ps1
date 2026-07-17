# rebuild_bundle.ps1 - rebuild deploy_bundle/ (use Copy-Item, write to real Windows disk)
# Usage: powershell -File tools/rebuild_bundle.ps1
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$bundle = Join-Path $repoRoot "deploy_bundle"

Write-Host "Bundle: $bundle" -ForegroundColor Cyan

# clean
if (Test-Path $bundle) {
    Remove-Item $bundle -Recurse -Force
}
New-Item -ItemType Directory -Path $bundle -Force | Out-Null

# copy zip
$zipSrc = Get-ChildItem "$repoRoot/deploy-v*.zip" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($zipSrc) {
    Copy-Item $zipSrc.FullName "$bundle/$($zipSrc.Name)" -Force
    Write-Host "  + $($zipSrc.Name) ($($zipSrc.Length) bytes)" -ForegroundColor Green
} else {
    Write-Host "  ! deploy-v*.zip NOT FOUND" -ForegroundColor Red
}

# copy deploy tools
$tools = @("deploy.sh", "precheck.sh", "smoke_test.sh", "rollback.sh", "diagnose.sh", "status.sh", "restart.sh", "watch.sh", "deploy_history.sh", "reset_admin_password.sh", "reset_deploy_test_user.sh", "unified_server.py")
foreach ($f in $tools) {
    $src = Join-Path "$repoRoot/tools" $f
    if (Test-Path $src) {
        Copy-Item $src "$bundle/$f" -Force
        $size = (Get-Item $src).Length
        Write-Host "  + $f ($size bytes)" -ForegroundColor Green
    } else {
        Write-Host "  ! $f NOT FOUND" -ForegroundColor Red
    }
}

# copy lib/
$libSrc = Join-Path "$repoRoot/tools/lib" "common.sh"
$libDst = Join-Path "$bundle" "lib"
New-Item -ItemType Directory -Path $libDst -Force | Out-Null
if (Test-Path $libSrc) {
    Copy-Item $libSrc "$libDst/common.sh" -Force
    Write-Host "  + lib/common.sh" -ForegroundColor Green
}

# [CHG 2026-07-04] copy lib/check_deploy_health.sh (一键 6 类 BUG 验证)
$checkHealthSrc = Join-Path "$repoRoot/tools/lib" "check_deploy_health.sh"
if (Test-Path $checkHealthSrc) {
    Copy-Item $checkHealthSrc "$libDst/check_deploy_health.sh" -Force
    Write-Host "  + lib/check_deploy_health.sh" -ForegroundColor Green
}

# copy tests/ (deployable test scripts)
$testsSrc = "$repoRoot/tests"
$testsDst = "$bundle/tests"
if (Test-Path $testsSrc) {
    New-Item -ItemType Directory -Path $testsDst -Force | Out-Null
    Get-ChildItem "$testsSrc/test_*.py" -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item $_.FullName "$testsDst/$($_.Name)" -Force
        Write-Host "  + tests/$($_.Name) ($($_.Length) bytes)" -ForegroundColor Green
    }
    Get-ChildItem "$testsSrc/test_*.sh" -ErrorAction SilentlyContinue | ForEach-Object {
        Copy-Item $_.FullName "$testsDst/$($_.Name)" -Force
        Write-Host "  + tests/$($_.Name) ($($_.Length) bytes)" -ForegroundColor Green
    }
} else {
    Write-Host "  ! tests/ NOT FOUND" -ForegroundColor Red
}

# README
$readme = @"
# deploy_bundle/

One-click deploy bundle. SFTP to /tmp/ on remote.

## 完整文档 (AI Agent 必读)
D:\filework\worktrees/release-prep\DEPLOY_INFRASTRUCTURE.md

## 上传
MobaXterm SFTP: drag deploy_bundle/ to /tmp/

## 部署
bash /tmp/deploy_bundle/deploy.sh --version v20260703_002 --port 5001

## 回滚
bash /tmp/deploy_bundle/rollback.sh --to <v> --port <p>

## 状态 / 重启
bash /tmp/deploy_bundle/status.sh
bash /tmp/deploy_bundle/restart.sh

## 监控
bash /tmp/deploy_bundle/watch.sh --loop 30
bash /tmp/deploy_bundle/watch.sh --auto-recover
bash /tmp/deploy_bundle/watch.sh --rollback-on-fail

## 历史
bash /tmp/deploy_bundle/deploy_history.sh
bash /tmp/deploy_bundle/deploy_history.sh --info v20260703_002
bash /tmp/deploy_bundle/deploy_history.sh --switch v20260630_003 --port 5000

## 测试 (远端)
/opt/miniconda3-py39/bin/python /tmp/deploy_bundle/tests/test_rollback_parallel.py
/opt/miniconda3-py39/bin/python /tmp/deploy_bundle/tests/test_frontend_dir.py
"@
Set-Content -Path "$bundle/README.txt" -Value $readme -Encoding UTF8
Write-Host "  + README.txt" -ForegroundColor Green

# stats
$totalSize = (Get-ChildItem $bundle -Recurse -File | Measure-Object -Property Length -Sum).Sum
$fileCount = (Get-ChildItem $bundle -Recurse -File).Count
Write-Host ""
Write-Host "Bundle size: $totalSize bytes ($([math]::Round($totalSize/1024/1024, 2)) MB)" -ForegroundColor Green
Write-Host "File count: $fileCount" -ForegroundColor Cyan
Write-Host ""
Write-Host "Full file list:" -ForegroundColor Yellow
Get-ChildItem $bundle -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($bundle.Length + 1)
    Write-Host "  $rel  ($($_.Length) bytes)" -ForegroundColor White
}

Write-Host ""
if ($fileCount -lt 9) {
    Write-Host "WARNING: file count $fileCount < 9" -ForegroundColor Red
    exit 1
}
Write-Host "Next: MobaXterm SFTP drag deploy_bundle/ to /tmp/" -ForegroundColor Yellow
