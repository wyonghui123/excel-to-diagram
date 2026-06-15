$ErrorActionPreference = "Stop"
Set-Location "d:\filework\excel-to-diagram"

$count = 0
$v2_count = 0
$v1_count = 0
$miss_count = 0
$unknown_count = 0
$v2_already = @()
$v1_still = @()
$unknown_list = @()
$missing_list = @()

$lines = Get-Content "reports/v1_to_v2_plan.md" -Encoding UTF8 | Select-String -Pattern '^\| \d+ \| `\w'
foreach ($m in $lines) {
    $line = $m.Line
    if ($line -match '^\| (\d+) \| `([\w\-]+)\.spec\.js`') {
        $num = $Matches[1]
        $name = $Matches[2]
        $p = 'e2e/features/' + $name + '.spec.js'
        if (Test-Path $p) {
            $v1 = (Get-Content $p -Encoding UTF8 -Head 30 | Select-String -Pattern "from '../helpers/auth\.js'").Count
            $v2 = (Get-Content $p -Encoding UTF8 -Head 30 | Select-String -Pattern "from '../helpers/auto-fixtures\.js'").Count
            if ($v2 -gt 0) {
                $v2_already += "$num $name"
                $v2_count++
            } elseif ($v1 -gt 0) {
                $v1_still += "$num $name"
                $v1_count++
            } else {
                $unknown_list += "$num $name"
                $unknown_count++
            }
            $count++
        } else {
            $missing_list += "$num $name"
            $miss_count++
            $count++
        }
    }
}

Write-Host '=== v1_to_v2_plan.md Accuracy Audit ==='
Write-Host ''
Write-Host ('Total plan specs: ' + $count)
Write-Host ('Already v2 (not actually v1): ' + $v2_count)
Write-Host ('Still v1 (need migration): ' + $v1_count)
Write-Host ('Unknown: ' + $unknown_count)
Write-Host ('Missing file: ' + $miss_count)
Write-Host ''
Write-Host '=== Already v2 (wasted plan entries) ==='
$v2_already | ForEach-Object { Write-Host ('  ' + $_) }
Write-Host ''
Write-Host '=== Still v1 (need real migration) ==='
$v1_still | ForEach-Object { Write-Host ('  ' + $_) }
Write-Host ''
Write-Host '=== Unknown (need manual check) ==='
$unknown_list | ForEach-Object { Write-Host ('  ' + $_) }
Write-Host ''
Write-Host '=== Missing file ==='
$missing_list | ForEach-Object { Write-Host ('  ' + $_) }
