"""
检查 el-option 的 Vue 实例数据，找出 emoji 来源
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

        # 点击下拉框
        cli.click(".el-dialog .el-select")
        cli.wait_for_timeout(1500)

        # 获取所有 el-option 的文本和父级 el-select-dropdown 的 id/class
        options_analysis = cli.evaluate("""
            () => {
                const results = [];
                const dropdowns = document.querySelectorAll('.el-select-dropdown');

                dropdowns.forEach((dd, ddIdx) => {
                    const ddStyle = window.getComputedStyle(dd);
                    if (ddStyle.display === 'none') {
                        results.push({ dropdownIdx: ddIdx, visible: false, items: [] });
                        return;
                    }
                    if (ddStyle.visibility === 'hidden') {
                        results.push({ dropdownIdx: ddIdx, visible: false, items: [] });
                        return;
                    }

                    const items = dd.querySelectorAll('.el-select-dropdown__item');
                    const itemData = [];

                    items.forEach((item, itemIdx) => {
                        // 尝试获取 Vue 实例
                        let vueComp = item.__vueParentComponent;
                        if (!vueComp) vueComp = item.__vue__;

                        // 获取文本
                        const text = item.textContent.trim();

                        // 获取父级
                        let parentSelect = dd.previousElementSibling;
                        if (!parentSelect) {
                            parentSelect = dd.closest('.el-select');
                        }

                        itemData.push({
                            idx: itemIdx,
                            text: text,
                            vueType: vueComp?.type?.name || vueComp?.type?.__file || (vueComp?.type ? String(vueComp.type).substring(0, 50) : 'N/A'),
                            parentDropdownIdx: ddIdx,
                            // 尝试从 Vue 实例获取 option 数据
                            optionValue: vueComp?.props?.value,
                            optionLabel: vueComp?.props?.label,
                            optionIcon: vueComp?.props?.icon
                        });
                    });

                    results.push({
                        dropdownIdx: ddIdx,
                        visible: true,
                        ddClass: dd.className,
                        ddStyle: { display: ddStyle.display, visibility: ddStyle.visibility },
                        items: itemData
                    });
                });

                return results;
            }
        """)

        print("=" * 60)
        print("下拉框和选项分析：")
        print("=" * 60)
        print(json.dumps(options_analysis, indent=2, ensure_ascii=False)[:3000])

        # 截图
        cli.screenshot("d:/filework/excel-to-diagram/test_results/10_options_vue.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
