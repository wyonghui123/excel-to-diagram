$env:GIT_PAGER = ""
$env:PAGER = ""
Set-Location 'd:\filework\excel-to-diagram'

# stash@{0} vs HEAD
$s0files = git --no-pager diff "HEAD" "stash@{0}" --name-only 2>$null | Where-Object {
    $_ -notmatch '^\.trae/context/' -and
    $_ -notmatch '^test_temp/' -and
    $_ -notmatch '^test-results/' -and
    $_ -notmatch '^playwright-report/' -and
    $_ -notmatch '^meta/db_monitor_logs/' -and
    $_ -notmatch '^uploads/' -and
    $_ -notmatch 'components\.d\.ts$'
}

# Working tree vs HEAD
$wtFiles = git --no-pager diff "HEAD" --name-only 2>$null

# Write results
$out = @()
$out += "========== stash@{0} vs HEAD (source code) =========="
$out += "Count: $($s0files.Count)"
$out += ""
$s0files | ForEach-Object { $out += "  $_" }

$out += ""
$out += "========== Working tree vs HEAD =========="
$out += "Count: $($wtFiles.Count)"
$out += ""
$wtFiles | ForEach-Object { $out += "  $_" }

# Now the critical part: dimension_scope_engine.py
$out += ""
$out += "========== dimension_scope_engine.py: stash@{2} vs HEAD =========="
$s2dse = git --no-pager diff "HEAD" "stash@{2}" -- meta/services/dimension_scope_engine.py 2>$null
if ($s2dse) {
    $out += "HAS DIFFERENCES"
    $s2dse | Select-Object -First 80 | ForEach-Object { $out += $_ }
} else {
    $out += "NO DIFFERENCES (same in both)"
}

$out += ""
$out += "========== dimension_scope_engine.py: stash@{0} vs HEAD =========="
$s0dse = git --no-pager diff "HEAD" "stash@{0}" -- meta/services/dimension_scope_engine.py 2>$null
if ($s0dse) {
    $out += "HAS DIFFERENCES"
    $s0dse | Select-Object -First 80 | ForEach-Object { $out += $_ }
} else {
    $out += "NO DIFFERENCES (same in both)"
}

$out += ""
$out += "========== dimension_scope_engine.py: working tree vs HEAD =========="
$wtdse = git --no-pager diff "HEAD" -- meta/services/dimension_scope_engine.py 2>$null
if ($wtdse) {
    $out += "HAS DIFFERENCES"
    $wtdse | Select-Object -First 80 | ForEach-Object { $out += $_ }
} else {
    $out += "NO DIFFERENCES (same in both)"
}

$out | Out-File -FilePath "d:\filework\excel-to-diagram\_full_analysis.txt" -Encoding UTF8
Write-Host "Written to _full_analysis.txt"
