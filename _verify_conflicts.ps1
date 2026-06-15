$env:GIT_PAGER = ""
$env:PAGER = ""
Set-Location 'd:\filework\excel-to-diagram'

# Check for remaining conflict markers
$conflicts = git diff --name-only --diff-filter=U 2>$null
if ($conflicts) {
    Write-Host "REMAINING CONFLICTS:"
    $conflicts | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host "ALL CONFLICTS RESOLVED!"
}

# Also grep for conflict markers in tracked files
$markers = Get-ChildItem -Recurse -Include *.py,*.vue,*.js,*.yaml -File | Select-String -Pattern "^<<<<<<|^>>>>>>" | Select-Object -First 10
if ($markers) {
    Write-Host ""
    Write-Host "FILES WITH CONFLICT MARKERS:"
    $markers | ForEach-Object { Write-Host "  $($_.Path):$($_.LineNumber) $($_.Line.Trim())" }
} else {
    Write-Host "No conflict markers found in source files."
}
