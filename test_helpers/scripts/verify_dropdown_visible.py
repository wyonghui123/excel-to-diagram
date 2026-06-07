#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
真实视觉验证：检测 category 下拉框是否真的在视口内可见
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from browser_auth_cli import PlaywrightCLI

OUT_DIR = r"d:\filework\excel-to-diagram\test_results\visual_verify"
os.makedirs(OUT_DIR, exist_ok=True)


def main():
    cli = PlaywrightCLI(headless=True)

    print("=" * 60)
    print("Step 1: dev-login")
    print("=" * 60)
    cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
    cli.wait_for_timeout(1000)
    print("[OK] dev-login done")

    print("=" * 60)
    print("Step 2: Navigate to business object detail")
    print("=" * 60)
    cli.goto("http://localhost:3004/")
    cli.wait_for_timeout(2000)

    cli.evaluate("""
        () => {
            const router = document.querySelector('#app').__vue_app__
                .config.globalProperties.$router
            router.push('/detail/business_object/25')
        }
    """)
    cli.wait_for_timeout(3000)

    if not cli.wait_for_selector("text=添加备注", timeout=15000):
        print("[FAIL] detail page not loaded")
        cli.screenshot(f"{OUT_DIR}/01_no_detail.png")
        return
    print("[OK] detail page loaded")
    cli.screenshot(f"{OUT_DIR}/01_detail.png")

    print("=" * 60)
    print("Step 3: Click '添加备注' to open dialog")
    print("=" * 60)
    cli.click("text=添加备注")
    cli.wait_for_timeout(2000)

    if not cli.wait_for_selector("text=新增备注", timeout=5000):
        print("[FAIL] dialog not opened")
        cli.screenshot(f"{OUT_DIR}/02_no_dialog.png")
        return
    print("[OK] dialog opened")
    cli.screenshot(f"{OUT_DIR}/02_dialog.png")

    page = cli._ensure_browser()

    print("=" * 60)
    print("Step 4: Find category select in dialog")
    print("=" * 60)

    select_info = page.evaluate("""
        () => {
            // Find select inside dialog
            const dialog = document.querySelector('.el-dialog, .app-modal');
            if (!dialog) return { found: false, reason: 'no dialog' };

            const allSelects = dialog.querySelectorAll('.el-select, .el-select-v2');
            const result = {
                found: allSelects.length > 0,
                count: allSelects.length,
                selects: []
            };

            for (const sel of allSelects) {
                const rect = sel.getBoundingClientRect();
                const labelEl = sel.closest('.mf-item, .el-form-item, .ds-item, [class*="item"]');
                let label = '';
                if (labelEl) {
                    const lbl = labelEl.querySelector('label, .mf-label, .ds-label');
                    if (lbl) label = lbl.textContent.trim();
                }
                result.selects.push({
                    label: label,
                    rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) }
                });
            }
            return result;
        }
    """)
    print(f"Select info: {select_info}")

    if not select_info.get('found'):
        print("[FAIL] no select found in dialog")
        page.screenshot(path=f"{OUT_DIR}/03_no_select.png", full_page=True)
        return

    # Tag category select
    page.evaluate("""
        () => {
            const dialog = document.querySelector('.el-dialog, .app-modal');
            const items = dialog.querySelectorAll('.mf-item, .el-form-item, .ds-item, [class*="item"]');
            for (const item of items) {
                const lbl = item.querySelector('label, .mf-label, .ds-label');
                if (lbl && lbl.textContent.trim() === '分类') {
                    const sel = item.querySelector('.el-select, .el-select-v2');
                    if (sel) {
                        sel.setAttribute('data-test-target', 'category-select');
                        return true;
                    }
                }
            }
            // Fallback: tag the first select
            const firstSel = dialog.querySelector('.el-select, .el-select-v2');
            if (firstSel) {
                firstSel.setAttribute('data-test-target', 'category-select');
                return true;
            }
            return false;
        }
    """)

    print("=" * 60)
    print("Step 5: Click category select to open dropdown")
    print("=" * 60)
    result = cli.open_dropdown("[data-test-target='category-select']")
    print(f"open_dropdown result: {result}")
    cli.wait_for_timeout(1500)

    print("=" * 60)
    print("Step 6: Check popper visibility (REAL visual check)")
    print("=" * 60)

    visibility_state = page.evaluate("""
        () => {
            const result = {};
            const poppers = document.querySelectorAll('.el-select-dropdown, .el-popper, [class*="el-select"][class*="dropdown"], [class*="el-select"][class*="popper"]');
            result.totalPoppers = poppers.length;
            result.poppers = [];

            for (const p of poppers) {
                const items = p.querySelectorAll('.el-select-dropdown__item, .el-option');
                if (items.length === 0) continue;

                const rect = p.getBoundingClientRect();
                const style = window.getComputedStyle(p);

                const isInViewport = (
                    rect.x >= 0 && rect.y >= 0 &&
                    rect.x + rect.width <= window.innerWidth &&
                    rect.y + rect.height <= window.innerHeight &&
                    rect.width > 0 && rect.height > 0
                );

                const isRendered = (
                    style.display !== 'none' &&
                    style.visibility !== 'hidden' &&
                    parseFloat(style.opacity) > 0
                );

                const centerX = rect.x + rect.width / 2;
                const centerY = rect.y + rect.height / 2;
                let topElement = null;
                let isObscured = false;
                if (isRendered && isInViewport && rect.width > 0) {
                    topElement = document.elementFromPoint(centerX, centerY);
                    if (topElement) {
                        isObscured = !p.contains(topElement) && !topElement.closest('.el-select-dropdown, .el-popper');
                    }
                }

                result.poppers.push({
                    texts: Array.from(items).map(i => i.textContent.trim()).slice(0, 10),
                    rect: { x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height) },
                    display: style.display,
                    visibility: style.visibility,
                    opacity: style.opacity,
                    zIndex: style.zIndex,
                    position: style.position,
                    inViewport: isInViewport,
                    isRendered: isRendered,
                    isObscured: isObscured,
                    topElementTag: topElement ? topElement.tagName + '.' + String(topElement.className).slice(0, 80) : null
                });
            }

            // Also check body-level popper container
            const popperContainers = document.querySelectorAll('[id*="popper-container"]');
            result.popperContainerCount = popperContainers.length;

            return result;
        }
    """)

    print(f"Total poppers: {visibility_state['totalPoppers']}")
    print(f"Popper containers: {visibility_state.get('popperContainerCount', 0)}")
    print(f"Poppers with items: {len(visibility_state['poppers'])}")
    for i, p in enumerate(visibility_state['poppers']):
        print(f"\n--- Popper {i} ---")
        print(f"  texts: {p['texts']}")
        print(f"  rect: {p['rect']}")
        print(f"  display: {p['display']}, visibility: {p['visibility']}, opacity: {p['opacity']}")
        print(f"  zIndex: {p['zIndex']}, position: {p['position']}")
        print(f"  inViewport: {p['inViewport']}, isRendered: {p['isRendered']}")
        print(f"  isObscured: {p['isObscured']}, topElement: {p['topElementTag']}")

    print("=" * 60)
    print("Step 7: Screenshot")
    print("=" * 60)
    page.screenshot(path=f"{OUT_DIR}/04_after_click.png", full_page=True)
    print(f"Saved: {OUT_DIR}/04_after_click.png")

    visible_dropdowns = [p for p in visibility_state['poppers']
                         if p['inViewport'] and p['isRendered'] and not p['isObscured']]

    print("\n" + "=" * 60)
    print("VERDICT")
    print("=" * 60)
    if visible_dropdowns:
        for p in visible_dropdowns:
            print(f"[OK] VISIBLE dropdown: {p['texts']}")
    else:
        print("[FAIL] NO visible dropdown found in viewport")
        for p in visibility_state['poppers']:
            issues = []
            if not p['inViewport']:
                issues.append(f"off-screen at {p['rect']}")
            if not p['isRendered']:
                issues.append(f"hidden (display={p['display']}, opacity={p['opacity']})")
            if p['isObscured']:
                issues.append(f"obscured by {p['topElementTag']}")
            print(f"  - {p['texts']}: {', '.join(issues) if issues else 'UNKNOWN'}")


if __name__ == "__main__":
    main()
