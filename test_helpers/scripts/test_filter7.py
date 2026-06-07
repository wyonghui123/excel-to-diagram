"""
测试用户组管理 tab 下的列表过滤
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

    # 找"用户组管理" tab 并点击
    user_group_tab = page.locator('text=用户组管理').first
    if user_group_tab.count() > 0:
        print('  click user group tab')
        user_group_tab.click()
        time.sleep(4)
        page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\ug-tab.png', full_page=True)
        page.wait_for_selector('.el-table', timeout=10000)
        time.sleep(2)

        print('=== headers ===')
        headers = page.locator('.el-table__header-wrapper th').all()
        for i, h in enumerate(headers):
            text = h.text_content().strip()
            print(f'  [{i}] {text!r}')

        # 找管理员列
        admin_th = page.locator('.el-table__header-wrapper th:has-text("管理员")').first
        if admin_th.count() > 0:
            # 找 filter icon
            icons = admin_th.locator('i, [class*="filter"]').all()
            print(f'  admin icons: {len(icons)}')
            for i, ic in enumerate(icons):
                cls = ic.get_attribute('class') or ''
                print(f'    [{i}] class={cls!r}')

            # 找 .caret-wrap (el-table 的 filter icon)
            carets = admin_th.locator('.caret-wrapper, .filter-trigger, [class*="caret"]').all()
            print(f'  admin carets: {len(carets)}')
            for i, c in enumerate(carets):
                cls = c.get_attribute('class') or ''
                print(f'    caret [{i}] class={cls!r}')

            if carets:
                carets[0].click()
                time.sleep(2)
                page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-open.png', full_page=True)

                # 找 popper
                popper = page.locator('.el-table-filter, .el-popper').first
                if popper.count() > 0:
                    print(f'  popper text: {popper.text_content()[:300]!r}')

                    # 找 input
                    input_in_popper = popper.locator('.el-input__inner').first
                    if input_in_popper.count() > 0:
                        input_in_popper.fill('管')
                        time.sleep(2)
                        page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)

    print('\n=== KEY LOGS (last 30) ===')
    for l in logs[-30:]:
        if 'VH' in l or 'value-help' in l.lower() or 'loadOptions' in l or 'search' in l.lower() or 'filter' in l.lower():
            print(l)

    browser.close()
