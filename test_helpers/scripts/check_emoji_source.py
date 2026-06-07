"""
检查 emoji 来源 - 找出哪个下拉框包含 emoji 选项
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

        # 找到对话框中所有的 el-select
        selects_info = cli.evaluate("""
            () => {
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return { error: 'no dialog' };

                const selects = dialog.querySelectorAll('.el-select');
                const results = [];

                for (const sel of selects) {
                    // 找到父级的 el-form-item 或 label
                    let label = '';
                    let parent = sel.parentElement;
                    for (let i = 0; i < 5; i++) {
                        if (!parent) break;
                        const labelEl = parent.querySelector('.el-form-item__label');
                        if (labelEl) {
                            label = labelEl.textContent.trim();
                            break;
                        }
                        parent = parent.parentElement;
                    }

                    // 获取当前值
                    const input = sel.querySelector('.el-input__inner, .el-select__wrapper');
                    const currentValue = input ? input.textContent.trim() : 'N/A';

                    // 获取关联的 options
                    // el-select-dropdown 通常是 body 的直接子元素
                    const selectId = sel.getAttribute('aria-controls') || sel.getAttribute('data-select-id') || Math.random().toString(36);

                    results.push({
                        label: label,
                        currentValue: currentValue,
                        selectHTML: sel.outerHTML.substring(0, 300)
                    });
                }
                return results;
            }
        """)

        print("=" * 60)
        print("对话框中的所有 el-select：")
        print("=" * 60)
        for idx, sel_item in enumerate(selects_info):
            print(f"\n--- Select {idx+1} ---")
            print(f"Label: {sel_item.get('label', 'N/A')}")
            print(f"当前值: {sel_item.get('currentValue', 'N/A')}")

        # 检查对话框之外是否还有 el-select
        all_selects = cli.evaluate("""
            () => {
                const dialog = document.querySelector('.el-dialog');
                const allSelects = document.body.querySelectorAll('.el-select');
                const results = [];
                for (const sel of allSelects) {
                    // 检查是否在对话框内
                    const inDialog = dialog && dialog.contains(sel);

                    // 获取 label
                    let label = '';
                    let parent = sel.parentElement;
                    for (let i = 0; i < 5; i++) {
                        if (!parent) break;
                        const labelEl = parent.querySelector('.el-form-item__label');
                        if (labelEl) {
                            label = labelEl.textContent.trim();
                            break;
                        }
                        parent = parent.parentElement;
                    }

                    // 获取当前值
                    const input = sel.querySelector('.el-input__inner, .el-select__wrapper');
                    const currentValue = input ? input.textContent.trim() : 'N/A';

                    results.push({
                        inDialog: inDialog,
                        label: label,
                        currentValue: currentValue
                    });
                }
                return results;
            }
        """)

        print("\n" + "=" * 60)
        print("页面中所有的 el-select：")
        print("=" * 60)
        for i, sel in enumerate(all_selects):
            marker = "【对话框内】" if sel['inDialog'] else "【对话框外】"
            print(f"{marker} Label: {sel['label']}, 当前值: {sel['currentValue']}")

        # 核心检查：找到哪个下拉框包含 emoji
        # 先点击对话框中的第一个 select
        print("\n" + "=" * 60)
        print("检查对话框中分类下拉框...")

        # 获取对话框中 label 包含"分类"或"备注"的 select
        classify_select = None
        for sel_item in selects_info:
            label = sel_item.get('label', '')
            if '分类' in label or '备注' in label or label == '':
                classify_select = sel_item
                break

        if classify_select:
            print(f"找到分类 select，label='{classify_select.get('label', '')}', 当前值='{classify_select.get('currentValue', '')}'")
        else:
            print("未找到分类 select")
            print("所有 select:")
            for sel_item in selects_info:
                print(f"  label='{sel_item.get('label', 'N/A')}'")

        # 截图
        cli.screenshot("d:/filework/excel-to-diagram/test_results/05_selects_check.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
