"""
诊断点击 th 4 实际
"""
import time
import os
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    api_requests = []
    def on_request(req):
        if 'value-help' in req.url:
            api_requests.append({'method': req.method, 'url': req.url, 'time': time.time()})
    page.on('request', on_request)

    page.goto("http://localhost:3004/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
    time.sleep(1)
    page.goto("http://localhost:3004/user-permission", wait_until="networkidle")
    time.sleep(3)
    page.locator('text=用户组管理').first.click()
    time.sleep(4)
    page.wait_for_selector('.el-table', timeout=10000)
    time.sleep(2)

    # 点击 父组 (th 3)
    print('=== 点击 父组 th[3] ===')
    api_requests.clear()
    th3 = page.locator('.el-table__header-wrapper th').nth(3)
    print(f'  th 3 text: {th3.text_content().strip()!r}')
    th3.locator('.filter-trigger').first.click()
    time.sleep(3)
    print('  API requests:')
    for r in api_requests:
        print(f'    {r["url"][-200:]}')

    # close any popover
    page.keyboard.press('Escape')
    time.sleep(1)

    # 点击 管理员 th 4
    print('\n=== 点击 管理员 th[4] ===')
    api_requests.clear()
    th4 = page.locator('.el-table__header-wrapper th').nth(4)
    print(f'  th 4 text: {th4.text_content().strip()!r}')
    th4.locator('.filter-trigger').first.click()
    time.sleep(3)
    print('  API requests:')
    for r in api_requests:
        print(f'    {r["url"][-200:]}')

    # 输入 1 个字符
    print('\n=== 在 th 4 中输入 1 个字符 ===')
    page.keyboard.type('管', delay=200)
    time.sleep(3)
    print('  API requests:')
    for r in api_requests:
        print(f'    {r["url"][-200:]}')

    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)
    browser.close()
