"""
验证本地 filterable：输入 "xxx" 应过滤到 0 个，输入 "管" 应保留 1 个
"""
import time
import os
from playwright.sync_api import sync_playwright

LOG_PATH = r'd:\filework\excel-to-diagram\test_helpers\test_filter18_full.log'
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
            log(f'  [VH req] {req.url[:200]}')
    page.on('request', on_request)

    page.goto("http://localhost:3004/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
    time.sleep(1)
    page.goto("http://localhost:3004/user-permission", wait_until="networkidle")
    time.sleep(3)
    page.locator('text=用户组管理').first.click()
    time.sleep(4)
    page.wait_for_selector('.el-table', timeout=10000)
    time.sleep(2)

    # 点击 th 4 (管理员) filter
    ths = page.locator('.el-table__header-wrapper th')
    ths.nth(4).locator('.filter-trigger').first.click()
    time.sleep(3)

    # 等待预加载完成
    time.sleep(2)

    # 点击 el-select__wrapper:visible 打开 dropdown
    target = page.locator('.filter-panel .el-select__wrapper:visible').first
    target.click()
    time.sleep(2)

    # 检查 dropdown options
    log('\n=== Dropdown 初始选项 ===')
    options = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
    opt_count = options.count()
    log(f'  option count: {opt_count}')
    for i in range(min(opt_count, 10)):
        text = options.nth(i).text_content().strip()
        log(f'    option[{i}]: {text!r}')

    # 输入 "xxx"（不存在的关键词）
    log('\n=== 输入 "xxx" ===')
    api_requests.clear()
    page.keyboard.type('xxx', delay=200)
    time.sleep(2)
    log('  API requests:')
    for r in api_requests:
        log(f'    {r["url"][:200]}')

    options = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
    opt_count2 = options.count()
    log(f'  option count after "xxx": {opt_count2}')

    # 清空输入（按 Backspace 3 次）
    log('\n=== 清空输入 ===')
    for _ in range(3):
        page.keyboard.press('Backspace')
    time.sleep(1)

    options = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
    opt_count3 = options.count()
    log(f'  option count after clear: {opt_count3}')

    # 输入 "管"
    log('\n=== 输入 "管" ===')
    api_requests.clear()
    page.keyboard.type('管', delay=200)
    time.sleep(2)
    log('  API requests:')
    for r in api_requests:
        log(f'    {r["url"][:200]}')

    options = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
    opt_count4 = options.count()
    log(f'  option count after "管": {opt_count4}')
    for i in range(min(opt_count4, 10)):
        text = options.nth(i).text_content().strip()
        log(f'    option[{i}]: {text!r}')

    # 选择第一个匹配项
    if opt_count4 > 0:
        options.first.click()
        time.sleep(1)
        log('  [DECORATIVE] 点击第一个选项')

        # 点击确定
        confirm = page.locator('.filter-panel .el-button--primary').first
        confirm.click()
        time.sleep(2)
        log('  [DECORATIVE] 点击确定')

        # 验证表格行被过滤
        rows = page.locator('.el-table__body tr')
        log(f'  filtered rows count: {rows.count()}')
        for i in range(min(rows.count(), 5)):
            text = rows.nth(i).text_content().strip()
            log(f'    row[{i}]: {text[:100]!r}')

    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter18-final.png', full_page=True)
    browser.close()
log('\n=== DONE ===')
