"""
完整测试列表上管理员列过滤 valuehelp
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

    # 点击"用户组管理" tab
    page.locator('text=用户组管理').first.click()
    time.sleep(4)
    page.wait_for_selector('.el-table', timeout=10000)
    time.sleep(2)

    # 找管理员列的 filter trigger
    admin_th = page.locator('.el-table__header-wrapper th:has-text("管理员")').first
    if admin_th.count() > 0:
        # 找 .filter-trigger (.el-tooltip__trigger 是同一个)
        filter_trigger = admin_th.locator('.filter-trigger').first
        print(f'  filter trigger count: {filter_trigger.count()}')
        if filter_trigger.count() > 0:
            filter_trigger.click()
            time.sleep(3)
            page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-open.png', full_page=True)

            # 找 filter panel 中的 el-select input
            filter_input = page.locator('.el-popper .el-select .el-input__inner, .el-popper .el-select__input').first
            if filter_input.count() > 0:
                print(f'  found filter input, typing "管"...')
                filter_input.click()
                time.sleep(1)
                filter_input.fill('管')
                time.sleep(3)
                page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)

                # 看 dropdown options
                opts = page.locator('.el-select-dropdown__item, .el-select-dropdown__list .el-option').all()
                print(f'  visible options: {len(opts)}')
                for o in opts[:5]:
                    print(f'    {o.text_content().strip()!r}')

    print('\n=== KEY LOGS (last 30) ===')
    for l in logs[-30:]:
        if 'VH' in l or 'value-help' in l.lower() or 'loadOptions' in l or 'search' in l.lower() or 'resolveDisplay' in l:
            print(l)

    browser.close()
