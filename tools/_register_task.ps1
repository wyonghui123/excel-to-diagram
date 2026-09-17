# Register Windows Task Scheduler task with elevated privileges
# Requires: Administrator (will auto-elevate)

$xmlPath = 'D:\filework\worktrees/release-prep\tools\yonaa_alert_monitor.xml'

# Load the task XML and register
try {
    $task = Register-ScheduledTask `
        -TaskName 'yonaa_alert_monitor' `
        -Xml (Get-Content $xmlPath -Raw) `
        -Force `
        -ErrorAction Stop
    Write-Host "[OK] Task registered successfully"
    Write-Host "    TaskName: $($task.TaskName)"
    Write-Host "    Path:     $($task.TaskPath)"
    Write-Host "    State:    $($task.State)"
} catch {
    Write-Host "[FAIL] $($_.Exception.Message)"
    exit 1
}
