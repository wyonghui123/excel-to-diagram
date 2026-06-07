"""
查找 listener 实际位置
"""
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

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
            if (!comp) return null;
            const vhComp = comp.parent;
            if (!vhComp) return null;
            // 找所有 key
            const allKeys = Object.keys(vhComp);
            // 找 listener
            const hasOnUpdateDisplayValue = 'onUpdate:displayValue' in vhComp;
            const hasOnUpdateModelValue = 'onUpdate:modelValue' in vhComp;
            return {
                allKeysSample: allKeys.slice(0, 30),
                hasOnUpdateDisplayValue,
                hasOnUpdateModelValue,
                // 试 vnode.props
                vnodePropsKeys: vhComp.vnode?.props ? Object.keys(vhComp.vnode.props) : null,
                // 试 instance.props
                instancePropsKeys: vhComp.instance?.props ? Object.keys(vhComp.instance.props) : null
            };
        }
        return null;
    }""")
    print('VH INFO:', info)

    browser.close()
