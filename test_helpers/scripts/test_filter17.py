"""
验证列表上"管理员"列 ValueHelp 过滤搜索修复 v2
"""
import time
import os
from playwright.sync_api import sync_playwright

LOG_PATH = r'd:\filework\excel-to-diagram\test_helpers\test_filter17_full.log'
log_lines = []
def log(msg):
    print(msg)
    log_lines.append(str(msg))
    try:
        with open(LOG_PATH, 'w', encoding='utf-8') as f:
            f.write('\n'.join(log_lines))
    except Exception:
        pass

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    api_requests = []
    def on_request(req):
        if 'value-help' in req.url:
            api_requests.append({'method': req.method, 'url': req.url, 'time': time.time()})
            log(f'  [VALUE-HELP request] {req.url}')
        elif '/api/' in req.url:
            log(f'  [other api] {req.url[-200:]}')
    page.on('request', on_request)

    page.on('console', lambda msg: log(f'  [console.{msg.type}] {msg.text[:300]}'))
    page.on('pageerror', lambda err: log(f'  [pageerror] {str(err)[:300]}'))

    page.goto("http://localhost:3004/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
    time.sleep(1)
    page.goto("http://localhost:3004/user-permission?nocache=" + str(int(time.time())), wait_until="networkidle")
    time.sleep(3)
    page.locator('text=用户组管理').first.click()
    time.sleep(4)
    page.wait_for_selector('.el-table', timeout=10000)
    time.sleep(2)

    ths = page.locator('.el-table__header-wrapper th')

    # 点击"管理员"列过滤
    log('=== 点击 管理员列 th[4] filter-trigger ===')
    api_requests.clear()
    th4 = ths.nth(4)
    th4.locator('.filter-trigger').first.click()
    time.sleep(3)

    log('  API requests after open:')
    for r in api_requests:
        log(f'    {r["url"]}')

    # 找到 filter-panel 内的 .el-select__wrapper（visible 部分）
    wrappers = page.locator('.filter-panel .el-select__wrapper, .filter-panel .el-select')
    log(f'\n  filter-panel el-select wrappers: {wrappers.count()}')
    for i in range(wrappers.count()):
        el = wrappers.nth(i)
        bbox = el.bounding_box()
        log(f'    wrapper[{i}] bbox: {bbox}')

    # 点击 wrapper 打开 dropdown
    log('\n=== 点击 .el-select__wrapper 打开 dropdown ===')
    api_requests.clear()
    # wrapper[0]/[1] 是 hidden v-if 内的（parent_id 列 filter panel），wrapper[2]/[3] 是 visible 的 manager_id
    target = page.locator('.filter-panel .el-select__wrapper:visible').first
    target.click()
    time.sleep(3)
    log('  API requests after click wrapper:')
    for r in api_requests:
        log(f'    {r["url"]}')

    # 检查 dropdown 状态
    expanded = page.locator('.el-select .el-select__wrapper[aria-expanded="true"], .el-select__wrapper.is-focused').count()
    log(f'  expanded wrappers: {expanded}')

    visible_dropdown = page.locator('.el-select-dropdown:visible').count()
    log(f'  visible select dropdowns: {visible_dropdown}')

    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter17-3-wrapper-clicked.png', full_page=True)

    # 找到 dropdown 中的 options
    options = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
    opt_count = options.count()
    log(f'\n  dropdown option count: {opt_count}')
    for i in range(min(opt_count, 10)):
        text = options.nth(i).text_content().strip()
        log(f'    option[{i}]: {text!r}')

    # 现在输入"管"
    log('\n=== 输入"管" ===')
    api_requests.clear()
    page.keyboard.type('管', delay=200)
    time.sleep(2)
    log('  API requests after type:')
    for r in api_requests:
        log(f'    {r["url"]}')

    # 再次检查 options
    options = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
    opt_count2 = options.count()
    log(f'\n  dropdown option count after type: {opt_count2}')
    for i in range(min(opt_count2, 10)):
        text = options.nth(i).text_content().strip()
        log(f'    option[{i}]: {text!r}')

    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter17-4-typed.png', full_page=True)

    # 关闭 popover
    page.keyboard.press('Escape')
    time.sleep(1)

    browser.close()
log('\n=== DONE ===')
