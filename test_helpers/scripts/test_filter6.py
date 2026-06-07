"""
测试列表上管理员列过滤 valuehelp - 正确 path /user-permission
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
    time.sleep(5)
    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\user-perm.png', full_page=True)

    # 找用户组管理 tab
    tabs = page.locator('.el-tabs__item, [role="tab"], .sub-nav-tab, .nav-tab, .gtc-tabs li').all()
    print(f'  tabs: {len(tabs)}')
    for t in tabs:
        print(f'    {t.text_content().strip()!r}')

    # 找用户组管理 tab 并点击
    user_group_tab = page.locator('.el-tabs__item:has-text("用户组"), .nav-tab:has-text("用户组"), [class*="tab"]:has-text("用户组")').first
    if user_group_tab.count() > 0:
        user_group_tab.click()
        time.sleep(3)
        page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\ug-tab.png', full_page=True)
        page.wait_for_selector('.el-table', timeout=10000)
        time.sleep(2)

        print('=== headers ===')
        headers = page.locator('.el-table__header-wrapper th').all()
        for i, h in enumerate(headers):
            text = h.text_content().strip()
            print(f'  [{i}] {text!r}')

        # 找管理员列的 filter icon
        admin_th = page.locator('.el-table__header-wrapper th:has-text("管理员")').first
        if admin_th.count() > 0:
            icons = admin_th.locator('i.el-icon, [class*="filter"], .sort-caret').all()
            print(f'  admin icons: {len(icons)}')
            for i, ic in enumerate(icons):
                cls = ic.get_attribute('class') or ''
                print(f'    [{i}] class={cls!r}')

            if icons:
                for ic in icons:
                    cls = ic.get_attribute('class') or ''
                    if 'filter' in cls.lower() or 'el-icon-arrow' in cls.lower():
                        ic.click()
                        time.sleep(2)
                        page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-open.png', full_page=True)

                        # 找搜索 input
                        popper = page.locator('.el-popper:not([style*="display: none"])').first
                        if popper.count() > 0:
                            print(f'  popper text: {popper.text_content()[:300]!r}')

                            # 找 input
                            input_in_popper = popper.locator('.el-input__inner').first
                            if input_in_popper.count() > 0:
                                input_in_popper.fill('管')
                                time.sleep(2)
                                page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)
                        break

    print('\n=== KEY LOGS ===')
    for l in logs:
        if 'VH' in l or 'value-help' in l.lower() or 'loadOptions' in l or 'search' in l.lower():
            print(l)

    browser.close()
