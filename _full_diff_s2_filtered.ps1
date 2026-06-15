$env:GIT_PAGER = ""
$env:PAGER = ""
Set-Location 'd:\filework\excel-to-diagram'

# Get all files that differ between stash@{2} and HEAD
$allDiffFiles = git diff "HEAD" "stash@{2}" --name-only 2>$null

# Filter to source code only (exclude context, test_temp, debug scripts, etc.)
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

Write-Host "========== stash@{2} vs HEAD: SOURCE CODE DIFFERENCES =========="
Write-Host "Total differing files: $($allDiffFiles.Count)"
Write-Host "Source code files: $($sourceFiles.Count)"
Write-Host ""

# Group by directory
$sourceFiles | ForEach-Object {
    $dir = ($_ -split '/')[0..1] -join '/'
    $dir
} | Group-Object | Sort-Object Count -Descending | ForEach-Object {
    Write-Host ("{0,4}  {1}" -f $_.Count, $_.Name)
}

Write-Host ""
Write-Host "========== FULL LIST =========="
$sourceFiles | ForEach-Object { Write-Host "  $_" }
