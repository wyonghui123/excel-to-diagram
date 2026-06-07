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
    time.sleep(5)
    page.wait_for_selector('.el-table', timeout=10000)
    time.sleep(2)

    print('=== headers ===')
    headers = page.locator('.el-table__header-wrapper th').all()
    for i, h in enumerate(headers):
        text = h.text_content().strip()
        print(f'  [{i}] {text!r}')

    # 找 "管理员" 列的 filter-trigger
    admin_header = page.locator('.el-table__header-wrapper th:has-text("管理员")').first
    if admin_header.count() > 0:
        print('  found admin header')
        # 找 filter icon
        filter_icons = admin_header.locator('.filter-trigger, .el-icon, [class*="filter"]').all()
        for i, ic in enumerate(filter_icons):
            cls = ic.get_attribute('class') or ''
            print(f'  filter icon [{i}]: class={cls!r}')

        # 试点击
        if filter_icons:
            filter_icons[0].click()
            time.sleep(2)
            page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-open.png', full_page=True)

            # 找 popper
            popper = page.locator('.el-table-filter, .el-popper, .filter-dropdown')
            print(f'  poppers count: {popper.count()}')
            for i in range(popper.count()):
                txt = popper.nth(i).text_content().strip()[:200]
                print(f'  popper [{i}]: {txt!r}')

    print('\n=== KEY LOGS (last 30) ===')
    for l in logs[-30:]:
        print(l)

    browser.close()
