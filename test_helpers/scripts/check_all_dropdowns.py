"""
找出 emoji 来自哪个 el-select-dropdown
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
import json

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI()

    try:
        # 认证
        cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        cli.wait_for_timeout(500)
        cli.goto("http://localhost:3004/")
        cli.wait_for_timeout(2000)

        # 导航到详情页
        cli.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/detail/business_object/25');
            }
        """)
        cli.wait_for_timeout(3000)

        # 点击添加备注
        cli.click("text=添加备注")
        cli.wait_for_timeout(2000)

        # 截图查看对话框
        cli.screenshot("d:/filework/excel-to-diagram/test_results/07_dialog_snapshot.png")

        # 展开对话框中所有可见的下拉框
        # 先获取对话框中所有 el-select
        all_selects = cli.evaluate("""
            () => {
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return { error: 'no dialog' };

                const selects = dialog.querySelectorAll('.el-select');
                const results = [];

                selects.forEach((sel, idx) => {
                    // 获取关联的 label
                    let labelText = '';
                    let parent = sel.parentElement;
                    for (let i = 0; i < 6; i++) {
                        if (!parent) break;
                        const labelEl = parent.querySelector(':scope > .el-form-item__label, :scope > label');
                        if (labelEl) {
                            labelText = labelEl.textContent.trim();
                            break;
                        }
                        parent = parent.parentElement;
                    }

                    // 当前选中的值
                    let currentValue = '';
                    const input = sel.querySelector('.el-input__inner, .el-select__wrapper');
                    if (input) currentValue = input.textContent.trim();

                    results.push({
                        index: idx,
                        label: labelText,
                        currentValue: currentValue
                    });
                });

                return results;
            }
        """)

        print("=" * 60)
        print("对话框中的所有 el-select：")
        print("=" * 60)
        print(f"all_selects type: {type(all_selects)}, value: {all_selects}")

        if isinstance(all_selects, dict):
            print(f"  (error): {all_selects.get('error', 'no error')}")
        elif isinstance(all_selects, list):
            for item in all_selects:
                print(f"  Select {item.get('index', '?')}: label='{item.get('label', '?')}', value='{item.get('currentValue', '?')}'")
        else:
            print(f"  Unexpected type: {type(all_selects)}")
            print(f"  Value: {all_selects}")

        # 点击所有下拉框，逐个展开并检查其 dropdown
        if isinstance(all_selects, list):
            for item in all_selects:
                idx = item.get('index', 0)

            # 点击这个 select
            click_result = cli.evaluate(f"""
                () => {{
                    const dialog = document.querySelector('.el-dialog');
                    if (!dialog) return false;
                    const selects = dialog.querySelectorAll('.el-select');
                    if (!selects[{idx}]) return false;
                    const sel = selects[{idx}];
                    const input = sel.querySelector('.el-input__inner, .el-select__wrapper, .el-input__wrapper');
                    if (input) {{
                        input.click();
                        return true;
                    }}
                    sel.click();
                    return true;
                }}
            """)

            cli.wait_for_timeout(1000)

            # 检查当前展开的 dropdown
            dropdown_options = cli.evaluate("""
                () => {
                    const results = [];
                    const dropdowns = document.querySelectorAll('.el-select-dropdown');
                    for (const dd of dropdowns) {
                        const style = window.getComputedStyle(dd);
                        if (style.display === 'none') continue;
                        if (style.visibility === 'hidden') continue;

                        const items = dd.querySelectorAll('.el-select-dropdown__item');
                        for (const item of items) {
                            const text = item.textContent.trim();
                            results.push(text);
                        }
                    }
                    return results;
                }
            """)

            print(f"\nSelect {idx} (label='{item.get('label', '')}') 的下拉选项: {dropdown_options}")

            # 检查是否有 emoji
            emoji_in_dropdown = any(e in opt for opt in dropdown_options for e in ['[WARNING]', '[ALERT]', '[DECORATIVE]', 'ℹ'])
            if emoji_in_dropdown:
                print(f"  [X] 发现 emoji!")

            # 关闭下拉
            cli.press_key("Escape")
            cli.wait_for_timeout(500)

        # 截图
        cli.screenshot("d:/filework/excel-to-diagram/test_results/08_all_dropdowns.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
