# V007.86b_PERMANENT_FIX.ps1 - 永久修复 yonaa_alert_monitor 计划任务 (V007.86 升级版)
# 适用: V007.71 worktree 迁移遗留 + V007.83 + V007.86 + V007.86b 多次尝试失败
# 用法: 右键 -> 以管理员身份运行 (UAC 弹窗点 "是")
# 期望: 5 分钟内 计划任务跑成功 (上次结果 0 或 0x0)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "V007.86b 永久修复 yonaa_alert_monitor"

# ====== 路径配置 ======
$oldPath = "D:\filework\worktrees/release-prep"
$newPath = "D:\filework\worktrees\release-prep"
$xmlPath = "$newPath\tools\yonaa_alert_monitor.xml"
$tempXml = "$newPath\tools\_yonaa_alert_monitor_v0760.xml"

Write-Host "============================================="
Write-Host "V007.86b 永久修复 yonaa_alert_monitor"
Write-Host "============================================="
Write-Host ""
Write-Host "老路径: $oldPath" -ForegroundColor Yellow
Write-Host "新路径: $newPath" -ForegroundColor Green
Write-Host "XML:    $xmlPath" -ForegroundColor Green
Write-Host ""

# ====== Step 1: Stop daemon (V007.86 启动的) ======
Write-Host "=== Step 1: Stop daemon (V007.86 启动的 python) ===" -ForegroundColor Cyan
$daemon = Get-Process | Where-Object {
    $_.ProcessName -eq "python" -and
    $_.CommandLine -match "alert_monitor_v0760.*--daemon"
}
if ($daemon) {
    Write-Host "  Found daemon PID: $($daemon.Id)"
    Stop-Process -Id $daemon.Id -Force
    Start-Sleep 2
    Write-Host "  [OK] Daemon stopped" -ForegroundColor Green
} else {
    Write-Host "  [INFO] No daemon running" -ForegroundColor Yellow
}
Write-Host ""

# ====== Step 2: Delete old task (if any) ======
Write-Host "=== Step 2: Delete old task (if exists) ===" -ForegroundColor Cyan
$deleteOutput = schtasks /Delete /TN "\yonaa_alert_monitor" /F 2>&1
Write-Host "  schtasks /Delete: $deleteOutput"
Write-Host ""

# ====== Step 3: Read + Fix XML (UTF-16 LE) ======
Write-Host "=== Step 3: Read + Fix XML (UTF-16 LE) ===" -ForegroundColor Cyan
if (-not (Test-Path $xmlPath)) {
    Write-Host "  [FAIL] XML not found: $xmlPath" -ForegroundColor Red
    pause
    exit 1
}

$bytes = [System.IO.File]::ReadAllBytes($xmlPath)
Write-Host "  Original size: $($bytes.Length) bytes"

# Check BOM: UTF-16 LE = FF FE (PowerShell/GBK may show as c3bf, but check first 2 bytes)
if ($bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
    Write-Host "  [OK] UTF-16 LE BOM (FF FE) confirmed"
} else {
    Write-Host "  [WARN] First 2 bytes: $($bytes[0].ToString('X2')) $($bytes[1].ToString('X2'))"
    Write-Host "         Expected FF FE for UTF-16 LE"
    Write-Host "         Will try to decode anyway..."
}

# Decode UTF-16 LE (Encoding.Unicode = UTF-16 LE)
$enc = [System.Text.Encoding]::Unicode
$xmlText = $enc.GetString($bytes)

# Count old path occurrences using simple substring check
$oldPathCount = ([regex]::Matches($xmlText, [regex]::Escape($oldPath))).Count
Write-Host "  Old path '$oldPath' found: $oldPathCount times"

if ($oldPathCount -eq 0) {
    Write-Host "  [WARN] No old path found in XML!" -ForegroundColor Yellow
    Write-Host "         Maybe XML already has new path?" -ForegroundColor Yellow
    Write-Host "         Skipping path replacement..." -ForegroundColor Yellow
} else {
    # Replace
    $xmlText = $xmlText.Replace($oldPath, $newPath)
    Write-Host "  Replaced $oldPathCount occurrence(s)" -ForegroundColor Green
}

# Re-encode + Write (WriteAllBytes, NOT Out-File, to avoid CRLF!)
$fixedBytes = $enc.GetBytes($xmlText)
[System.IO.File]::WriteAllBytes($tempXml, $fixedBytes)
Write-Host "  Fixed XML saved to: $tempXml ($($fixedBytes.Length) bytes)" -ForegroundColor Green
Write-Host ""

# ====== Step 4: Create new task ======
Write-Host "=== Step 4: Create new task from fixed XML ===" -ForegroundColor Cyan
$createOutput = schtasks /Create /TN "\yonaa_alert_monitor" /XML $tempXml /F 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] Task created: $createOutput" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] Task create failed: $createOutput" -ForegroundColor Red
    pause
    exit 1
}
Write-Host ""

# ====== Step 5: Verify task ======
Write-Host "=== Step 5: Verify new task ===" -ForegroundColor Cyan
$taskInfo = schtasks /Query /TN "\yonaa_alert_monitor" /V /FO LIST 2>&1
$taskInfo | Select-String "要运行的任务|起始于|计划任务状态|下次运行时间" | ForEach-Object { Write-Host "  $_" }
Write-Host ""

# ====== Step 6: Cleanup temp file ======
Write-Host "=== Step 6: Cleanup temp file ===" -ForegroundColor Cyan
Remove-Item $tempXml -Force -ErrorAction SilentlyContinue
Write-Host "  [OK] Cleanup done"
Write-Host ""

# ====== Step 7: Run task once immediately (don't wait 5 min) ======
Write-Host "=== Step 7: Run task once immediately (no need to wait 5 min) ===" -ForegroundColor Cyan
$runOutput = schtasks /Run /TN "\yonaa_alert_monitor" 2>&1
Write-Host "  schtasks /Run: $runOutput"
Write-Host "  Waiting 15 seconds for task to start and report..."
Start-Sleep 15

# Re-verify after run
Write-Host ""
Write-Host "=== Task status after run ===" -ForegroundColor Cyan
schtasks /Query /TN "\yonaa_alert_monitor" /V /FO LIST 2>&1 | Select-String "上次运行时间|上次结果|状态" | ForEach-Object { Write-Host "  $_" }
Write-Host ""

# ====== Summary ======
Write-Host "=============================================" -ForegroundColor Green
Write-Host "修复完成!" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host ""
Write-Host "下一步:" -ForegroundColor Cyan
Write-Host "  1. 验证 '上次结果' 是不是 0 或 0x0 (成功)" -ForegroundColor White
Write-Host "  2. 看 log 确认 监控跑通:" -ForegroundColor White
Write-Host "     $newPath\tools\alert_monitor_v0760.log" -ForegroundColor White
Write-Host ""
pause
