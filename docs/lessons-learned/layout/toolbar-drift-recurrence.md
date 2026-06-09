# Toolbar Drift / Offset Recurrence

> **Date**: 2026-06-09
> **Status**: Active - Monitoring
> **Severity**: Medium (visual, non-blocking)
> **Recurrence**: 3+ times (user reported "countless times")

---

## Regression Incident: 2026-06-09 (Second Occasion)

After applying fixes earlier this session, all 3 files were **silently reverted** to their pre-fix state:

| File | Reverted Property | Current Value (Pre-Re-Apply) |
|------|-------------------|------------------------------|
| `MetaListPage.vue` | `flex-wrap` | `wrap` (was: `nowrap`) |
| `MetaListPage.vue` | `overflow` | `hidden` (was: `overflow-x: auto`) |
| `MetaListPage.vue` | `min-height` | (missing) |
| `MetaListPage.vue` | `position` | (missing) |
| `MetaListPage.vue` (compact) | `padding` | `var(--spacing-xs) 0` (was: `var(--spacing-xs) var(--spacing-sm)`) |
| `_meta-table.scss` | `border-bottom` | `1px solid var(--color-border)` (was: removed) |
| `GlobalToolbar.vue` | `gap` | `4px` (was: `8px`) |
| `GlobalToolbar.vue` | hover/focus/active styles | (missing) |
| `GlobalToolbar.vue` | `:deep(.el-button + .el-button)` | (missing) |

**Root cause of regression (suspected)**:
- Modifications were not committed to git
- Another session/tool/auto-format may have overwritten them
- The `//` Chinese comments in `<style>` blocks caused Vite parser errors which may have triggered editor rollbacks

**Re-applied 2026-06-09 with English comments and `overflow-x/y` split syntax (no `//` comments)**.

**Action items to prevent recurrence**:
1. Commit changes immediately after applying
2. Avoid Chinese comments in `<style>` blocks (Vite parser bug)
3. Set up visual regression test (see `testing/toolbar-test-coverage-gap.md`)

---

## Symptom

MetaListPage `.toolbar` appears to shift/offset position on certain pages or after state changes.
User reports: "metalist 的toolbar 发生了漂移，这个问题发生了无数次了，每次都是修好后过了不久又出现"

## Root Cause Analysis

### Primary Cause: Global vs Scoped CSS Conflict

**4 locations define `.toolbar`** with conflicting properties:

| Location | File | Key Properties |
|----------|------|---------------|
| Global | `src/styles/_meta-table.scss:146` | `padding: var(--spacing-sm) 0`, `border-bottom: 1px solid` |
| Scoped | `src/components/common/MetaListPage/MetaListPage.vue:1514` | `padding: var(--spacing-sm) var(--spacing-md)`, `border-radius`, no border-bottom |
| Scoped (compact) | `MetaListPage.vue:1764` | `padding: var(--spacing-xs) **0**` |
| Other | `src/components/MermaidComponent.css:23` | Unrelated |

**Conflict points**:
1. Horizontal padding: global = `0`, scoped = `var(--spacing-md)` → inconsistent across render contexts
2. Border: global has `border-bottom`, scoped uses `border-radius` → appear/disappear on mode switch
3. Compact mode padding = `0` horizontally → visual jump when entering/exiting compact mode

### Secondary Causes

| Cause | Mechanism | Fix Applied |
|-------|-----------|-------------|
| `flex-wrap: wrap` | Content wraps → height changes → drift | Changed to `nowrap` + `overflow-x: auto` |
| No `min-height` | Height collapses when content shrinks | Added `min-height: 44px` |
| Missing `position: relative` | Child elements may shift positioning context | Added to `.toolbar` |
| EP default `.el-button + .el-button { margin-left: 12px }` | Stacks with `gap: 4px` → inconsistent spacing | Overridden with `:deep()` selector |

### Why It Keeps Coming Back

1. **Multiple CSS sources**: Each fix only addresses one layer, other layers reintroduce the conflict
2. **Mode switching**: Normal ↔ Compact ↔ Embedded modes each have different padding values
3. **Dynamic content**: Batch action area (`selection-info-wrapper`) appears/disappears → content width changes
4. **EP defaults**: Element Plus injects styles that are hard to fully override

---

## Fixes Applied (2026-06-09)

### Fix 1: Unify Global Base Styles (`_meta-table.scss`)
```css
/* Before: conflicting padding/border */
.toolbar {
  padding: var(--spacing-sm) 0;        /* conflicts with scoped */
  border-bottom: 1px solid ...;         /* conflicts with scoped */
}

/* After: minimal base, let scoped override fully */
.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: nowrap;
  min-height: 44px;
}
```

### Fix 2: Compact Mode Padding Consistency (`MetaListPage.vue`)
```css
/* Before: horizontal padding = 0, causes jump */
.toolbar { padding: var(--spacing-xs) 0; }

/* After: keep horizontal padding consistent */
.toolbar { padding: var(--spacing-xs) var(--spacing-sm); }
```

### Fix 3: Lock Positioning Context (`MetaListPage.vue`)
```css
.toolbar {
  /* ... existing properties ... */
  position: relative; /* Lock positioning context */
}
```

### Fix 4: Override EP Button Margin (`GlobalToolbar.vue`)
```css
.gt-actions {
  gap: 8px;
  :deep(.el-button + .el-button) { margin-left: 0; }
}
.gt-actions .el-button {
  margin: 0; /* Lock against EP/global injection */
  &:hover, &:focus, &:active {
    transform: none; box-shadow: none; /* Prevent jitter */
  }
}
```

---

## Vite Vue Plugin Gotcha

> **CRITICAL**: Vite's Vue plugin CANNOT parse `//` comments inside `<style>` blocks correctly.
> 
> Error: `Unknown word <first-word-after-comment>`
> 
> **Rule**: Never use `//` comments in `<style lang="scss">` blocks. Use `/* */` only, or no comments at all.

---

## Monitoring Checklist

- [ ] Verify user-permission page (GenericTabContainer > GenericObjectList > MetaListPage)
- [ ] Verify archdata page (direct MetaListPage usage)
- [ ] Check compact mode toggle does not cause visual jump
- [ ] Check batch selection appearance/disappearance does not shift toolbar
- [ ] Check narrow viewport (< 768px) behavior
- [ ] Watch for regression after EP version upgrade (EP may change default button margins)

## Prevention Rules for Future Modifications

1. When modifying `.toolbar` styles, check ALL 4 definition locations
2. Never set `padding: X 0` in any mode (keep horizontal padding)
3. Always set `min-height` on toolbars with dynamic content
4. Always override EP sibling selectors (`:deep(.el-button + .el-button)`) in custom toolbars
5. Never use `//` comments in `<style>` blocks of `.vue` files
