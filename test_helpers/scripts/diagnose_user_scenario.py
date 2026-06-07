"""
诊断：模拟用户的实际场景，不修改样式，看 popper 在哪里
"""
import sys
import os
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from playwright.sync_api import sync_playwright

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    out_dir = "d:/filework/excel-to-diagram/test_results"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()

        # 用户的实际场景
        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        page.wait_for_timeout(2000)
        # 用 router.push 模拟
        page.goto("http://localhost:3004/")
        page.wait_for_timeout(3000)
        # 等待 router
        try:
            page.wait_for_function(
                "() => document.querySelector('#app') && document.querySelector('#app').__vue_app__",
                timeout=15000
            )
        except Exception as e:
            print(f"Vue app not ready: {e}")
            # 继续，看页面状态
        page.wait_for_timeout(2000)
        page.evaluate("""
            () => {
                const app = document.querySelector('#app');
                if (app && app.__vue_app__) {
                    const router = app.__vue_app__.config.globalProperties.$router;
                    if (router) router.push('/detail/business_object/25');
                }
            }
        """)
        page.wait_for_timeout(5000)

        # 截图：当前页面
        page.screenshot(path=f"{out_dir}/user_actual_01_page.png", full_page=True)
        print("Saved: user_actual_01_page.png")

        # 找所有 "添加备注" 按钮
        add_btns = page.evaluate("""
            () => {
                const btns = Array.from(document.querySelectorAll('button, a, [role="button"]'));
                return btns.filter(b => b.textContent.trim().includes('添加备注')).map(b => ({
                    text: b.textContent.trim().substring(0, 50),
                    tag: b.tagName,
                    visible: window.getComputedStyle(b).display !== 'none' && b.offsetParent !== null
                }));
            }
        """)
        print(f"Add buttons: {add_btns}")

        # 点击
        page.click("text=添加备注")
        page.wait_for_timeout(3000)

        # 截图：打开的对话框
        page.screenshot(path=f"{out_dir}/user_actual_02_dialog.png", full_page=True)
        print("Saved: user_actual_02_dialog.png")

        # 找 分类 select
        page.evaluate("""
            () => {
                const all = document.querySelectorAll('.el-select');
                for (const s of all) {
                    if (s.textContent.trim() === '重要') {
                        s.setAttribute('data-test-target', 'category-select');
                        return true;
                    }
                }
                return false;
            }
        """)

        # 点击 select - 模拟真实用户点击
        # 找 wrapper
        anchor = page.evaluate("""
            () => {
                const sel = document.querySelector("[data-test-target='category-select']");
                if (!sel) return null;
                const wrapper = sel.querySelector('.el-select__wrapper');
                if (!wrapper) return null;
                const rect = wrapper.getBoundingClientRect();
                return { x: rect.x + rect.width/2, y: rect.y + rect.height/2 };
            }
        """)
        print(f"Anchor position: {anchor}")

        if anchor:
            # 真实鼠标点击
            page.mouse.click(anchor['x'], anchor['y'])
            page.wait_for_timeout(2000)

            # 截图：点击后（不修改样式）
            page.screenshot(path=f"{out_dir}/user_actual_03_after_click.png", full_page=True)
            print("Saved: user_actual_03_after_click.png")

            # 检查 popper 的实际状态
            state = page.evaluate("""
                () => {
                    const poppers = document.querySelectorAll('body .el-select-dropdown, body .el-dropdown-menu, body .el-popper');
                    const result = [];
                    for (const p of poppers) {
                        const items = p.querySelectorAll('.el-select-dropdown__item, .el-dropdown-menu__item, .el-popper__item');
                        if (items.length === 0) continue;
                        const rect = p.getBoundingClientRect();
                        const style = window.getComputedStyle(p);
                        result.push({
                            texts: Array.from(items).map(i => i.textContent.trim()).slice(0, 10),
                            rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
                            display: style.display,
                            visibility: style.visibility,
                            zIndex: style.zIndex,
                            opacity: style.opacity,
                            position: style.position,
                            transform: style.transform
                        });
                    }
                    return result;
                }
            """)
            print(f"Poppers state:")
            for i, s in enumerate(state):
                print(f"  Popper #{i}:")
                print(f"    texts: {s['texts']}")
                print(f"    rect: x={s['rect']['x']:.0f}, y={s['rect']['y']:.0f}, w={s['rect']['w']:.0f}, h={s['rect']['h']:.0f}")
                print(f"    display={s['display']}, visibility={s['visibility']}, z-index={s['zIndex']}, opacity={s['opacity']}")
                print(f"    position={s['position']}, transform={s['transform']}")

        browser.close()

if __name__ == "__main__":
    main()
