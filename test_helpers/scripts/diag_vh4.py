"""
诊断 th 4 实际绑定的 column
"""
import time
import os
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    page.goto("http://localhost:3004/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
    time.sleep(1)
    page.goto("http://localhost:3004/user-permission", wait_until="networkidle")
    time.sleep(3)
    page.locator('text=用户组管理').first.click()
    time.sleep(4)
    page.wait_for_selector('.el-table', timeout=10000)
    time.sleep(2)

    # 找所有 th 的 prop
    ths = page.locator('.el-table__header-wrapper th').all()
    print('=== THs ===')
    for i, th in enumerate(ths):
        try:
            cls = th.get_attribute('class') or ''
            label = th.text_content().strip()
            # 找 inner data prop
            prop = th.get_attribute('data-prop') or ''
            print(f'  [{i}] label={label!r}, data-prop={prop!r}, class={cls[:50]!r}')
        except:
            pass

    browser.close()
