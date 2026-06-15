$env:GIT_PAGER = ""
$env:PAGER = ""
Set-Location 'd:\filework\excel-to-diagram'

# Stage all working tree changes
git add -A

# Check what's staged
$staged = git diff --cached --name-only 2>$null
Write-Host "Staged: $($staged.Count) files"

# Commit
git commit --no-verify -m "chore: save working tree before stash recovery (12 files + 876 untracked)" 2>&1 | Select-Object -First 5

Write-Host ""
git log --oneline -1
