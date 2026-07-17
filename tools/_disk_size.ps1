$root = 'D:\TraeData\TraeCN\ModularData\ai-agent\snapshot'
Get-ChildItem $root -Directory | ForEach-Object {
    $size = 0
    $files = 0
    Get-ChildItem -Path $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $size += $_.Length
        $files++
    }
    [PSCustomObject]@{
        Id      = $_.Name
        GB      = [math]::Round($size / 1GB, 2)
        Files   = $files
        CTime   = $_.CreationTime
        LastW   = $_.LastWriteTime
    }
} | Sort-Object GB -Descending | Select-Object -First 15 | Format-Table -AutoSize

Write-Host '---- filework worktrees/release-prep detail ----' -ForegroundColor Cyan
Get-ChildItem 'D:\filework\worktrees/release-prep' -Directory | ForEach-Object {
    $size = 0
    Get-ChildItem -Path $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue | ForEach-Object { $size += $_.Length }
    [PSCustomObject]@{ Name = $_.Name; GB = [math]::Round($size / 1GB, 2) }
} | Sort-Object GB -Descending | Select-Object -First 10 | Format-Table -AutoSize
