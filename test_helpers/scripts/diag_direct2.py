"""
直接调用 VH 的 emit
"""
import time
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

    info = page.evaluate("""() => {
        const sels = document.querySelectorAll('.el-select');
        for (const sel of sels) {
            const field = sel.closest('.op-field');
            if (!field || !field.textContent.includes('父组')) continue;
            const comp = sel.__vnode?.component;
            if (!comp) return { error: 'no comp' };
            const vhComp = comp.parent;
            if (!vhComp) return { error: 'no vhComp' };
            const ss = vhComp.setupState || {};
            const props = vhComp.props || {};
            return {
                vhTypeName: vhComp.type?.name || 'anon',
                setupKeys: Object.keys(ss),
                propsKeys: Object.keys(props),
                // 找 listener
                hasOnUpdateDisplayValue: 'onUpdate:displayValue' in props,
                hasOnUpdateModelValue: 'onUpdate:modelValue' in props,
                // 调用 emit
                emitTest: 'will call',
            };
        }
        return { error: 'no parent field select' };
    }""")
    print('VH INFO:', info)

    browser.close()
