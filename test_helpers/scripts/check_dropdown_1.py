"""
找到每个 dropdown 的父级 el-select 及 form-label
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
import json

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI()

    try:
        cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        cli.wait_for_timeout(1000)
        cli.goto("http://localhost:3004/")
        cli.wait_for_timeout(3000)
        cli.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/detail/business_object/25');
            }
        """)
        cli.wait_for_timeout(3000)

        cli.click("text=添加备注")
        cli.wait_for_timeout(3000)

        # 分析每个 dropdown 的父级 select
        result = cli.evaluate("""
            () => {
                const result = [];
                const dropdowns = document.querySelectorAll('.el-select-dropdown');

                dropdowns.forEach((dd, idx) => {
                    const style = window.getComputedStyle(dd);
                    const isVisible = style.display !== 'none';

                    // 获取这个 dropdown 的父级 select
                    let parentSelect = null;
                    let formLabel = '';

                    // 方法1: 通过 aria-controls 属性查找
                    const controls = dd.getAttribute('aria-controls');
                    if (controls) {
                        const selectById = document.getElementById(controls);
                        if (selectById) {
                            parentSelect = selectById;
                        }
                    }

                    // 方法2: 通过相邻兄弟元素查找
                    if (!parentSelect) {
                        parentSelect = dd.previousElementSibling;
                    }

                    // 方法3: 通过 Vue 实例查找
                    if (parentSelect) {
                        const vueComp = parentSelect.__vueParentComponent || parentSelect.__vue__;
                        if (vueComp) {
                            // 获取 form-label
                            let current = parentSelect.parentElement;
                            for (let i = 0; i < 10; i++) {
                                if (!current) break;
                                const label = current.querySelector('.el-form-item__label');
                                if (label) {
                                    formLabel = label.textContent.trim();
                                    break;
                                }
                                current = current.parentElement;
                            }
                        }
                    }

                    // 获取选项
                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    const texts = Array.from(items).map(i => i.textContent.trim());

                    result.push({
                        idx: idx,
                        visible: isVisible,
                        ariaControls: dd.getAttribute('aria-controls'),
                        parentSelectClass: parentSelect ? parentSelect.className.substring(0, 50) : 'none',
                        formLabel: formLabel,
                        itemCount: items.length,
                        texts: texts.slice(0, 8)
                    });
                });

                return result;
            }
        """)

        print("=" * 60)
        print("每个 dropdown 的父级分析：")
        print("=" * 60)
        for dd in result:
            marker = "【可见】" if dd['visible'] else "【隐藏】"
            print(f"\nDropdown {dd['idx']} {marker}")
            print(f"  aria-controls: {dd['ariaControls']}")
            print(f"  父级 class: {dd['parentSelectClass']}")
            print(f"  Form label: '{dd['formLabel']}'")
            print(f"  选项数: {dd['itemCount']}")
            print(f"  选项: {dd['texts']}")

        cli.screenshot("d:/filework/excel-to-diagram/test_results/final_08_parent_select.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
