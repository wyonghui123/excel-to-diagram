$logPath = 'd:\filework\excel-to-diagram\find-vite-result.log'
$log = @()

$conn = Get-NetTCPConnection -LocalPort 3004 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $pid = $conn.OwningProcess
    $log += "Port 3004 listener PID: $pid"
    $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($p) {
        $log += "Process name: $($p.ProcessName)"
        $log += "Started: $($p.StartTime)"
        $log += "Path: $($p.Path)"
    }
} else {
    $log += "[NO listener on port 3004]"
}

$log | Out-File $logPath -Encoding UTF8