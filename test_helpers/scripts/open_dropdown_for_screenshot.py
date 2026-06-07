"""
打开下拉框并截图 - 通过点击 input 元素
"""
import sys
import os
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI()
    out_dir = "d:/filework/excel-to-diagram/test_results"

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
        cli.click("text=添加备注")
        cli.wait_for_timeout(3000)

        # 强制聚焦并点击分类下拉框的 input
        cli.evaluate("""
            () => {
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return 'no dialog';
                const formItems = dialog.querySelectorAll('.el-form-item');
                for (const item of formItems) {
                    const label = item.querySelector('.el-form-item__label');
                    if (label && label.textContent.trim() === '分类') {
                        const sel = item.querySelector('.el-select');
                        if (sel) {
                            // 模拟点击 input 选择器
                            const input = sel.querySelector('.el-input__inner, .el-select__input, input');
                            if (input) {
                                input.focus();
                                input.click();
                            }
                            // 触发 element-plus 的下拉
                            const event = new MouseEvent('mousedown', { bubbles: true });
                            sel.dispatchEvent(event);
                            const event2 = new MouseEvent('mouseup', { bubbles: true });
                            sel.dispatchEvent(event2);
                            return 'clicked';
                        }
                    }
                }
                return 'not found';
            }
        """)
        cli.wait_for_timeout(3000)

        # 检查是否打开
        dropdown_visible = cli.evaluate("""
            () => {
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                for (const dd of dropdowns) {
                    const style = window.getComputedStyle(dd);
                    if (style.display !== 'none' && style.visibility !== 'hidden') {
                        const items = dd.querySelectorAll('.el-select-dropdown__item');
                        if (items.length > 0) {
                            const texts = Array.from(items).map(i => i.textContent.trim());
                            return { visible: true, count: items.length, texts };
                        }
                    }
                }
                return { visible: false };
            }
        """)
        print(f"Dropdown state: {dropdown_visible}")

        cli.screenshot(f"{out_dir}/verify_dropdown_forced_open.png")
        print(f"Screenshot saved: {out_dir}/verify_dropdown_forced_open.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
