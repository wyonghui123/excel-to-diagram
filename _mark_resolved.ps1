$env:GIT_PAGER = ""
$env:PAGER = ""
Set-Location 'd:\filework\excel-to-diagram'

# Mark all conflicts as resolved
git add -A 2>&1 | Select-Object -First 5

# Verify
$conflicts = git diff --name-only --diff-filter=U 2>$null
if ($conflicts) {
    Write-Host "STILL CONFLICTED: $($conflicts.Count)"
} else {
    Write-Host "ALL CONFLICTS MARKED AS RESOLVED"
}

# Show what's staged
$staged = git diff --cached --stat 2>$null | Select-Object -Last 5
Write-Host ""
Write-Host "Staged changes:"
$staged | ForEach-Object { Write-Host "  $_" }
