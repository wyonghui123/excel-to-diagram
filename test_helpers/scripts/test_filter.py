"""
测试列表上管理员列过滤 valuehelp
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
    page.goto("http://localhost:3004/list/user_group", wait_until="networkidle")
    time.sleep(3)

    # 找 "管理员" 列的过滤
    print('=== look for filter header ===')
    headers = page.locator('.el-table-header th').all()
    for i, h in enumerate(headers):
        text = h.text_content().strip()
        print(f'  [{i}] {text}')

    # 找管理员过滤 dropdown
    filter_loc = page.locator('.el-table-header th:has-text("管理员") .filter-trigger, .el-table-header th:has-text("管理员") .el-icon').first
    if filter_loc.count() > 0:
        filter_loc.click()
        time.sleep(2)
        # 截图
        page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-open.png', full_page=True)

        # 找搜索框
        search_input = page.locator('.el-table-filter .el-input__inner, .el-table-filter .filter-input, .el-popper .el-input__inner').first
        if search_input.count() > 0:
            search_input.fill('管理员')
            time.sleep(2)
            page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)

            # 找 dropdown options
            opts = page.locator('.el-table-filter .el-checkbox__label, .el-table-filter .filter-item')
            print(f'  options count: {opts.count()}')
            for i in range(opts.count()):
                print(f'    [{i}] {opts.nth(i).text_content().strip()!r}')

    print('\n=== KEY LOGS ===')
    for l in logs:
        if 'VH' in l or 'search' in l.lower() or 'value-help' in l.lower() or 'loadOptions' in l or 'filter' in l.lower():
            print(l)

    browser.close()
