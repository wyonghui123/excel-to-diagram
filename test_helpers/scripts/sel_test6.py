"""
简化的 e2e 测试
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
    page.goto("http://localhost:3004/detail/user_group/2", wait_until="networkidle")
    time.sleep(3)
    page.locator("button:has-text('编辑')").first.click()
    time.sleep(4)
    sel = page.locator(".op-field:has-text('父组') .el-select").first
    sel.click()
    time.sleep(2)
    page.locator(".el-select-dropdown__item:has-text('TEST Group 100')").first.click()
    time.sleep(3)

    print("=== ALL CONSOLE (last 30) ===")
    for l in logs[-30:]:
        print(l)
    browser.close()
