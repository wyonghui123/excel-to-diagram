"""
严格的验证 - 多次确认下拉框实际打开并截图
"""
import sys
import os
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from playwright.sync_api import sync_playwright

def main():
    out_dir = "d:/filework/excel-to-diagram/test_results"
    os.makedirs(out_dir, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()

        # 认证 + 加载
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

        # 点击"添加备注"
        page.click("text=添加备注")
        page.wait_for_timeout(3000)

        # 截图 1: 打开对话框后
        page.screenshot(path=f"{out_dir}/strict_01_dialog.png")
        print(f"Step 1: Saved strict_01_dialog.png")

        # 找到 分类 select 元素
        category_input = page.locator(".el-dialog .el-form-item:has(.el-form-item__label:text-is('分类')) .el-select").first
        print(f"Step 2: Category select found: {category_input.count() > 0}")

        # 检查 select 数量
        select_count = page.locator(".el-dialog .el-select").count()
        print(f"Step 3: Selects in dialog: {select_count}")

        # 点击 select
        category_input.click()
        page.wait_for_timeout(2000)

        # 检查 dropdown 是否真的可见
        check1 = page.evaluate("""
            () => {
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                const result = [];
                for (let i = 0; i < dropdowns.length; i++) {
                    const dd = dropdowns[i];
                    const style = window.getComputedStyle(dd);
                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    const rect = dd.getBoundingClientRect();
                    result.push({
                        index: i,
                        display: style.display,
                        visibility: style.visibility,
                        zIndex: style.zIndex,
                        itemCount: items.length,
                        items: Array.from(items).map(i => i.textContent.trim()),
                        rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height }
                    });
                }
                return result;
            }
        """)
        print(f"Step 4: Total dropdowns in DOM: {len(check1)}")
        for dd in check1:
            is_open = dd['display'] != 'none' and dd['visibility'] != 'hidden'
            print(f"  Dropdown #{dd['index']}: display={dd['display']}, items={dd['itemCount']}, visible={is_open}")
            for txt in dd['items']:
                hex_codes = ' '.join(f'U+{ord(c):04X}' for c in txt)
                print(f"    '{txt}' -> {hex_codes}")

        # 截图 2
        page.screenshot(path=f"{out_dir}/strict_02_after_click.png")
        print(f"Step 5: Saved strict_02_after_click.png")

        # 等待并再次截图
        page.wait_for_timeout(2000)
        page.screenshot(path=f"{out_dir}/strict_03_waited.png")
        print(f"Step 6: Saved strict_03_waited.png")

        # 如果没开，尝试 hover
        category_input.hover()
        page.wait_for_timeout(500)
        category_input.click(force=True)
        page.wait_for_timeout(2000)
        page.screenshot(path=f"{out_dir}/strict_04_force_click.png")
        print(f"Step 7: Saved strict_04_force_click.png")

        # 最后一次详细检查
        final = page.evaluate("""
            () => {
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return { error: 'no dialog' };
                const items = dialog.querySelectorAll('.el-form-item');
                for (const item of items) {
                    const label = item.querySelector('.el-form-item__label');
                    if (label && label.textContent.trim() === '分类') {
                        const sel = item.querySelector('.el-select');
                        if (sel) {
                            return {
                                selectExists: true,
                                selectClass: sel.className,
                                html: sel.outerHTML.substring(0, 500)
                            };
                        }
                    }
                }
                return { error: 'no category select' };
            }
        """)
        print(f"Step 8: Select info: {final}")

        browser.close()

if __name__ == "__main__":
    main()
