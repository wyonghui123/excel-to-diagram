"""
完整测试列表上管理员列过滤 valuehelp - focus + type
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

    # 找 el-select 的 input (visible)
    sel_input = page.locator('.el-popper .el-select__wrapper.is-filterable input.el-select__input, .el-popper .el-select input').first
    print(f'  sel input count: {sel_input.count()}')

    # 直接 focus + type
    popper = page.locator('.el-popper .el-select').first
    popper_box = popper.bounding_box()
    if popper_box:
        print(f'  popper box: {popper_box}')
        # 找到 input 的位置 (大致在 popper 内部)
        # 点击 popper 内空白处，然后 type
        page.mouse.click(popper_box['x'] + popper_box['width']/2, popper_box['y'] + popper_box['height'] - 30)
        time.sleep(1)
        page.keyboard.type('管', delay=100)
        time.sleep(2)

    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)

    # 看 dropdown options
    opts = page.locator('.el-select-dropdown__item, .el-select-dropdown__list .el-option').all()
    print(f'  visible options: {len(opts)}')
    for o in opts[:5]:
        try:
            print(f'    {o.text_content().strip()!r}')
        except:
            pass

    print('\n=== KEY LOGS (last 20) ===')
    for l in logs[-20:]:
        if 'VH' in l or 'value-help' in l.lower() or 'loadOptions' in l or 'remote' in l.lower():
            print(l)

    browser.close()
