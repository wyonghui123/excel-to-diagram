"""
直接 click 可见的 el-select input
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

    # 找 visible 的 el-select input
    visible_input = page.locator('.el-select__input.is-default:visible').first
    print(f'  visible input count: {visible_input.count()}')
    if visible_input.count() > 0:
        visible_input.click()
        time.sleep(1)
        page.keyboard.type('管', delay=200)
        time.sleep(3)

    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)

    opts = page.locator('.el-select-dropdown__item').all()
    print(f'  visible options: {len(opts)}')
    for o in opts[:5]:
        try:
            print(f'    {o.text_content().strip()!r}')
        except:
            pass

    print('\n=== KEY LOGS (last 30) ===')
    for l in logs[-30:]:
        if 'VH' in l or 'value-help' in l.lower() or 'loadOptions' in l or 'remote' in l.lower() or 'handleRemote' in l or 'handleDropdown' in l:
            print(l)

    browser.close()
