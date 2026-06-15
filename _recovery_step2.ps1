$env:GIT_PAGER = ""
$env:PAGER = ""
Set-Location 'd:\filework\excel-to-diagram'

# Export stash@{2} as patch (the big one - 399 files)
Write-Host "Exporting stash@{2} patch..."
git --no-pager diff "stash@{2}^..stash@{2}" 2>$null | Out-File -FilePath "d:\filework\excel-to-diagram\_stash2.patch" -Encoding UTF8
Write-Host "  stash@{2} patch exported"

# Export stash@{0} as patch (20 files)
Write-Host "Exporting stash@{0} patch..."
git --no-pager diff "stash@{0}^..stash@{0}" 2>$null | Out-File -FilePath "d:\filework\excel-to-diagram\_stash0.patch" -Encoding UTF8
Write-Host "  stash@{0} patch exported"

# Create recovery branch
Write-Host "Creating recovery branch..."
git checkout -b recovery/stash-restore 2>&1 | Select-Object -First 3

Write-Host ""
Write-Host "Current branch:"
git branch --show-current
Write-Host "HEAD:"
git log --oneline -1
