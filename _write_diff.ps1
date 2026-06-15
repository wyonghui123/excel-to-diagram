git --no-pager diff "HEAD" "stash@{2}" --name-only 2>$null | Where-Object {
    $_ -notmatch '^\.trae/context/' -and
    $_ -notmatch '^test_temp/' -and
    $_ -notmatch '^test-results/' -and
    $_ -notmatch '^playwright-report/' -and
    $_ -notmatch '^meta/db_monitor_logs/' -and
    $_ -notmatch '^uploads/' -and
    $_ -notmatch '^check_' -and
    $_ -notmatch '^_' -and
    $_ -notmatch 'components\.d\.ts$'
} | Out-File -FilePath "d:\filework\excel-to-diagram\_s2_source_diff.txt" -Encoding UTF8

Write-Host "Done. Reading file..."
