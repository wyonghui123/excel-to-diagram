"""
验证成员数列 number_range filter
"""
import time
import os
from playwright.sync_api import sync_playwright

LOG_PATH = r'd:\filework\excel-to-diagram\test_helpers\test_filter20_full.log'
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

    bo_requests = []
    def on_request(req):
        if '/api/v2/bo/user_group' in req.url and 'value-help' not in req.url:
            bo_requests.append({'url': req.url, 'time': time.time()})
            log(f'  [BO req] {req.url}')
    page.on('request', on_request)

    page.goto("http://localhost:3004/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
    time.sleep(1)
    page.goto("http://localhost:3004/user-permission", wait_until="networkidle")
    time.sleep(3)
    page.locator('text=用户组管理').first.click()
    time.sleep(4)
    page.wait_for_selector('.el-table', timeout=10000)
    time.sleep(2)

    # 检查 th 内容
    ths = page.locator('.el-table__header-wrapper th')
    log('=== 检查 th ===')
    for i in range(ths.count()):
        text = ths.nth(i).text_content().strip()
        log(f'  th[{i}]: {text!r}')

    # 找到"成员数"列的 th（th 5）
    member_th = ths.nth(5)
    log(f'\n  member th text: {member_th.text_content()!r}')

    # 点击成员数列的 filter-trigger
    log('\n=== 点击 成员数列 filter-trigger ===')
    api_requests_before = len(bo_requests)
    member_th.locator('.filter-trigger').first.click()
    time.sleep(2)

    # 先检查 popover 实际内容
    log('\n=== Popover 实际内容 ===')
    filter_panels = page.locator('.filter-panel')
    log(f'  filter-panel count: {filter_panels.count()}')
    # 找可见的 panel
    visible_panels = page.locator('.filter-panel:visible')
    log(f'  visible filter-panel count: {visible_panels.count()}')
    for i in range(visible_panels.count()):
        text = visible_panels.nth(i).text_content().strip()[:200]
        log(f'    panel[{i}]: {text!r}')

    # 找 el-input-number
    input_numbers = page.locator('.filter-panel .el-input-number')
    log(f'  el-input-number count: {input_numbers.count()}')
    for i in range(input_numbers.count()):
        bbox = input_numbers.nth(i).bounding_box()
        log(f'    input-number[{i}] bbox: {bbox}')

    # 找 confirm button
    confirm_btns = page.locator('.filter-panel .el-button--primary')
    log(f'  confirm buttons count: {confirm_btns.count()}')
    for i in range(confirm_btns.count()):
        bbox = confirm_btns.nth(i).bounding_box()
        log(f'    confirm[{i}] bbox: {bbox}')

    # 输入最小值
    log('\n=== 输入最小值 1 ===')
    min_input = page.locator('.filter-panel .el-input-number input').first
    min_input.fill('1')
    time.sleep(1)

    # 输入最大值
    log('=== 输入最大值 10 ===')
    max_input = page.locator('.filter-panel .el-input-number input').nth(1)
    max_input.fill('10')
    time.sleep(1)

    # 点击确定
    log('\n=== 点击确定 ===')
    bo_requests.clear()
    confirm_btn = page.locator('.filter-panel:visible .el-button--primary').first
    confirm_btn.click()
    time.sleep(3)

    log('  API requests after confirm:')
    for r in bo_requests:
        log(f'    {r["url"]}')

    # 检查表格行数
    rows = page.locator('.el-table__body tr')
    row_count = rows.count()
    log(f'\n  filtered rows count: {row_count}')
    for i in range(min(row_count, 5)):
        text = rows.nth(i).text_content().strip()
        log(f'    row[{i}]: {text[:150]!r}')

    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter20-numberrange.png', full_page=True)

    browser.close()
log('\n=== DONE ===')
