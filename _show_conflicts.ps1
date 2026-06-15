$env:GIT_PAGER = ""
$env:PAGER = ""
Set-Location 'd:\filework\excel-to-diagram'

$conflicts = @(
    "meta/api/special_routes_api.py",
    "meta/core/interceptors/data_permission_interceptor.py",
    "meta/schemas/dimension_object_mapping.yaml",
    "meta/services/dimension_scope_engine.py",
    "meta/services/import_export_service.py",
    "src/components/common/MasterDetailLayout/MasterDetailLayout.vue",
    "src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue",
    "src/composables/useMermaid/renderer/useSvgProcessor.js"
)

foreach ($f in $conflicts) {
    Write-Host "========== $f =========="
    $content = Get-Content $f -Raw -Encoding UTF8 2>$null
    $markers = ($content | Select-String -Pattern "<<<<<<" -AllMatches).Matches.Count
    Write-Host "  Conflict markers: $markers"
    
    # Show the conflict sections
    $lines = Get-Content $f -Encoding UTF8 2>$null
    $inConflict = $false
    $conflictNum = 0
    foreach ($line in $lines) {
        if ($line -match '^<<<<<<') {
            $conflictNum++
            $inConflict = $true
            Write-Host "  --- Conflict #$conflictNum ---"
        }
        if ($inConflict) {
            Write-Host "    $line"
        }
        if ($line -match '^>>>>>>') {
            $inConflict = $false
            Write-Host ""
        }
    }
}
