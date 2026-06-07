"""
检查 el-option 的 label 属性值
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

        # 检查对话框是否出现
        dialog_exists = cli.is_visible("text=新增备注")
        print(f"对话框可见: {dialog_exists}")

        if not dialog_exists:
            # 获取页面文本
            page_text = cli.evaluate("() => document.body.innerText.substring(0, 500)")
            print(f"页面文本: {page_text}")

            # 截图
            cli.screenshot("d:/filework/excel-to-diagram/test_results/12_no_dialog.png")
            return

        # 点击下拉框 - 使用 JavaScript 直接点击
        cli.evaluate("""
            () => {
                // 找到对话框中的 el-select
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return 'no dialog';

                // 找到 label 为"分类"或第一个 el-select
                const formItems = dialog.querySelectorAll('.el-form-item');
                for (const item of formItems) {
                    const label = item.querySelector('.el-form-item__label');
                    if (label && label.textContent.includes('分类')) {
                        const sel = item.querySelector('.el-select');
                        if (sel) {
                            sel.click();
                            return 'clicked category select';
                        }
                    }
                }

                // 如果没找到分类，尝试第一个 el-select
                const firstSelect = dialog.querySelector('.el-select');
                if (firstSelect) {
                    firstSelect.click();
                    return 'clicked first select';
                }

                return 'no select found';
            }
        """)
        print("点击下拉框: JS click")
        cli.wait_for_timeout(3000)

        # 检查 el-option 的 label 属性
        result = cli.evaluate("""
            () => {
                // 尝试多种选择器
                let items = document.querySelectorAll(".el-option");
                if (items.length === 0) {
                    items = document.querySelectorAll(".el-select-dropdown__item");
                }
                if (items.length === 0) {
                    // 尝试找所有包含 "重要" 的元素
                    const allElements = Array.from(document.querySelectorAll("*"));
                    const matching = allElements.filter(el => {
                        return el.textContent && el.textContent.includes("重要") && el.children.length === 0;
                    });
                    return {
                        method: "all elements with '重要'",
                        count: matching.length,
                        items: matching.slice(0, 10).map(el => ({
                            tag: el.tagName,
                            class: el.className.substring(0, 60),
                            text: el.textContent.trim(),
                            label: el.getAttribute ? el.getAttribute("label") : null,
                            parent: el.parentElement ? el.parentElement.className.substring(0, 60) : "none"
                        }))
                    };
                }
                return {
                    method: "el-option",
                    count: items.length,
                    items: Array.from(items).map(item => {
                        return {
                            text: item.textContent.trim(),
                            labelAttr: item.getAttribute("label"),
                            selected: item.classList.contains("selected"),
                            parentClass: item.parentElement ? item.parentElement.className.substring(0, 50) : "none"
                        };
                    })
                };
            }
        """)

        print("=" * 60)
        print("el-option 的 label 属性：")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 截图
        cli.screenshot("d:/filework/excel-to-diagram/test_results/13_el_options.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
