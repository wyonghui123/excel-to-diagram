"""
打开下拉框并截图 - 用真实的鼠标点击
"""
import sys
import os
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from playwright.sync_api import sync_playwright

def main():
    out_dir = "d:/filework/excel-to-diagram/test_results"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()

        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        page.wait_for_timeout(1500)
        page.goto("http://localhost:3004/")
        page.wait_for_timeout(3000)
        page.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/detail/business_object/25');
            }
        """)
        page.wait_for_timeout(5000)
        page.click("text=添加备注")
        page.wait_for_timeout(3000)

        # 找到分类 select 的位置并用真实鼠标点击
        box = page.evaluate("""
            () => {
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return null;
                const items = dialog.querySelectorAll('.el-form-item');
                for (const item of items) {
                    const label = item.querySelector('.el-form-item__label');
                    if (label && label.textContent.trim() === '分类') {
                        const sel = item.querySelector('.el-select');
                        if (sel) {
                            const rect = sel.getBoundingClientRect();
                            return { x: rect.x + rect.width/2, y: rect.y + rect.height/2 };
                        }
                    }
                }
                return null;
            }
        """)
        print(f"Select position: {box}")

        if box:
            page.mouse.click(box['x'], box['y'])
            page.wait_for_timeout(2500)
            page.screenshot(path=f"{out_dir}/category_dropdown_opened.png")
            print(f"Saved: category_dropdown_opened.png")

            # 再次获取可见 dropdown 状态
            state = page.evaluate("""
                () => {
                    const dropdowns = document.querySelectorAll('.el-select-dropdown');
                    const visible = [];
                    for (const dd of dropdowns) {
                        const style = window.getComputedStyle(dd);
                        if (style.display !== 'none' && style.visibility !== 'hidden') {
                            const items = dd.querySelectorAll('.el-select-dropdown__item');
                            visible.push({
                                count: items.length,
                                texts: Array.from(items).map(i => i.textContent.trim())
                            });
                        }
                    }
                    return visible;
                }
            """)
            print(f"Visible dropdowns: {len(state)}")
            for i, dd in enumerate(state):
                print(f"  Dropdown {i+1}: {dd['count']} items")
                for text in dd['texts']:
                    hex_codes = ' '.join(f'U+{ord(c):04X}' for c in text)
                    print(f"    '{text}' -> {hex_codes}")

        browser.close()

if __name__ == "__main__":
    main()
