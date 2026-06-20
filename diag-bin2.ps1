$logPath = 'd:\filework\excel-to-diagram\diag-out3.log'
$log = @()

$binDir = 'd:\filework\excel-to-diagram\node_modules\.bin'
$log += "=== .bin contents (first 30) ==="
if (Test-Path $binDir) {
    Get-ChildItem $binDir -ErrorAction SilentlyContinue | Select-Object -First 30 | ForEach-Object { $log += $_.Name }
} else {
    $log += "[MISS] $binDir"
}

$log += ""
$log += "=== Check vite packages ==="
$pkgPaths = @(
    'd:\filework\excel-to-diagram\node_modules\vite',
    'd:\filework\excel-to-diagram\node_modules\vite\package.json',
    'd:\filework\excel-to-diagram\node_modules\@vitejs'
)
foreach ($p in $pkgPaths) {
    if (Test-Path $p) {
        if ((Get-Item $p).PSIsContainer) {
            $log += "[DIR ] $p"
        } else {
            $log += "[FILE] $p ($((Get-Item $p).Length) bytes)"
        }
    } else {
        $log += "[MISS] $p"
    }
}

$log += ""
$log += "=== package.json devDependencies ==="
$pkg = Get-Content 'd:\filework\excel-to-diagram\package.json' -Raw -Encoding UTF8 | ConvertFrom-Json
if ($pkg.devDependencies) {
    $pkg.devDependencies.PSObject.Properties | ForEach-Object { $log += "$($_.Name) = $($_.Value)" }
}
if ($pkg.dependencies) {
    $log += "--- dependencies ---"
    $pkg.dependencies.PSObject.Properties | ForEach-Object { $log += "$($_.Name) = $($_.Value)" }
}

$log | Out-File $logPath -Encoding UTF8