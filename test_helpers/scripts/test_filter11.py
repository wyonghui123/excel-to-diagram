"""
直接通过 el-select 的 input 测试
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

    # 找 .el-popper 内的所有 input
    inputs_in_panel = page.locator('.el-popper .el-input__inner, .el-popper .el-select__input, .el-popper input').all()
    print(f'  inputs in popper: {len(inputs_in_panel)}')
    for i, inp in enumerate(inputs_in_panel):
        try:
            visible = inp.is_visible()
            cls = inp.get_attribute('class') or ''
            print(f'    [{i}] visible={visible}, class={cls[:60]!r}')
        except:
            pass

    # 找 filter panel 容器
    panel = page.locator('.el-popper .filter-panel').first
    if panel.count() > 0:
        print(f'  panel visible: {panel.is_visible()}')
        # 找 panel 内部 input
        panel_input = panel.locator('input').first
        if panel_input.count() > 0:
            print(f'  panel input visible: {panel_input.is_visible()}')

    # 用 JS 直接设置值
    print('\n=== Trying direct JS focus + type ===')
    page.evaluate("""() => {
        const panel = document.querySelector('.el-popper .filter-panel');
        if (panel) {
            const inp = panel.querySelector('input');
            if (inp) {
                inp.focus();
                return { found: true, tag: inp.tagName, type: inp.type, class: inp.className };
            }
        }
        return { found: false };
    }""")
    page.keyboard.type('管', delay=200)
    time.sleep(3)

    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)

    # 看 dropdown options
    opts = page.locator('.el-select-dropdown__item').all()
    print(f'  visible options: {len(opts)}')
    for o in opts[:5]:
        try:
            print(f'    {o.text_content().strip()!r}')
        except:
            pass

    print('\n=== KEY LOGS (last 20) ===')
    for l in logs[-20:]:
        if 'VH' in l or 'value-help' in l.lower() or 'loadOptions' in l or 'remote' in l.lower() or 'handleRemote' in l:
            print(l)

    browser.close()
