"""
验证新的 PlaywrightCLI dropdown helper + CSS z-index 修复
"""
import sys
import os
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    out_dir = "d:/filework/excel-to-diagram/test_results"
    os.makedirs(out_dir, exist_ok=True)

    cli = PlaywrightCLI(screenshot_dir=out_dir)

    try:
        print("Step 1: 认证 + 加载首页")
        cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        cli.wait_for_timeout(2000)
        # 直接 goto 详情页（替代 router.push，规避 __vue_app__ 路径差异）
        cli.goto("http://localhost:3004/detail/business_object/25")
        cli.wait_for_timeout(6000)

        print("Step 3: 点击 '添加备注'")
        cli.click("text=添加备注")
        cli.wait_for_timeout(3000)

        # 用一个更稳定的方式：标记 分类 select
        print("Step 3.5: 标记分类 select 元素")
        marked = cli.evaluate("""
            () => {
                // 找所有包含 "分类" 文本的 form-item 容器
                const candidates = document.querySelectorAll('.el-form-item, .app-form-item, [class*="form-item"]');
                for (const item of candidates) {
                    const label = item.querySelector('.el-form-item__label, [class*="form-item__label"]');
                    if (label && label.textContent.trim() === '分类') {
                        const sel = item.querySelector('.el-select');
                        if (sel) {
                            sel.setAttribute('data-test-target', 'category-select');
                            return 'marked via form-item';
                        }
                    }
                }
                // 备选：直接找 text=重要 的 el-select
                const all = document.querySelectorAll('.el-select');
                for (const s of all) {
                    if (s.textContent.trim() === '重要') {
                        s.setAttribute('data-test-target', 'category-select');
                        return 'marked via text=重要';
                    }
                }
                return 'not found';
            }
        """)
        print(f"  Mark: {marked}")

        # 验证标记生效
        count = cli.evaluate("""
            () => document.querySelectorAll("[data-test-target='category-select']").length
        """)
        print(f"  Marked count: {count}")

        # 检查所有 .el-select 的位置
        all_selects = cli.evaluate("""
            () => {
                const all = document.querySelectorAll('.el-select');
                return Array.from(all).map((s, i) => ({
                    idx: i,
                    text: s.textContent.substring(0, 30).trim(),
                    className: s.className,
                    hasMarker: s.hasAttribute('data-test-target')
                }));
            }
        """)
        print(f"  All .el-selects: {all_selects}")

        print("Step 4: 用新 helper 验证下拉框")
        anchor = "[data-test-target='category-select']"
        result = cli.verify_no_emoji(anchor, expected=['重要', '警告', '信息', '提示'])

        print(f"  ok: {result.get('ok')}")
        print(f"  options: {result.get('options')}")
        print(f"  hasEmoji: {result.get('hasEmoji')}")
        print(f"  missing: {result.get('missing')}")

        print("\nStep 5: 截图下拉框 (新方法)")
        screenshot_result = cli.screenshot_dropdown(
            anchor_selector=anchor,
            save_path=f"{out_dir}/helper_dropdown_after_fix.png",
            include_extract_html=True
        )
        print(f"  ok: {screenshot_result.get('ok')}")
        print(f"  count: {screenshot_result.get('count')}")
        print(f"  screenshot: {screenshot_result.get('screenshot_path')}")
        if screenshot_result.get('html_path'):
            print(f"  html: {screenshot_result.get('html_path')}")

        print("\nStep 6: get_dropdown_options 提取")
        options = cli.get_dropdown_options(anchor)
        print(f"  options: {options}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
