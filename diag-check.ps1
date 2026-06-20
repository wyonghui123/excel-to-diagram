$dirs = @('node_modules\.bin', 'node_modules\vite', 'node_modules\.package-lock.json')
foreach ($d in $dirs) {
    $path = "d:\filework\excel-to-diagram\$d"
    if (Test-Path $path) {
        if ((Get-Item $path).PSIsContainer) {
            $count = (Get-ChildItem $path -Force | Measure-Object).Count
            Write-Host "[DIR ] $d -> $count items"
        } else {
            $size = (Get-Item $path).Length
            Write-Host "[FILE] $d -> $size bytes"
        }
    } else {
        Write-Host "[MISS] $d"
    }
}

$nm = 'd:\filework\excel-to-diagram\node_modules'
if (Test-Path $nm) {
    $topCount = (Get-ChildItem $nm -Force | Measure-Object).Count
    Write-Host "node_modules has $topCount top-level items"
}