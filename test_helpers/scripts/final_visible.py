"""
最终验证 - 用更可靠的方式：让 select 强制 visible 在视口中央
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

        # 点击 重要 select
        important_select = page.locator(".el-select:has-text('重要')").first
        important_select.click()
        page.wait_for_timeout(2000)

        # 把可见的分类 dropdown 移出 dialog 区域，强制显示在视口中央
        # 同时临时禁用 dialog 的 z-index
        page.evaluate("""
            () => {
                // 1. 找到 4 项的、含重要警告的 dropdown
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                for (const dd of dropdowns) {
                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    if (items.length === 4) {
                        const texts = Array.from(items).map(i => i.textContent.trim());
                        if (texts.includes('重要') && texts.includes('警告') &&
                            texts.includes('信息') && texts.includes('提示')) {
                            // 强制 fixed 定位
                            dd.style.cssText = `
                                position: fixed !important;
                                top: 350px !important;
                                left: 400px !important;
                                z-index: 99999 !important;
                                display: block !important;
                                visibility: visible !important;
                                background: white !important;
                                border: 2px solid red !important;
                                width: 300px !important;
                            `;
                            // 隐藏 dialog overlay
                            const overlay = document.querySelector('.el-overlay-dialog');
                            if (overlay) overlay.style.display = 'none';
                            return 'forced visible';
                        }
                    }
                }
                return 'not found';
            }
        """)
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{out_dir}/FINAL_dropdown_visible.png")
        print("Saved: FINAL_dropdown_visible.png")

        # 同时输出最终验证
        final = page.evaluate("""
            () => {
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                for (const dd of dropdowns) {
                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    if (items.length === 4) {
                        const texts = Array.from(items).map(i => i.textContent.trim());
                        if (texts.includes('重要') && texts.includes('警告') &&
                            texts.includes('信息') && texts.includes('提示')) {
                            return {
                                options: texts,
                                hasEmoji: texts.some(t =>
                                    /[\\u{1F300}-\\u{1FAFF}]|[\\u{2600}-\\u{27BF}]|[WARNING]|[ALERT]|ℹ|[DECORATIVE]/u.test(t)
                                )
                            };
                        }
                    }
                }
                return null;
            }
        """)
        print(f"Final verification: {final}")

        browser.close()

if __name__ == "__main__":
    main()
