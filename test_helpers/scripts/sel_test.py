"""
测试详情页选择父组后是否显示 name
"""
import time
import os
from playwright.sync_api import sync_playwright

DEV_LOGIN_URL = 'http://localhost:3004/api/v1/auth/dev-login?username=admin'
USER_GROUP_DETAIL_URL = 'http://localhost:3004/detail/user_group/2'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    logs = []
    page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))

    page.goto(DEV_LOGIN_URL, wait_until='networkidle')
    time.sleep(1)
    page.goto(USER_GROUP_DETAIL_URL, wait_until='networkidle')
    time.sleep(3)
    edit_btn = page.locator('button:has-text("编辑")').first
    edit_btn.click()
    time.sleep(4)

    # 检查初始显示
    sel = page.locator('.op-field:has-text("父组") .el-select').first
    placeholder = sel.locator('.el-select__placeholder')
    print(f'Initial placeholder: {placeholder.text_content().strip()!r}')

    # 打开下拉
    sel.click()
    time.sleep(2)

    # 选择第一项
    options = page.locator('.el-select-dropdown__item')
    print(f'Options count: {options.count()}')
    if options.count() > 0:
        # 找一个 "普通用户" 之类的（不是 "系统管理员"）
        target_text = None
        for i in range(options.count()):
            text = options.nth(i).text_content().strip()
            if text and '系统管理员' not in text:
                target_text = text
                print(f'Clicking option: {text!r}')
                options.nth(i).click()
                break
        if not target_text:
            print('No other option found, clicking first')
            options.first.click()
        time.sleep(2)

    # 关闭下拉
    page.keyboard.press('Escape')
    time.sleep(1)

    # 再次检查显示
    sel = page.locator('.op-field:has-text("父组") .el-select').first
    print(f'After select placeholder: {placeholder.text_content().strip()!r}')

    # 看 input
    input_value = page.locator('.op-field:has-text("父组") .el-select input').first
    print(f'Input value: {input_value.input_value()!r}')

    # 看 el-select 内部 selected
    states = page.evaluate("""() => {
        const sel = document.querySelector('.op-field:nth-of-type(3) .el-select');
        if (!sel) {
            // 找父组
            const fields = document.querySelectorAll('.op-field');
            for (let i = 0; i < fields.length; i++) {
                if (fields[i].textContent.includes('父组')) {
                    return { error: 'not found in op-field ' + i };
                }
            }
            return { error: 'no field' };
        }
        const comp = sel.__vnode?.component;
        const setupState = comp?.setupState || {};
        return {
            propsModelValue: comp?.props?.modelValue,
            statesSelected: setupState.selected,
            statesSelectedLabel: setupState.selectedLabel,
            optionsCount: setupState.optionsArray ? setupState.optionsArray.length : 0
        };
    }""")
    print(f'states: {states}')

    # 看 _display 字段
    form_data = page.evaluate("""() => {
        // 找 .op-field 下面的 input，看它的 v-model 值
        // 通过 Vue Devtools 方式
        const fields = document.querySelectorAll('.op-field');
        const result = [];
        for (const f of fields) {
            const label = f.querySelector('label')?.textContent?.trim();
            const input = f.querySelector('input');
            if (label && input) {
                result.push({ label, value: input.value });
            }
        }
        return result;
    }""")
    print(f'Field values: {form_data}')

    fld = page.locator('.op-field:has-text("父组")').first
    if fld.count() > 0:
        fld.screenshot(path=os.path.join(r'd:\filework\excel-to-diagram\test-results', 'detail-after-sel.png'))

    print('\n=== CONSOLE LOGS ===')
    for l in logs:
        if 'useValueHelp' in l or 'resolveDisplay' in l or 'select' in l.lower() or 'change' in l.lower():
            print(l)

    browser.close()
