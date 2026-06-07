"""
直接通过 Vue Devtools 调用 ValueHelpField 内部的 emit
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

    # Walk DOM tree to find ValueHelpField
    result = page.evaluate("""() => {
        const all = document.querySelectorAll('.op-field');
        const out = [];
        for (const f of all) {
            const label = f.querySelector('label')?.textContent?.trim();
            const sels = f.querySelectorAll('.el-select');
            for (const s of sels) {
                // 找 .__vueParentComponent
                const comp = s.__vueParentComponent;
                const parent = comp?.parent;
                if (parent) {
                    out.push({
                        label,
                        selCompType: comp?.type?.name || comp?.type?.__name || 'anon',
                        parentType: parent?.type?.name || parent?.type?.__name || 'anon',
                        // 找 vh 的 setupState
                        vhSetup: parent?.setupState ? Object.keys(parent.setupState).slice(0, 20) : null,
                        vhModelValue: parent?.props?.modelValue,
                        vhOnUpdateModelValue: typeof parent?.props?.onUpdate:modelValue
                    });
                }
            }
        }
        return out;
    }""")
    print('=== VUE COMPS ===')
    for r in result:
        print(r)

    print('\n=== LOGS WITH emit/update ===')
    for l in logs:
        if 'emit' in l.lower() or 'update' in l.lower() or 'display' in l.lower() or 'ValueHelp' in l or 'ObjectPage' in l:
            print(l)

    browser.close()
