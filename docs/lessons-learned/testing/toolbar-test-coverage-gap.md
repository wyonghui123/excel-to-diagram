# Test Coverage Gap Analysis: Toolbar Drift & Layout Issues

> **Date**: 2026-06-09
> **Purpose**: Compare reported issues against existing test cases to identify coverage gaps
> **Context**: User reported toolbar drift and button hover spacing issues that recurred multiple times

---

## Issue Summary from This Session

### Issue 1: MetaListPage Toolbar Drift (Recurring 3+ times)

| Attribute | Details |
|-----------|---------|
| **Symptom** | Toolbar position shifts/offsets on pages using MetaListPage |
| **Affected Pages** | user-permission?tab=roles, archdata page, any page with MetaListPage |
| **Trigger Scenarios** | 1) Page load, 2) State changes, 3) Mode switch (Normal ↔ Compact), 4) Batch selection appears/disappears |
| **Root Cause** | 4 `.toolbar` CSS definitions with conflicting padding/border properties |
| **Severity** | Medium (visual, non-blocking) |

### Issue 2: GlobalToolbar Button Spacing Shrinks on Hover

| Attribute | Details |
|-----------|---------|
| **Symptom** | Button spacing visually shrinks when mouse hovers over icon buttons |
| **Affected Pages** | archdata page GlobalToolbar (4 icon buttons) |
| **Trigger Scenarios** | Mouse hover over any button in `.gt-actions` |
| **Root Cause** | Element Plus default `.el-button + .el-button { margin-left: 12px }` stacking with `gap: 4px`, combined with sub-pixel border rendering jitter |
| **Severity** | Low (cosmetic, non-blocking) |

---

## Existing Test Coverage Analysis

### Files Reviewed

| Test File | Coverage | Gap |
|-----------|----------|-----|
| `tests/e2e/audit_log_management.spec.js` | Toolbar visible check | ❌ No layout/stability checks |
| `tests/e2e/test_frontend_sort_user_list.py` | Navigates to user-permission | ❌ Functional test only, no UI checks |
| `tests/e2e/test_relation_scope_fix.py` | Navigates to archdata | ❌ Functional test only, no UI checks |
| `tests/e2e/test_e2e_rss_*.py` | RSS tree visibility | ❌ Focuses on tree, not toolbar |
| `tests/integration/test_overlap_e2e.py` | CSS variable validation | ✅ Only validates CSS variables exist |
| `tests/e2e/diag_*.py` | Page diagnostics | ❌ Diagnostic scripts, not assertions |

### Detailed Gap Analysis

#### 1. Toolbar Visibility vs. Position

| Test | What It Checks | What It Misses |
|------|----------------|----------------|
| `audit_log_management.spec.js:51` | `await expect(toolbar).toBeVisible()` | ❌ Position stability after state change |
| `audit_log_management.spec.js:147` | Button click | ❌ Toolbar layout after action |
| `audit_log_management.spec.js:221` | Export button exists | ❌ Hover state effects |

**Gap Type**: Binary visibility check only. Does NOT verify:
- Toolbar remains at same Y position after data loads
- Toolbar does not shift when batch selection appears
- Toolbar is not offset from expected position

#### 2. Page Navigation vs. Layout Stability

| Test | What It Checks | What It Misses |
|------|----------------|----------------|
| `test_frontend_sort_user_list.py:14` | `page.goto('/user-permission/users')` | ❌ No layout assertions |
| `test_relation_scope_fix.py:121` | `page.goto('/system/archdata')` | ❌ No toolbar position verification |
| `test_e2e_rss_nodes_visible.py:49` | Page load | ❌ No layout stability checks |

**Gap Type**: Functional navigation only. Does NOT verify:
- Toolbar Y position consistency across page loads
- No visual drift compared to baseline

#### 3. CSS Validation vs. Runtime Behavior

| Test | What It Checks | What It Misses |
|------|----------------|----------------|
| `test_overlap_e2e.py:209` | `assertIn("var(--color-", content)` | ❌ CSS variable presence, not runtime values |
| `diag_precise.py:135` | `style.display !== 'none'` | ❌ Display check, not spacing/gap checks |

**Gap Type**: Static CSS validation. Does NOT verify:
- Computed `gap` value on `.gt-actions`
- Computed `margin-left` value on sibling buttons
- Hover state CSS properties

---

## Root Cause: Why These Gaps Exist

### 1. Test Focus: Functional vs. Visual

| Philosophy | What It Tests | Blind Spot |
|------------|---------------|------------|
| **Functional Testing** | Does the feature work? (click, navigate, query) | Does it look correct? (layout, spacing, alignment) |
| **Visual Testing** | Does the UI match spec? (position, color, spacing) | Requires screenshot/visual comparison |

**Current state**: 95% functional tests, 5% visual tests (only CSS variable presence)

### 2. No Regression Tests for CSS Changes

| Scenario | Existing Coverage | Missing |
|----------|-------------------|---------|
| Add new `.toolbar` definition | ❌ No detection | When someone adds conflicting `.toolbar` CSS, no test fails |
| Modify Element Plus version | ❌ No detection | EP default margins may change |
| Change compact mode padding | ❌ No detection | Padding inconsistency not caught |

### 3. No Hover/Interaction State Testing

| Test Type | Coverage | Missing |
|-----------|----------|---------|
| Default state | ✅ Some | - |
| Hover state | ❌ None | `.gt-actions .el-button:hover` spacing |
| Focus/Active state | ❌ None | Focus ring effects on layout |
| Disabled state | ❌ None | Disabled button layout |

### 4. No Layout Stability Tests

| Trigger | Coverage | Missing |
|---------|----------|---------|
| Page load | ✅ Basic | Toolbar Y position baseline |
| Data load complete | ❌ None | Toolbar shifts when data arrives |
| Batch selection toggle | ❌ None | Toolbar moves when selection info appears |
| Mode switch (Normal→Compact) | ❌ None | Padding jump during transition |

---

## Missing Test Scenarios

### Priority 1: Critical (Would Have Caught the Bug)

#### T1: Toolbar Position Stability Test
```javascript
// Pseudocode - would have caught Issue 1
test('toolbar position stable after data load', async ({ page }) => {
  await page.goto('/user-permission/roles');
  const toolbarBefore = await page.locator('.toolbar').boundingBox();
  
  // Trigger data load
  await page.waitForTimeout(2000); // wait for data
  
  const toolbarAfter = await page.locator('.toolbar').boundingBox();
  
  // Verify no drift
  expect(toolbarBefore.y).toBe(toolbarAfter.y);
  expect(toolbarBefore.x).toBe(toolbarAfter.x);
});
```

#### T2: Batch Selection Toolbar Stability Test
```javascript
// Pseudocode - would have caught Issue 1
test('toolbar stable when batch selection appears', async ({ page }) => {
  await page.goto('/system/archdata');
  const toolbarBefore = await page.locator('.toolbar').boundingBox();
  
  // Select multiple rows to trigger batch action
  await page.locator('table tbody tr').first().click();
  await page.keyboard.down('Shift');
  await page.locator('table tbody tr').nth(3).click();
  await page.keyboard.up('Shift');
  
  const toolbarAfter = await page.locator('.toolbar').boundingBox();
  
  // Verify toolbar didn't shift
  expect(toolbarBefore.y).toBe(toolbarAfter.y);
});
```

### Priority 2: High (Visual Quality)

#### T3: GlobalToolbar Button Spacing Test
```javascript
// Pseudocode - would have caught Issue 2
test('button spacing consistent on hover', async ({ page }) => {
  await page.goto('/system/archdata');
  
  const buttons = page.locator('.gt-actions .el-button');
  const buttonCount = await buttons.count();
  
  // Get spacing before hover
  const boxes = await Promise.all(
    Array.from({ length: buttonCount }, (_, i) => buttons.nth(i).boundingBox())
  );
  
  // Check gap between adjacent buttons
  for (let i = 1; i < boxes.length; i++) {
    const gapBefore = boxes[i].x - (boxes[i-1].x + boxes[i-1].width);
    
    // Hover on button
    await buttons.nth(i).hover();
    await page.waitForTimeout(100);
    
    const boxAfterHover = await buttons.nth(i).boundingBox();
    const gapAfter = boxAfterHover.x - (boxes[i-1].x + boxes[i-1].width);
    
    // Gap should not change more than 1px
    expect(Math.abs(gapAfter - gapBefore)).toBeLessThan(1);
  }
});
```

#### T4: Compact Mode Padding Consistency
```javascript
// Pseudocode - would have caught compact mode jump
test('compact mode does not cause layout jump', async ({ page }) => {
  await page.goto('/system/archdata');
  
  // Get toolbar padding before
  const paddingBefore = await page.evaluate(() => {
    const toolbar = document.querySelector('.toolbar');
    const style = window.getComputedStyle(toolbar);
    return {
      left: parseInt(style.paddingLeft),
      right: parseInt(style.paddingRight)
    };
  });
  
  // Toggle compact mode if available
  // ... toggle logic ...
  
  const paddingAfter = await page.evaluate(() => {
    const toolbar = document.querySelector('.toolbar');
    const style = window.getComputedStyle(toolbar);
    return {
      left: parseInt(style.paddingLeft),
      right: parseInt(style.paddingRight)
    };
  });
  
  // Horizontal padding should not be 0 in either mode
  expect(paddingBefore.left).toBeGreaterThan(0);
  expect(paddingAfter.left).toBeGreaterThan(0);
});
```

### Priority 3: Medium (Regression Prevention)

#### T5: CSS Conflict Detection Test
```javascript
// Pseudocode - detects multiple .toolbar definitions
test('no conflicting .toolbar CSS definitions', async ({ page }) => {
  const styles = await page.evaluate(() => {
    const sheets = document.styleSheets;
    const toolbarRules = [];
    
    for (const sheet of sheets) {
      try {
        for (const rule of sheet.cssRules) {
          if (rule.selectorText && rule.selectorText.includes('.toolbar')) {
            toolbarRules.push({
              selector: rule.selectorText,
              file: sheet.href || 'inline',
              hasPadding: rule.style.padding !== '',
              hasBorderBottom: rule.style.borderBottom !== '',
              hasBorderRadius: rule.style.borderRadius !== ''
            });
          }
        }
      } catch (e) { /* cross-origin */ }
    }
    return toolbarRules;
  });
  
  // Check for conflicting properties
  const withPadding = styles.filter(r => r.hasPadding && r.hasPadding.includes('0'));
  const withBorder = styles.filter(r => r.hasBorderBottom);
  const withRadius = styles.filter(r => r.hasBorderRadius);
  
  // Multiple definitions with conflicting properties = potential drift
  const hasConflict = (withPadding.length > 0 && withBorder.length > 0) ||
                      (withPadding.length > 1);
  
  if (hasConflict) {
    console.log('Conflicting .toolbar definitions detected:', styles);
  }
  
  expect(hasConflict).toBe(false);
});
```

---

## Recommended Test Strategy

### Short-term (Add Visual Assertions)

1. **Add layout stability checks** to existing E2E tests:
   - Before: `await page.goto('/user-permission/roles')`
   - After: Verify toolbar position, then proceed with functional test

2. **Add hover state checks** for GlobalToolbar:
   - Verify computed styles don't change unexpectedly

### Medium-term (Visual Regression Suite)

1. **Screenshot comparison** for critical pages:
   - Capture baseline screenshots
   - Compare after CSS changes
   - Use tools like `playwright-visual-regression` or `argos-ci`

2. **Layout snapshot tests**:
   - Store bounding box positions as JSON
   - Compare against baseline
   - Fail CI if drift detected

### Long-term (CSS Governance)

1. **CSS linting rules**:
   - Warn on multiple `.toolbar` definitions
   - Enforce consistent padding/border patterns

2. **Design system enforcement**:
   - CSS custom properties for spacing
   - No ad-hoc padding values
   - Token-based design system

---

## Summary Table

| Issue | Would Have Been Caught By | Current Coverage |
|-------|---------------------------|------------------|
| Toolbar drift on page load | T1: Position stability test | ❌ No |
| Toolbar drift when batch selection appears | T2: Batch selection stability test | ❌ No |
| Button spacing shrinks on hover | T3: Hover spacing test | ❌ No |
| Compact mode padding jump | T4: Padding consistency test | ❌ No |
| CSS conflict from multiple definitions | T5: CSS conflict detection | ❌ No |

**Conclusion**: All 5 scenarios lack test coverage. The bugs recurred because there are no visual/layout regression tests. Only functional behavior is tested, not UI stability.
