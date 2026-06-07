"""
跟踪选择后的 console
"""
import time
from playwright.sync_api import sync_playwright

DEV_LOGIN_URL = 'http://localhost:3004/api/v1/auth/dev-login?username=admin'
USER_GROUP_DETAIL_URL = 'http://localhost:3004/detail/user_group/2'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    logs = []
    page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))

    page.goto(DEV_LOGIN_URL, wait_until='networkidle')
    time.sleep(1)
    page.goto(USER_GROUP_DETAIL_URL, wait_until='networkidle')
    time.sleep(3)
    edit_btn = page.locator('button:has-text("编辑")').first
    edit_btn.click()
    time.sleep(4)

    sel = page.locator('.op-field:has-text("父组") .el-select').first
    sel.click()
    time.sleep(2)
    target = page.locator('.el-select-dropdown__item:has-text("TEST Group 100")').first
    target.click()
    time.sleep(3)

    print('=== CONSOLE LOGS WITH KEY ===')
    for l in logs:
        if 'handleFieldDisplay' in l or 'handleFieldUpdate' in l or 'field-display' in l or 'update:displayValue' in l or 'VH ' in l or 'ValueHelpField' in l or 'resolveDisplay' in l:
            print(l)

    browser.close()
