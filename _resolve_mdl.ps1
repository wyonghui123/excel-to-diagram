$env:GIT_PAGER = ""
$env:PAGER = ""
Set-Location 'd:\filework\excel-to-diagram'

# Use working tree version (Updated upstream) for MasterDetailLayout
# because it has the latest fixes for resizer and collapse button
git checkout --ours -- "src/components/common/MasterDetailLayout/MasterDetailLayout.vue" 2>&1

Write-Host "Resolved MasterDetailLayout.vue (kept working tree version)"
