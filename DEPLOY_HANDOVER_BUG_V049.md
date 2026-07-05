# Deploy Handover: BUG-V049 Production Import Stuck (FD Leak)

> **Trigger**: User reports production `http://172.20.59.7:8081/system/archdata` global import "almost stuck 0% not moving"
> **Date**: 2026-07-05
> **Author**: dev-agent
> **Target branch**: `fix/V049-import-fd-leak` -> coordinator cherry-pick to `release/pre-2026-06-29`
> **Env**: dev worktree (worktree-V049), awaiting integration 3007/3018 validation

---

## 1. Summary

| Item | Content |
|---|---|
| Bug ID | BUG-V049 |
| Trigger | User clicks global import in production `/system/archdata?tab=business_object`, picks large Excel (20k rows), progress bar stuck at 0% |
| User error | `[Errno 24] Too many open files: '/tmp/tmpeci25jgz'` (error code 23f6a90d4e668284362d88519494bd79) |
| Expected | Import completes in 16-26s (local SQLite benchmark) |
| Original bug | Progress 0% stuck, then re-import errors with Too many open files |

## 2. Root Cause (5 Why)

| Why | Answer |
|---|---|
| 1. Why stuck 0%? | Backend throws `OSError: Too many open files` |
| 2. Why FD exhausted? | `openpyxl read_only=True` mode creates 3-5 temp files per wb |
| 3. Why accumulate? | `import_cascade` + `_import_sheet` double `load_workbook` (~12 FD/import), multi-sheet + multi-user |
| 4. Why trigger on Linux? | Linux default `ulimit -n = 1024`, single import needs ~12 FD |
| 5. Why not caught? | Local dev uses Windows (resource module unavailable), test uses SQLite, neither hits ulimit |

**Root cause**: openpyxl read_only temp file FD leak + Linux default ulimit 1024 insufficient.

## 3. Fix

### Fix 1: Process-level FD limit

**File**: `waitress_server.py` (line 36-55)

On startup `setrlimit(RLIMIT_NOFILE, (65536, ...))`:
- Effective on Linux, raise to 65536
- Windows skipped (resource module unavailable)

### Fix 2: Force-close openpyxl wb + GC

**File**: `meta/services/import_export_service.py` (line 5637-5647)

`import_cascade` end path:
```python
try:
    wb.close()
except Exception:
    pass
import gc
gc.collect()
```

## 4. Git Status

### 4.1 Worktree

```
worktree: D:/filework/worktree-V049
branch:   fix/V049-import-fd-leak (local commit, awaiting push)
base:     release/pre-2026-06-29 @ 8bfcbff
```

### 4.2 Commit (local, not pushed)

```
[fix/V049-import-fd-leak 89c63f0] fix(be): V049 production import stuck fix - FD leak
 3 files changed, 44 insertions(+), 3 deletions(-)
  waitress_server.py
  meta/services/import_export_service.py
  spec.md
```

### 4.3 Push Status

NOT PUSHED -- pre-push hook (AI content guard) rejected push, because entire src/ has 36 CRITICAL + 21 HIGH legacy violations.

NOT introduced by my commit. Pre-existing on main branch (V044 era).

**Needs coordinator**:
- Option A: Coordinator evaluates push risk, decides `SKIP_AI_CHECK=1` or batch fix CRITICAL first
- Option B: Coordinator `git push origin fix/V049-import-fd-leak --no-verify` (like V037)
- Option C: Coordinator cherry-pick `89c63f0` directly to release/pre-2026-06-29 (worktree already has it, no push needed)

## 5. Notification Status

- [x] dev-agent commit done (89c63f0 in fix/V049-import-fd-leak)
- [ ] **coordinator handles push / cherry-pick** <-- current todo
- [ ] e2e agent deploys to integration 3007/3018 validation
- [ ] PM validates in main 3006

## 6. Coordinator Action Items

### Step 1: Evaluate CRITICAL legacy issues

```bash
cd D:/filework/worktree-V049
git diff 8bfcbff..HEAD --stat
# Should show only 3 files (waitress_server, import_export, spec.md)
# If src/ has diff, that's worktree-V049 dirty tree, not commit-introduced
```

If `git diff` only shows my 3 files, CRITICAL issues are pre-existing main. Coordinator can:
- `git push origin fix/V049-import-fd-leak --no-verify`
- Or `SKIP_AI_CHECK=1 git push origin fix/V049-import-fd-leak` (hook line 18)

### Step 2: Cherry-pick to release/pre-2026-06-29

```bash
cd D:/filework/release-prep-worktree
git fetch origin fix/V049-import-fd-leak
git cherry-pick 89c63f0
# Expected: no conflict (3 files all whitelisted)
```

### Step 3: Deploy to integration 3007/3018

```bash
pwsh -File D:/filework/scripts/check-sha-consistency.ps1 -Strict
pwsh -File D:/filework/scripts/sync-integration-db.ps1 -Force  # if schema change
pwsh -File D:/filework/scripts/stop-integration.ps1 -Force
pwsh -File D:/filework/scripts/start-integration.ps1
```

### Step 4: e2e agent validates

Key test (user reported path):
- Select PUM(564) + SP(332) + relationship INTERNAL + CROSS_BOUNDARY
- Run user original Excel (BIP application architecture data import template)
- Expected: 18-26s completion (local benchmark), progress 0 to 100

FD validation:
```bash
lsof -p <pid> | grep /tmp/ | wc -l  # should be 0
cat /proc/<pid>/limits | grep "open files"  # should be 65536
```

## 7. Coordinator Completion Checklist

- [ ] push success (origin/fix/V049-import-fd-leak exists)
- [ ] cherry-pick to release/pre-2026-06-29
- [ ] integration 3007/3018 restarted
- [ ] e2e test PASS
- [ ] notify PM for 3006 validation

## 8. Retro (dev-agent part)

Mistakes:
1. Did not read SOP_INFRASTRUCTURE.md first, edited code in release-prep-worktree directly (violation of L5)
2. Used integration (local SQLite) to test production issue, wrong root cause
3. User gave real error [Errno 24], I did not locate immediately, ran cProfile blindly

Correction:
1. After user reminded, read SOP_INFRASTRUCTURE.md + development-workflow.md
2. Created independent worktree-V049 (fix/V049-import-fd-leak)
3. Commit to fix branch (not release)
4. Reverted modifications in release-prep-worktree
5. Wrote DEPLOY_HANDOVER to notify coordinator

Lessons:
- Read SOP first thing
- production != integration
- Real error code > cProfile speculation
- Strictly follow L1-L6 iron rules

---

*Author: dev-agent (V049)*
*Date: 2026-07-05*
*Status: dev done, awaiting coordinator push + cherry-pick + integration deploy*