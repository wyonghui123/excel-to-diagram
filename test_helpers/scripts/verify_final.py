"""
简化的最终验证：截图 + 看 el-select 显示
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
    page.goto("http://localhost:3004/detail/user_group/2", wait_until="networkidle")
    time.sleep(3)
    page.locator("button:has-text('编辑')").first.click()
    time.sleep(4)

    # 截图 before
    page.screenshot(path=os.path.join(r'd:\filework\excel-to-diagram\test-results', 'final-before.png'), full_page=True)

    sel = page.locator(".op-field:has-text('父组') .el-select").first
    sel.click()
    time.sleep(2)
    target = page.locator(".el-select-dropdown__item:has-text('TEST Group 100')").first
    target.click()
    time.sleep(3)

    # 截图 after
    page.screenshot(path=os.path.join(r'd:\filework\excel-to-diagram\test-results', 'final-after.png'), full_page=True)

    # 抓 el-select 状态
    state = page.evaluate("""() => {
        const fields = document.querySelectorAll('.op-field');
        for (const f of fields) {
            if (f.textContent.includes('父组')) {
                const s = f.querySelector('.el-select');
                const placeholder = s.querySelector('.el-select__placeholder');
                const input = s.querySelector('input');
                const comp = s.__vnode?.component;
                const setupState = comp?.setupState || {};
                return {
                    placeholderText: placeholder ? placeholder.textContent.trim() : '',
                    inputValue: input ? input.value : '',
                    propsModelValue: comp?.props?.modelValue,
                    optionsSample: Array.isArray(setupState.optionsArray) ? setupState.optionsArray.slice(0, 3).map(o => ({ value: o.value, label: o.label })) : null
                };
            }
        }
        return null;
    }""")
    print('FINAL STATE:', state)

    print('\n=== KEY LOGS ===')
    for l in logs:
        if 'VH ' in l or 'ObjectPageField' in l or 'handleField' in l or 'Content' in l or 'Shell' in l:
            print(l)

    browser.close()
