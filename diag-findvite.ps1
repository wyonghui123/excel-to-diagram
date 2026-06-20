$logPath = 'd:\filework\excel-to-diagram\diag-findvite.log'
$log = @()

# Get process listening on port 3004
$conn = Get-NetTCPConnection -LocalPort 3004 -State Listen -ErrorAction SilentlyContinue
if ($conn) {
    $pid = $conn.OwningProcess
    $log += "Port 3004 listener PID: $pid"
    $p = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($p) {
        $log += "Process name: $($p.ProcessName)"
        $log += "Started: $($p.StartTime)"
        $log += "Path: $($p.Path)"
        $log += "CommandLine: $($p.CommandLine)"
    }
} else {
    $log += "[NO listener on port 3004]"
}

# Find all node processes running vite
$log += ""
$log += "=== All node processes ==="
Get-Process node -ErrorAction SilentlyContinue | ForEach-Object {
    $log += "PID=$($_.Id) Started=$($_.StartTime) Cmd=$($_.CommandLine)"
}

$log | Out-File $logPath -Encoding UTF8