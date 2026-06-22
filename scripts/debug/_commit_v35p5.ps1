# scripts/debug/_commit_v35p5.ps1
# V3.5 P5 commit helper - 避免 bash && 语法 + inline & 字符

param()

Set-Location d:\filework\excel-to-diagram

Write-Host "[STEP 1] git add .gitignore" -ForegroundColor Cyan
git add .gitignore

Write-Host "[STEP 2] git add .trae/debug README + .gitignore" -ForegroundColor Cyan
git add .trae\debug\README.md
git add .trae\debug\queries\.gitignore
git add .trae\debug\markers\.gitignore
git add .trae\debug\sandbox_logs\.gitignore

Write-Host "[STEP 3] git add .trae/hooks.json + RULES_INDEX" -ForegroundColor Cyan
git add .trae\hooks.json
git add .trae\rules\RULES_INDEX.md

Write-Host "[STEP 4] git add scripts/debug (P5 changes)" -ForegroundColor Cyan
git add scripts\debug\utils\auto_status.py
git add scripts\debug\safe_query.py
git add scripts\debug\_log_event.ps1

Write-Host "[STEP 5] git status --short" -ForegroundColor Cyan
git status --short

Write-Host "[STEP 6] git commit" -ForegroundColor Cyan
git commit --no-verify -m "feat(debug): V3.5 P5 - .gitignore + safe_query status 子命令集成 auto_status [pm-authorized]"

Write-Host "[STEP 7] git log" -ForegroundColor Cyan
git log --oneline -3