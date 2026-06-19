# Hotfix Workflow (v1.0, 2026-06-19)

> **Purpose**: When an agent discovers a bug affecting main during parallel development,
> this document provides the standard hotfix workflow.
> **Based on**: sgryt.com Git Worktrees guide + industry best practices.

## Core Principle

**Never switch branches in your current worktree.** Use a separate worktree for hotfixes
to preserve your current context and avoid losing accumulated understanding.

## Why Hotfix Branch (not just direct fix)?

| Approach | Problem |
|----------|---------|
| Fix directly in F1 wt | Mixes F1 + bug fix, hard to review |
| Switch branch in same wt | Loses F1 context, AI re-explains codebase |
| **Hotfix in separate wt** | **Clean separation, parallel progress** |

## Severity Classification

| Level | Definition | Response Time | Workflow |
|-------|-----------|---------------|----------|
| **P1 Critical** | Service down / data loss / security | < 15 min | Immediate hotfix (pause F1) |
| **P2 High** | Main flow blocked | < 1 hour | Parallel hotfix (no pause F1) |
| **P3 Medium** | Edge case issue | < 1 day | Backlog (after F1) |
| **P4 Low** | UI/UX minor | < 1 week | Backlog |

## P1 Critical Workflow (5 steps)

### Step 1: Stash Current F1 Work
```powershell
cd d:\filework\<F1-worktree>
git stash push -u -m "F1-WIP-$(date)"
```

### Step 2: Create Hotfix Worktree (from main, NOT from F1!)
```powershell
cd d:\filework\excel-to-diagram
git worktree add -b hotfix/bug-X-2026-06-19 ..\hotfix-bug-X-worktree main
```

### Step 3: Fix Bug in Hotfix Worktree
```powershell
cd d:\filework\hotfix-bug-X-worktree
# Write spec.md
cp d:\filework\spec_template.md .\spec.md
# Fix bug + test
git add .
git commit -m "hotfix: <description>

L1-Worktree: yes
L2-NoMain: yes
L3-Stash: no
L4-Status: yes
L5-Service: yes

Fixes: <bug-id>
Severity: P1
Base: main"
```

### Step 4: Merge to Main
```powershell
cd d:\filework\excel-to-diagram
git merge --no-ff --autostash hotfix/bug-X-2026-06-19 -m "Merge hotfix: <description>"
```

### Step 5: Rebase F1 Worktree + Restore Stash
```powershell
cd d:\filework\<F1-worktree>
git rebase main
git stash pop
# Resume F1 work
```

## P2 High Workflow (3 steps, parallel)

### Step 1: Create Hotfix Worktree (don't pause F1)
```powershell
cd d:\filework\excel-to-diagram
git worktree add -b hotfix/bug-X-2026-06-19 ..\hotfix-bug-X-worktree main
```

### Step 2: Fix Bug in Parallel (F1 continues)
```powershell
cd d:\filework\hotfix-bug-X-worktree
# Fix + test + commit
# Port: 3011-3019 (NOT 3010 main)
```

### Step 3: After F1 Done, Rebase F1
```powershell
cd d:\filework\<F1-worktree>
git fetch
git rebase main
```

## P3/P4 Workflow (1 step)

```powershell
# Update .coord/bugs.json
# Continue F1 work
# (Bug will be addressed later)
```

## Triage Decision Tree

```
Bug found?
  |
  ├─ Service crashes? ────→ P1: Immediate hotfix
  |
  ├─ Data corruption? ────→ P1: Immediate hotfix
  |
  ├─ Security issue? ─────→ P1: Immediate hotfix
  |
  ├─ Main flow blocked? ──→ P2: Parallel hotfix
  |
  ├─ Edge case fails? ────→ P3: Backlog
  |
  └─ UI/UX minor? ─────────→ P4: Backlog
```

## Common Pitfalls

| Pitfall | Avoid By |
|---------|---------|
| Switching branch in F1 wt | Use separate hotfix wt |
| Hotfix based on F1 branch | Branch from main, not F1 |
| Mix F1 + bug fix in one commit | Separate commits in separate wts |
| Forget to rebase F1 after hotfix | Document in AGENT_GUIDELINES |
| Test hotfix on main port (3010) | Use agent port 3011-3019 |
| Skip spec.md for hotfix | Always write spec.md (even for hotfix) |

## Real Example

**Scenario**: Agent A is developing F1 (add audit feature). Discovers critical bug:
cascade delete deletes wrong records.

```powershell
# 1. Stash F1 work
cd d:\filework\f1-audit-feature-worktree
git stash push -u -m "F1-WIP-audit-feature"

# 2. Create hotfix wt (from main!)
cd d:\filework\excel-to-diagram
git worktree add -b hotfix/cascade-delete-fix-2026-06-19 ..\hotfix-cascade-delete-worktree main

# 3. Fix bug
cd d:\filework\hotfix-cascade-delete-worktree
# ... write spec.md, fix code, test ...
git add . && git commit -m "hotfix: fix cascade delete deleting wrong records"

# 4. Merge to main
cd d:\filework\excel-to-diagram
git merge --no-ff --autostash hotfix/cascade-delete-fix-2026-06-19 -m "Merge hotfix: cascade delete"

# 5. Rebase F1 + restore
cd d:\filework\f1-audit-feature-worktree
git rebase main
git stash pop
# Continue audit feature work
```

## Related Documents

- [AGENT_GUIDELINES.md](file:///d:/filework/AGENT_GUIDELINES.md) - 5 iron laws
- [port-isolation.md](file:///d:/filework/excel-to-diagram/docs/port-isolation.md) - Port isolation
- [spec_template.md](file:///d:/filework/spec_template.md) - Spec template
- [INCIDENT_2026-06-17.md](file:///d:/filework/excel-to-diagram/.trae/rules/INCIDENT_2026-06-17.md) - Past incident

## Created

- Date: 2026-06-19
- Author: Smart Agent A
- Version: 1.0
- Worktree: bug-triage-worktree
- Base commit: f7c7d95