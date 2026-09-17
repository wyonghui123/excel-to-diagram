# Swap old task for v0762 (requires admin)
$xmlPath = 'D:\filework\worktrees/release-prep\tools\yonaa_alert_monitor_v0762.xml'

try {
    # Delete old (idempotent)
    Unregister-ScheduledTask -TaskName 'yonaa_alert_monitor' -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host '[OK] Old task removed (if existed)'

    # Register new
    $task = Register-ScheduledTask `
        -TaskName 'yonaa_alert_monitor' `
        -Xml (Get-Content $xmlPath -Raw) `
        -Force `
        -ErrorAction Stop

    Write-Host "[OK] New task registered"
    Write-Host "    TaskName: $($task.TaskName)"
    Write-Host "    Path:     $($task.TaskPath)"
    Write-Host "    State:    $($task.State)"
} catch {
    Write-Host "[FAIL] $($_.Exception.Message)"
    exit 1
}
