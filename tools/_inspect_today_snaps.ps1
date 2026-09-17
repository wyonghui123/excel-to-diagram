$snapDir = 'D:\TraeData\TraeCN\ModularData\ai-agent\snapshot'

Write-Host '===== Sample 5 snapshot internals (object counts, working tree files) =====' -ForegroundColor Cyan
Get-ChildItem $snapDir -Directory -Force -ErrorAction SilentlyContinue |
    Sort-Object CreationTime -Descending |
    Select-Object -First 5 |
    ForEach-Object {
        Write-Host ('-' * 60)
        Write-Host ("SNAP: {0}" -f $_.Name)
        $v2 = Join-Path $_.FullName 'v2'
        if (-not (Test-Path $v2)) { Write-Host '  (no v2/)'; return }
        Write-Host '  v2/ contents:'
        Get-ChildItem $v2 -Force | Select-Object Mode, Name, Length | Format-Table -AutoSize | Out-Host
        $git = Join-Path $v2 '.git'
        if (Test-Path $git) {
            $objDir = Join-Path $git 'objects'
            if (Test-Path $objDir) {
                $objCount = (Get-ChildItem $objDir -Directory -Force | ForEach-Object {
                    Get-ChildItem $_.FullName -File -Force
                } | Measure-Object).Count
                Write-Host ("  .git/objects count: {0}" -f $objCount)
            }
            $refDir = Join-Path $git 'refs\heads'
            if (Test-Path $refDir) {
                Get-ChildItem $refDir -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
                    Write-Host ("  ref: {0} -> {1}" -f $_.Name, (Get-Content $_.FullName).Trim())
                }
            }
            $logDir = Join-Path $git 'logs\refs\heads'
            if (Test-Path $logDir) {
                Get-ChildItem $logDir -File -Force -ErrorAction SilentlyContinue | Select-Object -First 2 | ForEach-Object {
                    $cnt = (Get-Content $_.FullName | Measure-Object).Count
                    Write-Host ("  log {0}: {1} commits" -f $_.Name, $cnt)
                }
            }
        }
    }
