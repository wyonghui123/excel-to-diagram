"""
找到正确的 dialog 容器并打开下拉框
"""
import sys
import os
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from playwright.sync_api import sync_playwright

def main():
    out_dir = "d:/filework/excel-to-diagram/test_results"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()

        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        page.wait_for_timeout(1500)
        page.goto("http://localhost:3004/")
        page.wait_for_timeout(3000)
        page.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/detail/business_object/25');
            }
        """)
        page.wait_for_timeout(5000)
        page.click("text=添加备注")
        page.wait_for_timeout(3000)

        # 探测 dialog 真实结构
        dialog_info = page.evaluate("""
            () => {
                // 找所有看起来像 dialog 的元素
                const candidates = [
                    '.el-dialog',
                    '.el-modal',
                    '.app-modal',
                    '.app-dialog',
                    '.modal',
                    '[role="dialog"]',
                    '.dialog'
                ];
                const found = {};
                for (const sel of candidates) {
                    const els = document.querySelectorAll(sel);
                    if (els.length > 0) {
                        found[sel] = Array.from(els).map(e => ({
                            tag: e.tagName,
                            className: e.className,
                            visible: window.getComputedStyle(e).display !== 'none'
                        }));
                    }
                }

                // 找所有包含 "重要" 的 select-like 元素
                const allSelects = document.querySelectorAll('.el-select, .el-input, select, [class*="select"], [class*="Select"]');
                const selectInfo = Array.from(allSelects).slice(0, 10).map(e => ({
                    tag: e.tagName,
                    className: e.className,
                    text: (e.textContent || '').substring(0, 50)
                }));

                return { found, selectInfo: selectInfo.slice(0, 20) };
            }
        """)
        print("Dialog candidates found:")
        for sel, items in dialog_info.get('found', {}).items():
            print(f"  {sel}: {len(items)}")
            for item in items:
                print(f"    {item}")
        print(f"\nAll select-like elements ({len(dialog_info['selectInfo'])}):")
        for s in dialog_info['selectInfo']:
            print(f"  {s}")

        # 直接定位 包含 "重要" 的 select
        important_select = page.locator(".el-select:has-text('重要')").first
        print(f"\nImportant select count: {page.locator('.el-select:has-text(\"重要\")').count()}")
        print(f"Important select visible: {important_select.is_visible() if important_select.count() > 0 else 'N/A'}")

        # 截图初始状态
        page.screenshot(path=f"{out_dir}/debug_01_before.png")
        print(f"Saved: debug_01_before.png")

        # 点击
        important_select.click()
        page.wait_for_timeout(2000)
        page.screenshot(path=f"{out_dir}/debug_02_after_click.png")
        print(f"Saved: debug_02_after_click.png")

        # 检查 dropdowns
        dropdowns = page.evaluate("""
            () => {
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                return Array.from(dropdowns).map(dd => {
                    const style = window.getComputedStyle(dd);
                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    return {
                        display: style.display,
                        visibility: style.visibility,
                        zIndex: style.zIndex,
                        count: items.length,
                        texts: Array.from(items).map(i => i.textContent.trim())
                    };
                });
            }
        """)
        print(f"\nAll dropdowns ({len(dropdowns)}):")
        for i, dd in enumerate(dropdowns):
            is_open = dd['display'] != 'none' and dd['visibility'] != 'hidden'
            print(f"  Dropdown #{i}: display={dd['display']}, items={dd['count']}, visible={is_open}")
            for txt in dd['texts']:
                hex_codes = ' '.join(f'U+{ord(c):04X}' for c in txt)
                print(f"    '{txt}' -> {hex_codes}")

        browser.close()

if __name__ == "__main__":
    main()
