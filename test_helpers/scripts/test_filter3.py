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
    # 试多个 path
    for path in ['/system/user-group-management', '/system/user_group-management', '/list/user_group']:
        page.goto(f"http://localhost:3004{path}", wait_until="networkidle")
        time.sleep(3)
        h1 = page.locator('h1, .page-title, .el-table__header-wrapper').first
        if h1.count() > 0:
            print(f'{path}: {h1.text_content()[:80]!r}')
            break
        else:
            print(f'{path}: no content')

    page.wait_for_selector('.el-table', timeout=10000)
    time.sleep(2)

    print('=== headers ===')
    headers = page.locator('.el-table__header-wrapper th').all()
    for i, h in enumerate(headers):
        text = h.text_content().strip()
        print(f'  [{i}] {text!r}')

    # 找 "管理员" 列的 filter icon
    admin_th = page.locator('.el-table__header-wrapper th:has-text("管理员")').first
    print(f'admin th count: {admin_th.count()}')

    if admin_th.count() > 0:
        # 找 filter trigger (通常 .el-icon 或 .filter-trigger)
        filter_btn = admin_th.locator('.el-icon, [class*="filter"], .filter-trigger').first
        if filter_btn.count() > 0:
            print(f'  filter btn found, clicking...')
            filter_btn.click()
            time.sleep(2)
            page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-open.png', full_page=True)

            # 找 popper (el-table-filter)
            pops = page.locator('.el-popper, .el-table-filter, .el-select__dropdown')
            print(f'  poppers: {pops.count()}')

            # 找 input
            inputs = page.locator('.el-popper .el-input__inner, .el-table-filter .el-input__inner').all()
            print(f'  inputs: {len(inputs)}')

    print('\n=== KEY LOGS ===')
    for l in logs:
        if 'VH' in l or 'search' in l.lower() or 'loadOptions' in l or 'value-help' in l.lower():
            print(l)

    browser.close()
