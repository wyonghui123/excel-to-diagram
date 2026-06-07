"""
诊断点击 管理员 后的实际 API 请求
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

    # 找所有 th 的 prop - 用 JS 直接读 Vue 组件实例
    info = page.evaluate("""() => {
        const ths = document.querySelectorAll('.el-table__header-wrapper th');
        const out = [];
        for (let i = 0; i < ths.length; i++) {
            const th = ths[i];
            const colEl = th.closest('colgroup') ? null : th;
            // 找 el-table-column 的 instance
            const colId = th.className.match(/el-table_\\d+_column_(\\d+)/);
            out.push({
                index: i,
                label: th.textContent.trim(),
                colId: colId ? colId[1] : null
            });
        }
        return out;
    }""")
    for r in info:
        print(r)

    # 现在通过 prop 找到对应 column
    # column_13 = visibleColumns[3] = manager_id
    # 但 value-help 调了 user_group？奇怪
    # 让我直接看 th[3] 是 父组（"父组"列）的 filter trigger 是否调 user_group
    print('\n=== 点击 父组 th[3] 测试 ===')
    api_requests.clear()
    th3 = page.locator('.el-table__header-wrapper th').nth(3)
    print(f'  th 3 text: {th3.text_content().strip()!r}')
    th3.locator('.filter-trigger').first.click()
    time.sleep(2)
    print('  API after click th 3 (父组):')
    for r in api_requests:
        print(f'    {r["url"][-200:]}')

    print('\n=== 点击 管理员 th[4] 测试 ===')
    api_requests.clear()
    th4 = page.locator('.el-table__header-wrapper th').nth(4)
    th4.locator('.filter-trigger').first.click()
    time.sleep(2)
    print('  API after click th 4 (管理员):')
    for r in api_requests:
        print(f'    {r["url"][-200:]}')

    browser.close()
