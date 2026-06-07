"""
测试列表上管理员列过滤 valuehelp - 展开 el-select dropdown
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

    # 找 filter panel 内的 el-select (multiple)
    sel = page.locator('.el-popper .el-select').first
    print(f'  sel count: {sel.count()}')

    # click el-select wrapper 打开 dropdown
    sel_wrapper = sel.locator('.el-select__wrapper').first
    print(f'  wrapper count: {sel_wrapper.count()}')
    if sel_wrapper.count() > 0:
        sel_wrapper.click()
        time.sleep(2)
        page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-opened.png', full_page=True)

        # 现在 dropdown 打开了，找 input
        input_in_dropdown = page.locator('.el-select-dropdown .el-select__input, .el-select-dropdown input.el-select__input').first
        print(f'  input in dropdown: {input_in_dropdown.count()}')
        if input_in_dropdown.count() > 0:
            input_in_dropdown.click()
            time.sleep(1)
            page.keyboard.type('管', delay=100)
            time.sleep(2)
            page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)

            # 看 options
            opts = page.locator('.el-select-dropdown__item, .el-select-dropdown__list .el-option').all()
            print(f'  visible options: {len(opts)}')
            for o in opts[:5]:
                print(f'    {o.text_content().strip()!r}')

    print('\n=== KEY LOGS (last 30) ===')
    for l in logs[-30:]:
        if 'VH' in l or 'value-help' in l.lower() or 'loadOptions' in l or 'remote' in l.lower() or 'handleRemote' in l:
            print(l)

    browser.close()
