try {
    $r1 = Invoke-WebRequest -Uri 'http://localhost:3010/api/v1/auth/dev-login?username=admin' -UseBasicParsing -TimeoutSec 5
    Write-Host "BACKEND 3010: status=$($r1.StatusCode)"
} catch {
    Write-Host "BACKEND 3010 ERROR: $($_.Exception.Message)"
}
try {
    $r2 = Invoke-WebRequest -Uri 'http://localhost:3004' -UseBasicParsing -TimeoutSec 5
    Write-Host "FRONTEND 3004: status=$($r2.StatusCode)"
} catch {
    Write-Host "FRONTEND 3004 ERROR: $($_.Exception.Message)"
}