"""
查 el-select 内部结构
"""
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    page.goto("http://localhost:3004/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
    time.sleep(1)
    page.goto("http://localhost:3004/user-permission", wait_until="networkidle")
    time.sleep(3)
    page.locator('text=用户组管理').first.click()
    time.sleep(4)
    page.wait_for_selector('.el-table', timeout=10000)
    time.sleep(2)

    th4 = page.locator('.el-table__header-wrapper th').nth(4)
    th4.locator('.filter-trigger').first.click()
    time.sleep(3)

    info = page.evaluate("""() => {
        const popovers = document.querySelectorAll('.el-popper.el-popover');
        for (const pop of popovers) {
            const panel = pop.querySelector('.filter-panel');
            if (panel) {
                const sel = pop.querySelector('.el-select');
                if (sel) {
                    const wrapper = sel.querySelector('.el-select__wrapper');
                    const input = sel.querySelector('input.el-select__input');
                    return {
                        popover: !!pop,
                        panel: !!panel,
                        sel: !!sel,
                        wrapper: !!wrapper,
                        wrapperHTML: wrapper ? wrapper.outerHTML.slice(0, 500) : null,
                        input: !!input,
                        inputType: input ? input.type : null,
                        inputReadonly: input ? input.readOnly : null,
                        inputAriaExpanded: input ? input.getAttribute('aria-expanded') : null,
                        // 找 el-select 的所有子元素
                        selChildren: Array.from(sel.children).map(c => c.className)
                    };
                }
            }
        }
        return null;
    }""")
    print(info)

    # click 一下 input
    print('\n=== 尝试 click input ===')
    result = page.evaluate("""() => {
        const popovers = document.querySelectorAll('.el-popper.el-popover');
        for (const pop of popovers) {
            const panel = pop.querySelector('.filter-panel');
            if (panel) {
                const input = pop.querySelector('input.el-select__input');
                if (input) {
                    input.focus();
                    input.click();
                    return { focused: document.activeElement === input, type: input.type, value: input.value };
                }
            }
        }
        return null;
    }""")
    print('after focus:', result)
    time.sleep(2)

    page.keyboard.type('管', delay=200)
    time.sleep(3)

    result2 = page.evaluate("""() => {
        const popovers = document.querySelectorAll('.el-popper.el-popover');
        for (const pop of popovers) {
            const panel = pop.querySelector('.filter-panel');
            if (panel) {
                const input = pop.querySelector('input.el-select__input');
                if (input) {
                    return { value: input.value, focused: document.activeElement === input };
                }
            }
        }
        return null;
    }""")
    print('after type:', result2)
    page.screenshot(path=r'd:\filework\excel-to-diagram\test-results\filter-typed.png', full_page=True)
    browser.close()
