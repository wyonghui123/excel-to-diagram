---
alwaysApply: false
description: "编码问题防护 v20260612：mojibake 修复和预防措施"
---

# Encoding Corruption Prevention Guide (v20260612)

> **Post-Incident Guide** for the 2026-06-12 GBK-mojibake event.
> New file (not appended to existing rules) to avoid pre-commit hook
> blocking on historical mojibake that exists in older rules files.

## 1. Event Summary

**Date**: 2026-06-12
**Symptom**: `src/utils/httpClient.js` Vite parse error; file size anomaly +2770 bytes.
**Diagnostic Data**:
- `node --check` -> exit 0 (JS structure intact)
- UTF-8 strict decode -> OK (encoding itself legal)
- High-byte followed by 0x3F count -> 81 (fullwidth '?' replaced with ASCII '?')
- Brace balance -> 161 == 161 (syntactically symmetric)

**Root Cause**: Agent write chain (IDE buffer / commit message share a channel)
interprets UTF-8 as GBK, replaces unmappable bytes (3-byte UTF-8 sequences) with
'?' (0x3F). Damage has already spread to **commit message layer** (commits
`347d8d9` and `7d0b78d` both have GBK-mojibake commit messages).

**Critical Correction**: The Vite parse error pointing to `line 322` is a
**red herring**. `node --check` passing means Acorn will not reject. The real
cause of a Vite error should be: (1) stale `node_modules/.vite` cache, (2) other
files in the import chain, (3) Vite deps pre-compile cache.

## 2. Five New Rules (Enforced by Toolchain)

### Rule 31: JS Structure Health Check

- All `.js` / `.jsx` / `.ts` / `.tsx` must pass `node --check` before commit
- pre-commit hook runs this automatically; failure blocks commit
- Bypass (emergency only): `git commit --no-verify` (document reason in report)

### Rule 32: UTF-8 Encoding Health Check (GBK-mojibake Detection)

- pre-commit hook invokes `scripts/check_file_encoding.py --staged`
- Detection items:
  - Strict UTF-8 decode (failure -> reject)
  - High-byte followed by 0x3F pattern (hit -> reject, hint "GBK damage")
  - Known GBK-mojibake signature characters (U+7EFA U+5E74 U+7E41 U+9418 ...)
  - File size bloat vs HEAD > 2.0x
- Tool: `scripts/check_file_encoding.py` (v1.0+)

### Rule 33: Commit Message Encoding

- `git commit -m "..."` message must UTF-8 decode cleanly
- Agent must use ASCII for message (or ensure terminal/IDE encoding = UTF-8)
- Example OK: `feat(scripts): add check_file_encoding.py`
- Example BAD: `fix(ui): 淇 #12 - ...`

### Rule 34: Agent Startup Must Report `git stash list`

- Before any work, agent must run `git stash list` and tell the user
- Has stash -> stop immediately, wait for user decision (do not touch stash)
- No stash -> continue

### Rule 35: Vite Error Triage SOP (Don't Trust the Line Number)

When you receive "Vite parse error at line X":

1. **Immediately** run `node --check <reported file>` to verify JS is truly invalid
2. If `node --check` **passes** -> Vite's line number is untrustworthy; check:
   - `node_modules/.vite` cache (delete + rebuild: `rm -rf node_modules/.vite`)
   - All files in the import chain
   - Browser console for the actual error (not just stack trace)
3. If `node --check` **fails** -> the error location is line X, handle normally

**Counter-example**: Agent A blamed "Vite error line 322" on `httpClient.js`,
but `node --check` passed -> wasted 30+ minutes going in the wrong direction.

## 3. Tooling Landing

| Tool | Path | Status | Purpose |
|------|------|--------|---------|
| Encoding health script | `scripts/check_file_encoding.py` | OK v1.0+ | CLI GBK-mojibake detection |
| pre-commit hook | `.git/hooks/pre-commit` | OK Python mode | Block encoding damage + JS error commits |
| This document | `.trae/rules/encoding-prevention-v20260612.md` | OK v1.0 | 5 rules + SOP |

## 4. Known Historical Issues (Out of Scope for This Commit)

The following pre-existing issues are flagged for follow-up but NOT fixed here:

| # | Issue | Location | Reason for non-fix |
|---|-------|----------|--------------------|
| 1 | Historical mojibake in HEAD of `file-encoding-rules.md` | HEAD bytes 1-7477 | pre-commit would block; would need dedicated cleanup commit |
| 2 | 4 stashes present in working tree | `stash@{0}` to `stash@{3}` | Per [ai-agent-undo-protection.md](./ai-agent-undo-protection.md), Agent must not touch stash without user decision |
| 3 | Commit messages `347d8d9` / `7d0b78d` are GBK-mojibake | git history | Would need `git rebase -i` (high risk, user decision required) |
| 4 | `httpClient.js` working tree still has partial mojibake | `M src/utils/httpClient.js` | Was fixed by another Agent but not 100% clean (size 18072 vs HEAD 17553) |

**Why these are deferred**: Per project rules, Agent should not perform
destructive git operations (rebase, stash drop) without explicit user direction.
The prevention tools landed here will **prevent recurrence** going forward.

## 5. Test the Tools

```bash
# 1. Run the encoding check on a clean file (should pass)
python scripts/check_file_encoding.py scripts/check_file_encoding.py
# Expected: [OK] No issues.

# 2. Run on a known-mojibake file (should detect)
python scripts/check_file_encoding.py src/utils/httpClient.js
# Expected: [BAD] GBK_MOJIBAKE_FINGERPRINT, MOJIBAKE_CHARS

# 3. Dry-run the pre-commit hook (no staged changes -> no-op)
python .git/hooks/pre-commit
# Expected: [pre-commit] OK

# 4. Stage a JS file with a syntax error -> commit should be blocked
echo "const x = {" > /tmp/bad.js
git add /tmp/bad.js
git commit -m "test"  # should fail with [SYNTAX FAIL]
rm /tmp/bad.js
```

## 6. Related Rules

- [ai-agent-undo-protection.md](./ai-agent-undo-protection.md) - stash residue rules
- [file-encoding-rules.md](./file-encoding-rules.md) - existing encoding rules (Note: HEAD content has historical mojibake)
- [SESSION_REMINDER.md](./SESSION_REMINDER.md) - debugging rules 25-30
- [multi-agent-coordination.md](./multi-agent-coordination.md) - multi-Agent rules

---

_Document version: v1.0 | Date: 2026-06-12 | Author: Post-Incident Agent_
