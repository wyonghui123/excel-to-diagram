$snapDir = 'D:\TraeData\TraeCN\ModularData\ai-agent\snapshot'

Write-Host '===== Recently created snapshots (last 2 hours) =====' -ForegroundColor Cyan
Get-ChildItem $snapDir -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.CreationTime -gt (Get-Date).AddHours(-2) } |
    Sort-Object CreationTime -Descending |
    ForEach-Object {
        $size = (Get-ChildItem $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
        $count = (Get-ChildItem $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object).Count
        [PSCustomObject]@{ Name=$_.Name; GB=[math]::Round($size/1GB,2); Files=$count; CTime=$_.CreationTime }
    } | Format-Table -AutoSize

Write-Host '===== Recently created snapshots (any) =====' -ForegroundColor Cyan
Get-ChildItem $snapDir -Directory -Force -ErrorAction SilentlyContinue |
    Sort-Object CreationTime -Descending |
    Select-Object -First 10 |
    ForEach-Object {
        $size = (Get-ChildItem $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
        [PSCustomObject]@{ Name=$_.Name; GB=[math]::Round($size/1GB,2); CTime=$_.CreationTime }
    } | Format-Table -AutoSize

Write-Host '===== Detail of newest snapshot =====' -ForegroundColor Cyan
$newest = Get-ChildItem $snapDir -Directory -Force -ErrorAction SilentlyContinue | Sort-Object CreationTime -Descending | Select-Object -First 1
if ($newest) {
    Write-Host ("Newest: {0} (created {1})" -f $newest.Name, $newest.CreationTime)
    Get-ChildItem $newest.FullName -Force | Format-Table Mode, Name, Length, LastWriteTime -AutoSize
    $v2 = Join-Path $newest.FullName 'v2'
    if (Test-Path (Join-Path $v2 '.git')) {
        $git = Join-Path $v2 '.git'
        Write-Host '--- HEAD ---'
        Get-Content (Join-Path $git 'HEAD') | Out-Host
        Write-Host '--- last 5 refs/heads commits ---'
        $refDir = Join-Path $git 'refs\heads'
        Get-ChildItem $refDir -File -Force -ErrorAction SilentlyContinue | Select-Object -First 1 | ForEach-Object {
            $log = Join-Path $git "logs\refs\heads\$($_.Name)"
            if (Test-Path $log) {
                Get-Content $log | Select-Object -Last 5 | ForEach-Object {
                    $line = $_
                    $msg = ($line -split ' ', 6)[5]
                    Write-Host "  $msg"
                }
            }
        }
    }
}

Write-Host '===== Total size of newly-created snapshots today =====' -ForegroundColor Cyan
$today = (Get-Date).Date
$totalSize = 0
Get-ChildItem $snapDir -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.CreationTime -ge $today } |
    ForEach-Object {
        $totalSize += (Get-ChildItem $_.FullName -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
    }
Write-Host ("Today's new snapshots total: {0} GB" -f [math]::Round($totalSize/1GB,2))
