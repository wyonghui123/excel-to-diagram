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

    # 找 ValueHelpField 的 setupState
    info = page.evaluate("""() => {
        const sel = document.querySelector('.op-field:nth-of-type(3) .el-select');
        if (!sel) return { error: 'no select' };
        const comp = sel.__vnode?.component;
        if (!comp) return { error: 'no comp' };
        // 找 ValueHelpField
        const vhComp = comp.parent;
        if (!vhComp) return { error: 'no vhComp' };
        const ss = vhComp.setupState || {};
        return {
            vhTypeName: vhComp.type?.name || vhComp.type?.__name || 'anon',
            setupKeys: Object.keys(ss),
            hasEmit: typeof vhComp.emit,
            emitKeys: vhComp.emit ? Object.keys(vhComp.emit) : null,
            // 找 props
            propsKeys: Object.keys(vhComp.props || {}),
            onUpdateDisplayValue: typeof vhComp.props?.onUpdate:displayValue,
            onUpdateModelValue: typeof vhComp.props?.onUpdate:modelValue
        };
    }""")
    print('VH INFO:', info)

    browser.close()
