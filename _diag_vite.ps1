$ErrorActionPreference = 'Continue'
Set-Location 'd:\filework\excel-to-diagram'

$logOut = 'd:\filework\excel-to-diagram\_vite_out.log'
$logErr = 'd:\filework\excel-to-diagram\_vite_err.log'

Write-Host "Starting Vite..."
$p = Start-Process npx `
    -ArgumentList 'vite','--port','3004','--host' `
    -RedirectStandardOutput $logOut `
    -RedirectStandardError $logErr `
    -PassThru -NoNewWindow

Write-Host "Vite PID = $($p.Id)"
Start-Sleep -Seconds 10

try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch { Write-Host "Stop-Process: $_" }

Write-Host "`n===== STDOUT ====="
if (Test-Path $logOut) { Get-Content $logOut -Tail 40 -Encoding UTF8 }
Write-Host "`n===== STDERR ====="
if (Test-Path $logErr) { Get-Content $logErr -Tail 40 -Encoding UTF8 }

# Cleanup
Remove-Item $logOut,$logErr -ErrorAction SilentlyContinue