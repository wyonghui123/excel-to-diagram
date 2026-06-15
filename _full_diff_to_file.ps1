$env:GIT_PAGER = ""
$env:PAGER = ""
Set-Location 'd:\filework\excel-to-diagram'

$allDiffFiles = git diff "HEAD" "stash@{2}" --name-only 2>$null

$sourceFiles = $allDiffFiles | Where-Object {
    $_ -notmatch '^\.trae/context/' -and
    $_ -notmatch '^test_temp/' -and
    $_ -notmatch '^test-results/' -and
    $_ -notmatch '^playwright-report/' -and
    $_ -notmatch '^meta/db_monitor_logs/' -and
    $_ -notmatch '^uploads/' -and
    $_ -notmatch '^check_' -and
    $_ -notmatch '^_' -and
    $_ -notmatch 'components\.d\.ts$'
}

$out = @()
$out += "Total differing files: $($allDiffFiles.Count)"
$out += "Source code files: $($sourceFiles.Count)"
$out += ""

# Group by top-level dir
$groups = $sourceFiles | ForEach-Object {
    $dir = ($_ -split '/')[0]
    $dir
} | Group-Object | Sort-Object Count -Descending

$out += "=== BY DIRECTORY ==="
foreach ($g in $groups) {
    $out += ("{0,4}  {1}" -f $g.Count, $g.Name)
}

$out += ""
$out += "=== FULL FILE LIST ==="
foreach ($f in $sourceFiles) {
    $out += "  $f"
}

$out | Out-File -FilePath "d:\filework\excel-to-diagram\_s2_vs_head.txt" -Encoding UTF8
Write-Host "Written to _s2_vs_head.txt"
Write-Host "Source code files: $($sourceFiles.Count)"
