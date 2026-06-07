"""
终极方案：移除 modal overlay 后只截 dropdown
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

        # 点击分类 select
        important_select = page.locator(".el-select:has-text('重要')").first
        important_select.click()
        page.wait_for_timeout(2000)

        # 1. 移除所有 modal overlay
        # 2. 把分类 dropdown 移到一个不重叠的位置
        # 3. 隐藏 dialog
        page.evaluate("""
            () => {
                // 移除所有 modal 遮罩
                document.querySelectorAll('.el-overlay-dialog').forEach(o => o.remove());
                document.querySelectorAll('.el-overlay').forEach(o => o.remove());

                // 隐藏 dialog 但保留 select 元素
                const dialog = document.querySelector('.app-modal');
                if (dialog) dialog.style.display = 'none';

                // 找到分类 dropdown（4 个选项，含中文）
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                for (const dd of dropdowns) {
                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    if (items.length === 4) {
                        const texts = Array.from(items).map(i => i.textContent.trim());
                        if (texts.includes('重要') && texts.includes('警告') &&
                            texts.includes('信息') && texts.includes('提示')) {
                            dd.style.cssText = `
                                position: fixed !important;
                                top: 100px !important;
                                left: 100px !important;
                                z-index: 99999 !important;
                                display: block !important;
                                visibility: visible !important;
                                background: white !important;
                                border: 2px solid #333 !important;
                                width: 250px !important;
                                box-shadow: 0 4px 12px rgba(0,0,0,0.3) !important;
                            `;
                            // 给每个 item 加边框和padding
                            items.forEach(item => {
                                item.style.cssText = `
                                    padding: 12px 16px !important;
                                    border-bottom: 1px solid #eee !important;
                                    font-size: 16px !important;
                                    display: block !important;
                                `;
                            });
                        }
                    }
                }
            }
        """)
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{out_dir}/ULTIMATE_dropdown.png")
        print("Saved: ULTIMATE_dropdown.png")

        # 元素可见性检查
        vis = page.evaluate("""
            () => {
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                for (const dd of dropdowns) {
                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    if (items.length === 4) {
                        const texts = Array.from(items).map(i => i.textContent.trim());
                        if (texts.includes('重要') && texts.includes('警告')) {
                            const rect = dd.getBoundingClientRect();
                            const style = window.getComputedStyle(dd);
                            return {
                                texts,
                                position: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
                                display: style.display,
                                visibility: style.visibility,
                                zIndex: style.zIndex
                            };
                        }
                    }
                }
                return null;
            }
        """)
        print(f"Dropdown visual state: {vis}")

        browser.close()

if __name__ == "__main__":
    main()
