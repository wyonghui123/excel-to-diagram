"""
截图：打开的备注分类下拉框
"""
import sys
import os
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI()
    out_dir = "d:/filework/excel-to-diagram/test_results"
    os.makedirs(out_dir, exist_ok=True)

    try:
        cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        cli.wait_for_timeout(1500)

        cli.goto("http://localhost:3004/")
        cli.wait_for_timeout(3000)

        cli.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/detail/business_object/25');
            }
        """)
        cli.wait_for_timeout(4000)

        click_ok = cli.click("text=添加备注")
        print(f"点击 '添加备注': {click_ok}")
        cli.wait_for_timeout(3000)

        cli.evaluate("""
            () => {
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return;
                const formItems = dialog.querySelectorAll('.el-form-item');
                for (const item of formItems) {
                    const label = item.querySelector('.el-form-item__label');
                    if (label && label.textContent.trim() === '分类') {
                        const sel = item.querySelector('.el-select');
                        if (sel) {
                            sel.click();
                            return;
                        }
                    }
                }
            }
        """)
        cli.wait_for_timeout(2500)

        # 截图
        cli.screenshot(f"{out_dir}/verify_dropdown_open_final.png")
        print(f"截图已保存: {out_dir}/verify_dropdown_open_final.png")

        # 输出选项
        options_info = cli.evaluate("""
            () => {
                const result = [];
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                for (const dd of dropdowns) {
                    const style = window.getComputedStyle(dd);
                    const isVisible = style.display !== 'none' && style.visibility !== 'hidden';
                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    for (const item of items) {
                        const text = item.textContent.trim();
                        const chineseLabels = ['重要', '警告', '信息', '提示'];
                        if (chineseLabels.some(l => text.includes(l))) {
                            result.push({ text, visible: isVisible });
                        }
                    }
                }
                return result;
            }
        """)
        print(f"分类选项:")
        for opt in options_info:
            mark = "[DECORATIVE]" if opt['visible'] else "  "
            print(f"  {mark} '{opt['text']}' (visible={opt['visible']})")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
