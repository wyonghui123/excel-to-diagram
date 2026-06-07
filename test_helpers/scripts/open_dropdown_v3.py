"""
打开下拉框并截图 - 用更简单的选择器
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

        # 用 evaluate 找到 select 并点击内部 input
        clicked = page.evaluate("""
            () => {
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return 'no dialog';
                const items = dialog.querySelectorAll('.el-form-item');
                for (const item of items) {
                    const label = item.querySelector('.el-form-item__label');
                    if (label && label.textContent.trim() === '分类') {
                        const sel = item.querySelector('.el-select');
                        if (sel) {
                            const input = sel.querySelector('input');
                            if (input) {
                                // 触发点击事件
                                ['mousedown', 'mouseup', 'click', 'focus'].forEach(et => {
                                    const evt = new MouseEvent(et, { bubbles: true, button: 0 });
                                    input.dispatchEvent(evt);
                                });
                                return 'clicked input';
                            }
                            return 'no input in select';
                        }
                        return 'no select';
                    }
                }
                return 'no category form-item';
            }
        """)
        print(f"Click result: {clicked}")
        page.wait_for_timeout(2000)

        # 检查 dropdown 状态
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
        print(f"Visible dropdowns: {state}")

        # 截图
        page.screenshot(path=f"{out_dir}/dropdown_open_v3.png")
        print(f"Saved: dropdown_open_v3.png")

        # 输出选项的 unicode
        for dd in state:
            print(f"  Dropdown with {dd['count']} items:")
            for text in dd['texts']:
                hex_codes = ' '.join(f'U+{ord(c):04X}' for c in text)
                print(f"    '{text}' -> {hex_codes}")

        browser.close()

if __name__ == "__main__":
    main()
