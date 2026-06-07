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

    # 直接调用 emit
    info = page.evaluate("""() => {
        const sels = document.querySelectorAll('.el-select');
        for (const sel of sels) {
            const field = sel.closest('.op-field');
            if (!field || !field.textContent.includes('父组')) continue;
            const comp = sel.__vnode?.component;
            if (!comp) return null;
            const vhComp = comp.parent;
            if (!vhComp) return null;
            // 找 emit 函数
            const emit = vhComp.emit;
            if (typeof emit === 'function') {
                emit('update:displayValue', 'TEST_VIA_EMIT_CALL');
                return { ok: true, emitted: 'update:displayValue' };
            }
            return { ok: false, hasEmit: typeof emit };
        }
        return null;
    }""")
    print('Direct emit:', info)

    time.sleep(1)

    # 看 console 中是否出现 [ObjectPageField]
    for l in logs:
        if 'ObjectPageField' in l or 'handleFieldDisplay' in l:
            print('LOG:', l)

    browser.close()
