Get-ChildItem 'd:\filework\excel-to-diagram\node_modules\.bin\' -Filter 'vite*' -ErrorAction SilentlyContinue |
    Select-Object Name, FullName |
    Format-Table -AutoSize | Out-File 'd:\filework\excel-to-diagram\diag-out2.log' -Encoding UTF8