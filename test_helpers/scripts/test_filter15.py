"""
测试 manager_id (index 4) 过滤
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

    # 管理员 = index 4
    admin_th = page.locator('.el-table__header-wrapper th').nth(4)
    print(f'  admin th text: {admin_th.text_content().strip()!r}')

    filter_trigger = admin_th.locator('.filter-trigger').first
    print(f'  filter trigger count: {filter_trigger.count()}')
    filter_trigger.click()
    time.sleep(3)

    page.evaluate("""() => {
        const popovers = document.querySelectorAll('.el-popper.el-popover');
        for (const pop of popovers) {
            const panel = pop.querySelector('.filter-panel');
            if (panel) {
                const sel = pop.querySelector('.el-select');
                if (sel) {
                    const wrapper = sel.querySelector('.el-select__wrapper');
                    if (wrapper) {
                        wrapper.click();
                        return true;
                    }
                }
            }
        }
        return false;
    }""")
    time.sleep(2)

    page.keyboard.type('管', delay=200)
    time.sleep(3)

    print('\n=== API REQUESTS ===')
    for r in api_requests:
        print(f'  {r["method"]} {r["url"][-200:]}')

    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-manager.png', full_page=True)

    opts = page.locator('.el-select-dropdown__item').all()
    print(f'\n  total options: {len(opts)}')
    for o in opts:
        try:
            print(f'    {o.text_content().strip()[:60]!r}')
        except:
            pass

    browser.close()
