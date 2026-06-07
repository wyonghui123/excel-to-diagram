"""
精确找 filter panel 内的 input
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

    # 找所有 .el-popper
    poppers = page.locator('.el-popper').all()
    print(f'  poppers count: {len(poppers)}')
    for i, p in enumerate(poppers):
        try:
            cls = p.get_attribute('class') or ''
            visible = p.is_visible()
            print(f'    [{i}] class={cls[:80]!r}, visible={visible}')
        except:
            pass

    # filter panel 应该是 el-popper 中含有 .filter-panel 的
    filter_popper = page.locator('.el-popper:has(.filter-panel)').first
    print(f'\n  filter popper count: {filter_popper.count()}, visible: {filter_popper.is_visible()}')

    if filter_popper.count() > 0:
        panel_input = filter_popper.locator('.el-select__input').first
        print(f'  panel input count: {panel_input.count()}, visible: {panel_input.is_visible()}')

        if panel_input.count() > 0:
            try:
                panel_input.click(force=True)
                time.sleep(1)
                page.keyboard.type('管', delay=200)
                time.sleep(3)
            except Exception as e:
                print(f'  click error: {e}')

    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)

    opts = page.locator('.el-select-dropdown__item').all()
    print(f'\n  visible options: {len(opts)}')
    for o in opts[:10]:
        try:
            print(f'    {o.text_content().strip()!r}')
        except:
            pass

    print('\n=== KEY LOGS (last 30) ===')
    for l in logs[-30:]:
        if 'VH' in l or 'value-help' in l.lower() or 'loadOptions' in l or 'remote' in l.lower() or 'handleRemote' in l or 'handleDropdown' in l:
            print(l)

    browser.close()
