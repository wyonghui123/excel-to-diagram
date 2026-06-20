# Spec: Landing Page Document Scroll + No Scrollbar

> **Task ID**: T-2026-06-20-001
> **Agent**: agent-landing-scroll
> **Worktree**: `d:\filework\detail-edit-tab-fix\`
> **Branch**: `fix-landing-scroll-2026-06-19`
> **Base commit**: `ce4a8e9` (current main HEAD)
> **Risk**: low (CSS-only, no business logic)

---

## 1. Goal

Landing page (/) use document scroll pattern (Vercel/Stripe/Linear/GitHub standard). Remove 4-layer overflow:hidden nesting. Browser shows no scrollbar.

## 2. Root Cause

```
body        { height: 100vh; overflow: hidden }  # L1 lock
#app        { height: 100vh; overflow: hidden }  # L2 lock
.app-shell__body     { overflow: hidden }        # L3 lock
.app-shell__content  { overflow: hidden }        # L4 lock
```

## 3. Changes (whitelist)

- `src/style.css` - body: remove height:100vh + overflow:hidden, set overflow-x:hidden overflow-y:auto; #app: remove height:100vh + overflow:hidden, set overflow:visible
- `src/components/common/AppShell/AppShell.vue` - .app-shell__body: remove overflow:hidden; .app-shell__content: overflow:hidden → overflow:visible

## 4. Forbidden

- `.agent-status.json`, `service_manager.ps1`, `.git/hooks/*`, main worktree files, `stash@{0}`

## 5. Acceptance Criteria

- [x] Work in worktree (D:/filework/detail-edit-tab-fix)
- [x] New branch `fix-landing-scroll-2026-06-19` from main
- [x] Apply 3 CSS fixes (body, #app, .app-shell__body, .app-shell__content)
- [x] Commit with L1-L5 declaration
- [ ] Update .agent-status.json with worktree entry
- [ ] Coordinator merge to main → Vite HMR picks up
- [ ] User verifies: no scrollbar, page scrolls smoothly

## 6. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Other pages affected | low | Only affects top-level body/#app; child components control their own scroll |
| Mobile layout | very low | min-height:0 preserved |
| Keyboard PgUp/PgDn | very low | document scroll natively supports |

## 7. Test Plan (after merge)

1. Open http://localhost:3004/ → no scrollbar visible
2. Scroll mouse → entire page scrolls (not nested box)
3. Resize to 320px → no horizontal scroll
4. Switch to /system/archdata → layout normal