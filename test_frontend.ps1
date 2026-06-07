$ErrorActionPreference = "Stop"
try {
    $response = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 2
    Write-Host "Frontend is running. Status: $($response.StatusCode)"
} catch {
    Write-Host "Frontend NOT responding: $($_.Exception.Message)"
}
