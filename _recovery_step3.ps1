$env:GIT_PAGER = ""
$env:PAGER = ""
Set-Location 'd:\filework\excel-to-diagram'

Write-Host "Applying stash@{2}..."
$result = git stash apply "stash@{2}" 2>&1
$exitCode = $LASTEXITCODE

Write-Host "Exit code: $exitCode"

# Check for conflicts
$conflicts = git diff --name-only --diff-filter=U 2>$null
if ($conflicts) {
    Write-Host ""
    Write-Host "=== CONFLICT FILES ==="
    $conflicts | ForEach-Object { Write-Host "  CONFLICT: $_" }
} else {
    Write-Host "No conflicts!"
}

# Check what was applied
$applied = git diff --name-only 2>$null
Write-Host ""
Write-Host "Applied files: $($applied.Count)"
$applied | ForEach-Object { Write-Host "  $_" } | Select-Object -First 30
