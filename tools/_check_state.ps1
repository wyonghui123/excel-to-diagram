$d = Get-PSDrive D
Write-Host ("D: free={0} GB" -f [math]::Round($d.Free/1GB,2))

Write-Host '----- snapshot/tbd contents -----' -ForegroundColor Cyan
$tbd = 'D:\TraeData\TraeCN\ModularData\ai-agent\snapshot\tbd'
if (Test-Path $tbd) {
    Get-ChildItem $tbd -Force | Select-Object Name, Mode, Length, LastWriteTime | Format-Table -AutoSize
} else { Write-Host 'tbd not found' }

Write-Host '----- verify if "moved" snapshot still exists at original path -----' -ForegroundColor Cyan
$orig = 'D:\TraeData\TraeCN\ModularData\ai-agent\snapshot\6a48a8b3c1de45488785910f'
if (Test-Path $orig) {
    $size = (Get-ChildItem $orig -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    Write-Host ("Original STILL exists: {0} GB" -f [math]::Round($size/1GB,2))
    Get-ChildItem $orig -Force | Select-Object Mode, Name, LastWriteTime | Format-Table -AutoSize
} else { Write-Host 'Original already removed.' }
