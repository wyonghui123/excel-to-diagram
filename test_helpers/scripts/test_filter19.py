"""
复现编辑态下父组 valuehelp 只显示当前值的问题
"""
import time
import os
from playwright.sync_api import sync_playwright

LOG_PATH = r'd:\filework\excel-to-diagram\test_helpers\test_filter19_full.log'
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

    page.on('console', lambda msg: log(f'  [console.{msg.type}] {msg.text[:300]}') if 'VHF' in msg.text or 'useValueHelp' in msg.text else None)
    page.on('pageerror', lambda err: log(f'  [pageerror] {str(err)[:300]}'))

    page.goto("http://localhost:3004/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
    time.sleep(1)
    page.goto("http://localhost:3004/user-permission", wait_until="networkidle")
    time.sleep(3)
    page.locator('text=用户组管理').first.click()
    time.sleep(4)
    page.wait_for_selector('.el-table', timeout=10000)
    time.sleep(2)

    # 找一行有"父组"或"管理员"的数据，点击编辑
    log('=== 找一行数据并点击编辑 ===')
    rows = page.locator('.el-table__body tr')
    log(f'  rows count: {rows.count()}')
    # 找第一行的"编辑"按钮
    first_row = rows.first
    log(f'  first row text: {first_row.text_content()[:200]!r}')

    # 点击"编辑"按钮（不同的行有不同的按钮，可能是文字"编辑"或者图标）
    edit_btns = page.locator('button:has-text("编辑"), .el-button:has-text("编辑")')
    log(f'  edit btns: {edit_btns.count()}')
    # 检查所有 .el-table__body 内的 row-action 按钮
    all_row_btns = first_row.locator('button')
    log(f'  first row buttons: {all_row_btns.count()}')
    for i in range(all_row_btns.count()):
        text = all_row_btns.nth(i).text_content().strip() or all_row_btns.nth(i).get_attribute('aria-label') or all_row_btns.nth(i).get_attribute('title') or '?'
        log(f'    btn[{i}]: {text!r}')

    if edit_btns.count() > 0:
        edit_btns.first.click()
    else:
        # 找业务键（"组编码"列）的链接 bk-link
        bk_links = page.locator('.el-table__body .bk-link')
        log(f'  bk-links: {bk_links.count()}')
        if bk_links.count() > 0:
            log('  click bk-link first')
            bk_links.first.click()
        else:
            # 双击行
            log('  no bk-link, double-click row')
            first_row.dblclick()
    time.sleep(3)

    # 如果没出现详情页，尝试双击行
    if page.locator('.value-help-field').count() == 0:
        log('  no value-help-field, trying click row')
        # 找第一行
        rows.nth(0).click()
        time.sleep(2)
        # 找编辑按钮
        edit_btn = page.locator('button:has-text("编辑"), .el-button:has-text("编辑"), .operation-btn:has-text("编辑")')
        log(f'  edit btn after click: {edit_btn.count()}')
        if edit_btn.count() > 0:
            edit_btn.first.click()
            time.sleep(2)
        else:
            # 尝试双击
            rows.nth(0).dblclick()
            time.sleep(2)

    # 等详情页加载
    page.wait_for_selector('.value-help-field, .el-input, .el-select', timeout=10000)
    time.sleep(2)

    # 找到父组 valuehelp（detail page 中的父组）
    log('\n=== 找父组 valuehelp ===')
    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter19-detail.png', full_page=True)

    # 找页面上的所有 value-help-field
    vh_fields = page.locator('.value-help-field')
    log(f'  value-help-field count: {vh_fields.count()}')

    # 找"父组"label
    parent_label = page.locator('text=父组').first
    log(f'  parent label exists: {parent_label.count() > 0}')

    # 找父组对应的 el-select（ObjectPageField 用 .op-field 包含 label）
    # 找 .op-field:has(label:text("父组")) 然后找其内的 .el-select
    parent_field = page.locator('.op-field:has(label:text-is("父组"))')
    log(f'  parent .op-field count: {parent_field.count()}')

    # 检查所有 op-field
    all_op_fields = page.locator('.op-field')
    log(f'  all .op-field count: {all_op_fields.count()}')
    for i in range(min(all_op_fields.count(), 10)):
        el = all_op_fields.nth(i)
        text = el.text_content().strip()[:80]
        log(f'    op_field[{i}]: {text!r}')

    if parent_field.count() > 0:
        parent_select = parent_field.first.locator('.el-select__wrapper, .el-select')
        log(f'  parent select count: {parent_select.count()}')
        if parent_select.count() > 0:
            # 打开 dropdown
            target = parent_select.first
            target.click()
            time.sleep(2)

            # 等 dropdown 出现
            log('\n=== 检查 dropdown options ===')
            options = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
            opt_count = options.count()
            log(f'  option count: {opt_count}')
            for i in range(min(opt_count, 10)):
                text = options.nth(i).text_content().strip()
                log(f'    option[{i}]: {text!r}')

            # 输入"系统"
            log('\n=== 输入"系统" ===')
            api_requests.clear()
            page.keyboard.type('系统', delay=200)
            time.sleep(2)
            log('  API requests:')
            for r in api_requests:
                log(f'    {r["url"][:250]}')

            options = page.locator('.el-select-dropdown:visible .el-select-dropdown__item')
            opt_count2 = options.count()
            log(f'  option count after type: {opt_count2}')
            for i in range(min(opt_count2, 10)):
                text = options.nth(i).text_content().strip()
                log(f'    option[{i}]: {text!r}')

            page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter19-dropdown.png', full_page=True)

    browser.close()
log('\n=== DONE ===')
