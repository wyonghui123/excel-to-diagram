"""
强制 click filter panel 的 input
"""
import time
import os
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    logs = []
    page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))

    page.goto("http://localhost:3004/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
    time.sleep(1)
    page.goto("http://localhost:3004/user-permission", wait_until="networkidle")
    time.sleep(3)
    page.locator('text=用户组管理').first.click()
    time.sleep(4)
    page.wait_for_selector('.el-table', timeout=10000)
    time.sleep(2)

    admin_th = page.locator('.el-table__header-wrapper th:has-text("管理员")').first
    filter_trigger = admin_th.locator('.filter-trigger').first
    filter_trigger.click()
    time.sleep(3)

    # 用 JS 找到 filter popover 内的 el-select input
    result = page.evaluate("""() => {
        // 找 filter-popover
        const popovers = document.querySelectorAll('.el-popper.el-popover');
        for (const pop of popovers) {
            const panel = pop.querySelector('.filter-panel');
            if (panel) {
                const inputs = pop.querySelectorAll('.el-select__input');
                for (const inp of inputs) {
                    inp.focus();
                    inp.click();
                    return { found: true, popoverClass: pop.className, inputId: inp.id };
                }
            }
        }
        return { found: false };
    }""")
    print('JS result:', result)
    time.sleep(1)
    page.keyboard.type('管', delay=200)
    time.sleep(3)

    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)

    # 看 value-help 的 dropdown
    opts = page.locator('.el-select__popper .el-select-dropdown__item').all()
    print(f'  visible options: {len(opts)}')
    for o in opts[:10]:
        try:
            print(f'    {o.text_content().strip()!r}')
        except:
            pass

    print('\n=== KEY LOGS ===')
    for l in logs:
        if 'VH' in l or 'value-help' in l.lower() or 'loadOptions' in l or 'remote' in l.lower() or 'handleRemote' in l or 'handleDropdown' in l or 'Search' in l:
            print(l)

    browser.close()
