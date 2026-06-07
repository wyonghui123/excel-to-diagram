"""
诊断 value-help 搜索
"""
import time
import os
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    # 监听所有 API 请求
    api_requests = []
    def on_request(req):
        if 'value-help' in req.url:
            api_requests.append({'method': req.method, 'url': req.url, 'time': time.time()})
    page.on('request', on_request)

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

    # 找 filter popover 中的 select wrapper
    result = page.evaluate("""() => {
        const popovers = document.querySelectorAll('.el-popper.el-popover');
        for (const pop of popovers) {
            const panel = pop.querySelector('.filter-panel');
            if (panel) {
                const sel = pop.querySelector('.el-select');
                if (sel) {
                    const wrapper = sel.querySelector('.el-select__wrapper');
                    if (wrapper) {
                        wrapper.click();
                        return { found: true };
                    }
                }
            }
        }
        return { found: false };
    }""")
    print('Click result:', result)
    time.sleep(2)

    # 输入
    page.keyboard.type('管', delay=200)
    time.sleep(3)

    print('\n=== API REQUESTS ===')
    for r in api_requests:
        print(f'  {r["method"]} {r["url"]}')

    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)

    print('\n=== visible el-select-dropdown items (in any popover) ===')
    opts = page.locator('.el-select-dropdown__item').all()
    print(f'  total: {len(opts)}')
    for o in opts:
        try:
            print(f'    {o.text_content().strip()[:60]!r}')
        except:
            pass

    browser.close()
