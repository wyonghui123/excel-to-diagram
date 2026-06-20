Get-ChildItem 'd:\filework\excel-to-diagram\node_modules\.bin\' -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like '*vite*' -or $_.Name -like 'npx*' } |
    Select-Object Name, FullName, Length |
    Format-Table -AutoSize | Out-String -Width 200