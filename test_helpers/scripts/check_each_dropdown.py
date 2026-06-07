"""
分析每个 el-select-dropdown 的具体内容
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

        # 获取所有 el-select-dropdown 的详细内容
        result = cli.evaluate("""
            () => {
                const result = [];
                const dropdowns = document.querySelectorAll('.el-select-dropdown');

                dropdowns.forEach((dd, idx) => {
                    const style = window.getComputedStyle(dd);
                    const isVisible = style.display !== 'none' && style.visibility !== 'hidden';

                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    const texts = Array.from(items).map(item => item.textContent.trim());

                    // 获取这个 dropdown 的父级信息
                    let parentInfo = 'unknown';
                    if (dd.previousElementSibling) {
                        parentInfo = dd.previousElementSibling.className.substring(0, 50);
                    }

                    result.push({
                        idx: idx,
                        visible: isVisible,
                        parentClass: parentInfo,
                        itemCount: items.length,
                        items: texts.slice(0, 10)
                    });
                });

                return result;
            }
        """)

        print("=" * 60)
        print("每个 el-select-dropdown 的内容：")
        print("=" * 60)
        for dd in result:
            marker = "【可见】" if dd['visible'] else "【隐藏】"
            print(f"\nDropdown {dd['idx']} {marker}")
            print(f"  父级: {dd['parentClass']}")
            print(f"  选项数: {dd['itemCount']}")
            print(f"  选项: {dd['items']}")

        cli.screenshot("d:/filework/excel-to-diagram/test_results/final_04_each_dropdown.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
