"""
打开下拉框并截图 - 用 Playwright 真实点击
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

        # 认证
        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        page.wait_for_timeout(1500)

        # 加载首页
        page.goto("http://localhost:3004/")
        page.wait_for_timeout(3000)

        # 导航到详情页
        page.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/detail/business_object/25');
            }
        """)
        page.wait_for_timeout(5000)

        # 点击 "添加备注"
        page.click("text=添加备注")
        page.wait_for_timeout(3000)

        # 截图 1: 打开的对话框
        page.screenshot(path=f"{out_dir}/dialog_with_input.png")
        print(f"Saved: dialog_with_input.png")

        # 用真实点击 - 通过 locator 找到 select
        # 找到 "分类" 标签的 form-item
        category_select = page.locator('.el-dialog .el-form-item:has(.el-form-item__label:text("分类")) .el-select').first
        category_select.click()
        page.wait_for_timeout(2000)

        # 截图 2: 打开的下拉框
        page.screenshot(path=f"{out_dir}/category_dropdown_open.png")
        print(f"Saved: category_dropdown_open.png")

        # 获取可见的 dropdown 文本
        items = page.locator('.el-select-dropdown:visible .el-select-dropdown__item').all_text_contents()
        print(f"Visible dropdown items: {items}")

        # 检查 unicode
        for item in items:
            hex_codes = ' '.join(f'U+{ord(c):04X}' for c in item)
            print(f"  '{item}' -> {hex_codes}")

        browser.close()

if __name__ == "__main__":
    main()
