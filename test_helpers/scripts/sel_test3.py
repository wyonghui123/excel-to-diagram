"""
最简化：截图选择前后
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

    page.goto(DEV_LOGIN_URL, wait_until='networkidle')
    time.sleep(1)
    page.goto(USER_GROUP_DETAIL_URL, wait_until='networkidle')
    time.sleep(3)
    edit_btn = page.locator('button:has-text("编辑")').first
    edit_btn.click()
    time.sleep(4)

    # 截图：选择前（全页）
    page.screenshot(path=os.path.join(r'd:\filework\excel-to-diagram\test-results', 'before-sel.png'), full_page=True)

    # 打开下拉
    sel = page.locator('.op-field:has-text("父组") .el-select').first
    sel.click()
    time.sleep(2)

    # 截图：下拉打开
    page.screenshot(path=os.path.join(r'd:\filework\excel-to-diagram\test-results', 'dropdown-open.png'), full_page=True)

    # 选择 "TEST Group 100"
    target = page.locator('.el-select-dropdown__item:has-text("TEST Group 100")').first
    target.click()
    time.sleep(2)

    # 截图：选择后
    page.screenshot(path=os.path.join(r'd:\filework\excel-to-diagram\test-results', 'after-sel.png'), full_page=True)

    # 看 el-select 状态
    sel_state = page.evaluate("""() => {
        const fields = document.querySelectorAll('.op-field');
        for (const f of fields) {
            if (f.textContent.includes('父组')) {
                const s = f.querySelector('.el-select');
                if (!s) return { error: 'no select' };
                const placeholder = s.querySelector('.el-select__placeholder');
                const input = s.querySelector('input');
                const vnode = s.__vnode;
                const comp = vnode?.component;
                const setupState = comp?.setupState || {};
                return {
                    placeholderText: placeholder ? placeholder.textContent.trim() : '',
                    placeholderClass: placeholder ? placeholder.className : '',
                    inputValue: input ? input.value : '',
                    propsModelValue: comp?.props?.modelValue,
                    statesSelected: setupState.selected,
                    statesSelectedLabel: setupState.selectedLabel,
                    optionsArrayLen: Array.isArray(setupState.optionsArray) ? setupState.optionsArray.length : 0,
                    optionsArraySample: Array.isArray(setupState.optionsArray) ? setupState.optionsArray.slice(0, 5).map(o => ({ value: o.value, label: o.label, currentLabel: o.currentLabel })) : null
                };
            }
        }
        return { error: 'no field' };
    }""")
    print('=== SEL STATE AFTER SELECT ===')
    print(sel_state)

    browser.close()
