$procs = Get-CimInstance Win32_Process -Filter "Name='Trae CN.exe'" -ErrorAction SilentlyContinue
foreach ($p in $procs) {
    Write-Host ("PID={0}  Started={1}" -f $p.ProcessId, $p.CreationDate)
}
if (-not $procs) { Write-Host 'No Trae CN.exe running.' }
