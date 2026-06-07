"""
打开下拉框并截全屏，找回 teleported 的下拉内容
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

        # 全屏截图
        page.screenshot(path=f"{out_dir}/fullscreen_01.png", full_page=True)
        print("Saved: fullscreen_01.png (full page)")

        # 找出 dropdown 的实际位置
        dropdown_info = page.evaluate("""
            () => {
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                return Array.from(dropdowns).map(dd => {
                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    const rect = dd.getBoundingClientRect();
                    const style = window.getComputedStyle(dd);
                    return {
                        text: items[0] ? items[0].textContent.trim() : '',
                        count: items.length,
                        texts: Array.from(items).map(i => i.textContent.trim()),
                        rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
                        display: style.display,
                        visibility: style.visibility,
                        zIndex: style.zIndex,
                        position: style.position
                    };
                });
            }
        """)
        for i, dd in enumerate(dropdown_info):
            print(f"Dropdown #{i}: text='{dd['text']}', count={dd['count']}, "
                  f"position=({dd['rect']['x']:.0f},{dd['rect']['y']:.0f}), "
                  f"size=({dd['rect']['w']:.0f}x{dd['rect']['h']:.0f}), "
                  f"display={dd['display']}, z={dd['zIndex']}")

        # 强制把 dropdown 设置到视口中央
        page.evaluate("""
            () => {
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                dropdowns.forEach((dd, i) => {
                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    if (items.length === 4) {
                        // 这是分类下拉
                        const texts = Array.from(items).map(i => i.textContent.trim());
                        if (texts.includes('重要') && texts.includes('警告')) {
                            dd.style.position = 'fixed';
                            dd.style.top = '200px';
                            dd.style.left = '500px';
                            dd.style.zIndex = '99999';
                            dd.style.display = 'block';
                            dd.style.visibility = 'visible';
                        }
                    }
                });
            }
        """)
        page.wait_for_timeout(1000)

        # 截图
        page.screenshot(path=f"{out_dir}/forced_visible_dropdown.png")
        print("Saved: forced_visible_dropdown.png")

        # 再次确认 dropdown 的内容
        final_check = page.evaluate("""
            () => {
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                for (const dd of dropdowns) {
                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    const texts = Array.from(items).map(i => i.textContent.trim());
                    if (texts.length === 4 &&
                        texts.includes('重要') && texts.includes('警告') &&
                        texts.includes('信息') && texts.includes('提示')) {
                        return texts;
                    }
                }
                return null;
            }
        """)
        print(f"Category dropdown options: {final_check}")
        if final_check:
            for txt in final_check:
                hex_codes = ' '.join(f'U+{ord(c):04X}' for c in txt)
                print(f"  '{txt}' -> {hex_codes}")
                # 检查是否有 emoji (任何不在 CJK 基本区或中文标点的字符)
                has_emoji = any(ord(c) > 0x2E80 and ord(c) not in range(0x3000, 0x303F) and ord(c) not in range(0xFF00, 0xFFEF) for c in txt if ord(c) > 0x9FFF)
                # 更准确：检查是否包含常见 emoji 范围
                has_emoji_v2 = any(0x1F300 <= ord(c) <= 0x1FAFF or 0x2600 <= ord(c) <= 0x27BF for c in txt)
                print(f"     contains emoji (v2): {has_emoji_v2}")

        browser.close()

if __name__ == "__main__":
    main()
