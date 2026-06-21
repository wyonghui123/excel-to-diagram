# V3.5 sandbox-safe git status reporter
$ErrorActionPreference = "Stop"
$output = @{
    timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    branch = ""
    uncommitted = @()
    worktrees = @()
}

# 切换到项目目录
Set-Location "d:\filework\excel-to-diagram"

# git status
try {
    $output.branch = git rev-parse --abbrev-ref HEAD 2>&1
    $statusLines = git status --short 2>&1
    $output.uncommitted = $statusLines
} catch {
    $output.error = $_.Exception.Message
}

# worktree list
try {
    $wtOutput = git worktree list 2>&1
    $output.worktrees = $wtOutput
} catch {
    $output.worktree_error = $_.Exception.Message
}

# 写文件
$outDir = ".trae\debug\queries"
if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
$outFile = Join-Path $outDir "git_status.json"
$output | ConvertTo-Json -Depth 5 | Out-File -FilePath $outFile -Encoding UTF8

Write-Host "WROTE: $outFile"
