"""
测试列表上管理员列过滤 valuehelp - 正确 path
"""
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    logs = []
    page.on("console", lambda m: logs.append(f"[{m.type}] {m.text}"))

    page.goto("http://localhost:3004/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
    time.sleep(1)
    page.goto("http://localhost:3004/objects/user-group", wait_until="networkidle")
    page.wait_for_selector('.el-table', timeout=10000)
    time.sleep(3)

    print('=== headers ===')
    headers = page.locator('.el-table__header-wrapper th').all()
    for i, h in enumerate(headers):
        text = h.text_content().strip()
        print(f'  [{i}] {text!r}')

    # 找 "管理员" 列
    admin_th = page.locator('.el-table__header-wrapper th').nth(3)  # 假设第 4 列是管理员
    if admin_th.count() > 0:
        print(f'  admin_th text: {admin_th.text_content().strip()!r}')

    # 找 filter trigger
    admin_filter_icons = page.locator('.el-table__header-wrapper th:has-text("管理员") .filter-trigger').all()
    print(f'  admin filter triggers: {len(admin_filter_icons)}')

    if not admin_filter_icons:
        # 试点击
        admin_th_text = page.locator('.el-table__header-wrapper th:has-text("管理员")').first
        if admin_th_text.count() > 0:
            # 找 .el-icon 或 .caret-wrap
            icons = admin_th_text.locator('i.el-icon, [class*="filter"], .sort-caret').all()
            print(f'  icons: {len(icons)}')
            for i, ic in enumerate(icons):
                cls = ic.get_attribute('class') or ''
                print(f'    [{i}] class={cls!r}')

            if icons:
                # 找 filter icon (不是 sort)
                for ic in icons:
                    cls = ic.get_attribute('class') or ''
                    if 'filter' in cls.lower() or 'el-icon-arrow-down' in cls.lower() or 'el-icon-filter' in cls.lower():
                        ic.click()
                        time.sleep(2)
                        page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-open.png', full_page=True)

                        # 找搜索框
                        popper_input = page.locator('.el-table-filter .el-input__inner, .el-popper .el-input__inner').first
                        if popper_input.count() > 0:
                            popper_input.fill('管')
                            time.sleep(2)
                            page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)

                            # 看 items
                            items = page.locator('.el-table-filter .el-checkbox__label, .el-table-filter li, .el-table-filter .el-select-dropdown__item').all()
                            print(f'  items: {len(items)}')
                            for it in items[:5]:
                                print(f'    {it.text_content().strip()[:60]!r}')
                        break

    print('\n=== KEY LOGS ===')
    for l in logs:
        if 'VH' in l or 'value-help' in l.lower() or 'loadOptions' in l or 'search' in l.lower():
            print(l)

    browser.close()
