$logPath = 'd:\filework\excel-to-diagram\diag-vitestructure.log'
$log = @()

$log += "=== vite directory structure ==="
$basePath = 'd:\filework\excel-to-diagram\node_modules\vite'
if (Test-Path $basePath) {
    Get-ChildItem $basePath -Force -ErrorAction SilentlyContinue | ForEach-Object { $log += $_.Name }
} else {
    $log += "[MISS] $basePath"
}

$log += ""
$log += "=== Look for vite.js ==="
$candidates = @(
    'd:\filework\excel-to-diagram\node_modules\vite\bin\vite.js',
    'd:\filework\excel-to-diagram\node_modules\vite\dist\node\cli.js',
    'd:\filework\excel-to-diagram\node_modules\vite\dist\node\index.js'
)
foreach ($c in $candidates) {
    if (Test-Path $c) {
        $log += "[OK] $c"
    } else {
        $log += "[NO] $c"
    }
}

$log | Out-File $logPath -Encoding UTF8