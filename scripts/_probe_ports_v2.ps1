foreach ($port in @(3004, 3005, 3010)) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:$port/" -UseBasicParsing -TimeoutSec 3
        Write-Host "PORT $port : status=$($r.StatusCode)"
    } catch {
        Write-Host "PORT $port : DOWN - $($_.Exception.Message.Split([Environment]::NewLine)[0])"
    }
}