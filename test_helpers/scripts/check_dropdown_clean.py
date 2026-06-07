"""
干净的测试：检查下拉框中分类选项的确切文本
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
import json

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI()

    try:
        # Step 1: 认证
        cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        cli.wait_for_timeout(1000)

        # Step 2: 加载首页
        cli.goto("http://localhost:3004/")
        cli.wait_for_timeout(3000)

        # Step 3: 导航到详情页
        cli.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/detail/business_object/25');
            }
        """)
        cli.wait_for_timeout(3000)

        # Step 4: 截图初始状态
        cli.screenshot("d:/filework/excel-to-diagram/test_results/final_01_initial.png")

        # Step 5: 点击添加备注
        click_ok = cli.click("text=添加备注")
        print(f"点击添加备注: {click_ok}")
        cli.wait_for_timeout(3000)

        # Step 6: 检查对话框
        dialog_visible = cli.is_visible("text=新增备注")
        print(f"对话框可见: {dialog_visible}")
        cli.screenshot("d:/filework/excel-to-diagram/test_results/final_02_dialog.png")

        # Step 7: 获取对话框中分类的当前值
        current_category = cli.evaluate("""
            () => {
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return 'no dialog';

                // 找 label 为"分类"的 form-item 中的 el-select
                const formItems = dialog.querySelectorAll('.el-form-item');
                for (const item of formItems) {
                    const label = item.querySelector('.el-form-item__label');
                    if (label && label.textContent.trim() === '分类') {
                        const sel = item.querySelector('.el-select');
                        if (sel) {
                            const input = sel.querySelector('.el-input__inner, .el-select__wrapper');
                            return input ? input.textContent.trim() : 'no input found';
                        }
                    }
                }
                return 'no category select found';
            }
        """)
        print(f"当前分类值: '{current_category}'")

        # Step 8: 点击分类下拉框
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
        cli.wait_for_timeout(2000)

        # Step 9: 获取下拉选项详情
        options_info = cli.evaluate("""
            () => {
                const result = {
                    dropdownCount: 0,
                    categoryOptions: [],
                    allOptions: []
                };

                // 获取所有 el-select-dropdown
                const dropdowns = document.querySelectorAll('.el-select-dropdown');
                result.dropdownCount = dropdowns.length;

                for (const dd of dropdowns) {
                    const style = window.getComputedStyle(dd);
                    const isVisible = style.display !== 'none' && style.visibility !== 'hidden';

                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    for (const item of items) {
                        const text = item.textContent.trim();

                        // 提取 Unicode
                        const hex = Array.from(text).map(c => 'U+' + c.charCodeAt(0).toString(16).toUpperCase().padStart(4, '0')).join(' ');

                        result.allOptions.push({
                            text: text,
                            unicode: hex,
                            dropdownVisible: isVisible
                        });
                    }
                }

                // 只找中文相关的选项
                const chineseOptions = result.allOptions.filter(o =>
                    o.text.includes('重要') || o.text.includes('警告') ||
                    o.text.includes('信息') || o.text.includes('提示')
                );
                result.categoryOptions = chineseOptions;

                return result;
            }
        """)

        print(f"\n下拉框总数: {options_info['dropdownCount']}")
        print(f"中文相关选项: {len(options_info['categoryOptions'])}")
        for opt in options_info['categoryOptions']:
            print(f"  '{opt['text']}' | {opt['unicode']}")

        # Step 10: 截图下拉框
        cli.screenshot("d:/filework/excel-to-diagram/test_results/final_03_dropdown.png")

        # Step 11: 验证结果
        print("\n" + "=" * 60)
        print("验证结果：")
        print("=" * 60)

        chinese_labels = ['重要', '警告', '信息', '提示']
        emoji_labels = ['[WARNING]', '[ALERT]', 'ℹ️', '[DECORATIVE]']

        for opt in options_info['categoryOptions']:
            has_emoji = any(e in opt['text'] for e in emoji_labels)
            has_chinese = any(l in opt['text'] for l in chinese_labels)

            if has_emoji:
                print(f"[X] 发现 emoji: '{opt['text']}'")
            if has_chinese and not has_emoji:
                print(f"[OK] 正确的中文: '{opt['text']}'")

        # 统计
        correct = sum(1 for o in options_info['categoryOptions'] if
                    any(l in o['text'] for l in chinese_labels) and
                    not any(e in o['text'] for e in emoji_labels))
        with_emoji = sum(1 for o in options_info['categoryOptions'] if
                        any(e in o['text'] for e in emoji_labels))

        print(f"\n正确的中文选项: {correct}/4")
        print(f"带 emoji 的选项: {with_emoji}")

        if correct == 4 and with_emoji == 0:
            print("\n[OK] 测试通过！")
        else:
            print("\n[X] 测试失败！")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
