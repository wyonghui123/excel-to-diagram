$env:GIT_PAGER = ""
$env:PAGER = ""
Set-Location 'd:\filework\excel-to-diagram'

# FULL diff: stash@{2} vs HEAD for ALL files
# This shows what stash@{2} has that HEAD doesn't
Write-Host "========== stash@{2} vs HEAD: FULL FILE-BY-FILE DIFF STAT =========="
git diff "HEAD" "stash@{2}" --stat 2>$null

Write-Host ""
Write-Host "========== TOTAL =========="
$stat = git diff "HEAD" "stash@{2}" --stat 2>$null
$lastLine = $stat | Select-Object -Last 1
Write-Host $lastLine
