"""
简单测试 - 截图 + 看是什么页面
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
    page.goto("http://localhost:3004/objects/user-group", wait_until="networkidle")
    time.sleep(5)
    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\list-page.png', full_page=True)
    print('url:', page.url)
    print('title:', page.title())
    print('body text:', page.locator('body').text_content()[:500])

    browser.close()
