Set-Location 'd:\filework\excel-to-diagram\meta'
$env:PORT = '3010'
$env:SKIP_PORT_CHECK = '1'
Start-Process python -ArgumentList 'server.py' -RedirectStandardOutput 'd:\filework\excel-to-diagram\logs\backend3010.out' -RedirectStandardError 'd:\filework\excel-to-diagram\logs\backend3010.err' -PassThru -WindowStyle Hidden