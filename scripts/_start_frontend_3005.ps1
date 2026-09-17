Set-Location 'd:\filework\excel-to-diagram'
$env:BACKEND_PORT = '3010'
Start-Process cmd -ArgumentList '/c','npm run dev -- --port 3005' -RedirectStandardOutput 'd:\filework\excel-to-diagram\logs\frontend-3005.log' -RedirectStandardError 'd:\filework\excel-to-diagram\logs\frontend-3005-err.log' -PassThru -WindowStyle Hidden