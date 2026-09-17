# V007.86_PERMANENT_FIX.ps1 - 永久修复 yonaa_alert_monitor 计划任务
# 适用: V007.71 worktree 迁移遗留 + V007.83 + V007.86 多次尝试失败
# 用法: 右键 -> 以管理员身份运行 (UAC 弹窗点 "是")
# 期望: 5 分钟内 计划任务跑成功 (上次结果 0 或 0x0)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "V007.86 永久修复 yonaa_alert_monitor"

# ====== Step 0: 路径配置 ======
$oldPath = "D:\filework\worktrees/release-prep"
$newPath = "D:\filework\worktrees\release-prep"
$xmlPath = "$newPath\tools\yonaa_alert_monitor.xml"
$tempXml = "$newPath\tools\_yonaa_alert_monitor_v0760.xml"

Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "V007.86 永久修复 yonaa_alert_monitor" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
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

# ====== Step 3: Read + Fix XML ======
Write-Host "=== Step 3: Read + Fix XML ===" -ForegroundColor Cyan
if (-not (Test-Path $xmlPath)) {
    Write-Host "  [FAIL] XML not found: $xmlPath" -ForegroundColor Red
    pause
    exit 1
}

$bytes = [System.IO.File]::ReadAllBytes($xmlPath)
Write-Host "  Original size: $($bytes.Length) bytes"

# Check BOM (UTF-16 LE = FF FE)
if ($bytes[0] -ne 0xFF -or $bytes[1] -ne 0xFE) {
    Write-Host "  [FAIL] XML not UTF-16 LE (BOM: $($bytes[0].ToString('X2')) $($bytes[1].ToString('X2')))" -ForegroundColor Red
    pause
    exit 1
}
Write-Host "  [OK] UTF-16 LE BOM found"

# Decode + Replace
$enc = [System.Text.Encoding]::Unicode
$xmlText = $enc.GetString($bytes)

# Count old path occurrences
$oldPathCount = ([regex]::Matches($xmlText, [regex]::Escape($oldPath))).Count
Write-Host "  Old path '$oldPath' found: $oldPathCount times"

# Replace
$xmlText = $xmlText.Replace($oldPath, $newPath)

# Re-encode + Write (no CRLF!)
$fixedBytes = $enc.GetBytes($xmlText)
[System.IO.File]::WriteAllBytes($tempXml, $fixedBytes)
Write-Host "  Fixed XML saved to: $tempXml ($($fixedBytes.Length) bytes)" -ForegroundColor Green
Write-Host ""

# ====== Step 4: Create new task ======
Write-Host "=== Step 4: Create new task from fixed XML ===" -ForegroundColor Cyan
$createOutput = schtasks /Create /TN "\yonaa_alert_monitor" /XML $tempXml /F 2>&1
Write-Host "  schtasks /Create: $createOutput"
Write-Host ""

# ====== Step 5: Verify task ======
Write-Host "=== Step 5: Verify new task ===" -ForegroundColor Cyan
$taskInfo = schtasks /Query /TN "\yonaa_alert_monitor" /V /FO LIST 2>&1
$taskInfo | Select-String "要运行的任务|起始于|计划任务状态|下次运行时间" | ForEach-Object { Write-Host "  $_" }
Write-Host ""

# ====== Step 6: Cleanup ======
Write-Host "=== Step 6: Cleanup temp file ===" -ForegroundColor Cyan
Remove-Item $tempXml -Force -ErrorAction SilentlyContinue
Write-Host "  [OK] Cleanup done"
Write-Host ""

# ====== Step 7: Summary ======
Write-Host "=============================================" -ForegroundColor Green
Write-Host "修复完成!" -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host ""
Write-Host "下一步:" -ForegroundColor Cyan
Write-Host "  1. 等 5 分钟, 计划任务会自动跑一次" -ForegroundColor White
Write-Host "  2. 验证: schtasks /Query /TN '\yonaa_alert_monitor' /V /FO LIST" -ForegroundColor White
Write-Host "  3. 期望 '上次结果: 0' (成功) 或 '0x0'" -ForegroundColor White
Write-Host ""
Write-Host "如果还有问题, 看 log:" -ForegroundColor Cyan
Write-Host "  $newPath\tools\alert_monitor_v0760.log" -ForegroundColor White
Write-Host ""
pause
