"""
提取 dropdown 实际渲染的 HTML 元素，单独渲染用于截图
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

        important_select = page.locator(".el-select:has-text('重要')").first
        important_select.click()
        page.wait_for_timeout(2000)

        # 提取 dropdown 完整的 HTML
        dropdown_html = page.evaluate("""
            () => {
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                for (const dd of dropdowns) {
                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    if (items.length === 4) {
                        const texts = Array.from(items).map(i => i.textContent.trim());
                        if (texts.includes('重要') && texts.includes('警告')) {
                            return dd.outerHTML;
                        }
                    }
                }
                return null;
            }
        """)
        print(f"Got dropdown HTML (length {len(dropdown_html) if dropdown_html else 0})")

        if dropdown_html:
            # 创建一个独立的 HTML 页面来展示 dropdown
            test_html = f"""<!DOCTYPE html>
<html>
<head>
<style>
  body {{ font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }}
  .test-container {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  h2 {{ color: #333; margin-top: 0; }}
  .verify-info {{ background: #e6f7ff; border: 1px solid #1677ff; padding: 12px; border-radius: 4px; margin-bottom: 16px; }}
  .verify-info strong {{ color: #1677ff; }}
  .dropdown-frame {{
    display: inline-block;
    background: white;
    border: 1px solid #dcdfe6;
    border-radius: 4px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.1);
    padding: 0;
    min-width: 240px;
  }}
</style>
</head>
<body>
  <div class="test-container">
    <h2>备注分类下拉框验证</h2>
    <div class="verify-info">
      <strong>验证目标：</strong> 确认 4 个分类选项（重要/警告/信息/提示）都是<strong>纯中文</strong>，<strong>无任何 emoji 前缀</strong>。
    </div>
    <p>下面是浏览器中实际渲染的 el-select-dropdown 元素：</p>
    <div class="dropdown-frame">
      {dropdown_html}
    </div>
  </div>
</body>
</html>"""

            # 保存 HTML
            with open(f"{out_dir}/extracted_dropdown.html", "w", encoding="utf-8") as f:
                f.write(test_html)

            # 用 playwright 打开
            page2 = context.new_page()
            page2.goto(f"file:///{out_dir.replace(os.sep, '/')}/extracted_dropdown.html")
            page2.wait_for_timeout(2000)
            page2.screenshot(path=f"{out_dir}/EXTRACTED_dropdown.png", full_page=True)
            print(f"Saved: EXTRACTED_dropdown.png")
            page2.close()

        browser.close()

if __name__ == "__main__":
    main()
