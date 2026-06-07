"""
检查 AppSelect 组件中的 options prop 数据
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

        # 获取 AppSelect 组件实例的 options prop
        appselect_data = cli.evaluate("""
            () => {
                // 找到对话框中的 AppSelect 组件
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return { error: 'no dialog' };

                // 查找所有 el-select 元素
                const selects = dialog.querySelectorAll('.el-select');
                const results = [];

                for (const sel of selects) {
                    // 获取 label
                    let label = '';
                    let parent = sel.parentElement;
                    for (let i = 0; i < 8; i++) {
                        if (!parent) break;
                        const lbl = parent.querySelector('.el-form-item__label');
                        if (lbl) { label = lbl.textContent.trim(); break; }
                        parent = parent.parentElement;
                    }

                    // 获取当前值
                    let currentValue = '';
                    const input = sel.querySelector('.el-input__inner, .el-select__wrapper');
                    if (input) currentValue = input.textContent.trim();

                    // 尝试获取 Vue 组件实例
                    let vueComp = sel.__vueParentComponent || sel.__vue__;

                    // 通过 Vue 3 的 componentInstance 获取 options
                    let vueOptions = null;
                    if (vueComp) {
                        // 尝试从 el-select 的 props 中获取
                        const props = vueComp.props;
                        const $props = vueComp.$props;

                        if (props?.options) {
                            vueOptions = props.options;
                        } else if ($props?.options) {
                            vueOptions = $props.options;
                        }

                        // 尝试通过 parent 获取
                        let parentComp = vueComp;
                        for (let i = 0; i < 5; i++) {
                            if (!parentComp) break;
                            const opts = parentComp.props?.options || parentComp.$props?.options;
                            if (opts) {
                                vueOptions = opts;
                                break;
                            }
                            parentComp = parentComp.parent || parentComp.$parent;
                        }
                    }

                    results.push({
                        label: label,
                        currentValue: currentValue,
                        vueOptionsCount: vueOptions ? vueOptions.length : 'N/A',
                        vueOptionsSample: vueOptions ? vueOptions.slice(0, 5).map(o => ({
                            value: o.value,
                            label: o.label,
                            name: o.name
                        })) : null
                    });
                }

                return results;
            }
        """)

        print("=" * 60)
        print("对话框中 el-select 的 options prop：")
        print("=" * 60)
        print(json.dumps(appselect_data, indent=2, ensure_ascii=False))

        # 也检查 Vue 3 的全局存储
        pinia_data = cli.evaluate("""
            () => {
                try {
                    const app = document.querySelector('#app').__vue_app__;
                    if (!app) return { error: 'no app' };

                    const pinia = app.config.globalProperties.$pinia;
                    if (!pinia) return { error: 'no pinia' };

                    // 尝试找到 archdata 或 archObject 的 store
                    const stores = {};
                    for (const [key, val] of pinia._s) {
                        stores[key] = {
                            hasAnnotationCategories: 'annotationCategories' in val,
                            hasCategory: 'category' in val,
                            keys: Object.keys(val).slice(0, 20)
                        };
                    }
                    return stores;
                } catch (e) {
                    return { error: e.message };
                }
            }
        """)

        print("\n" + "=" * 60)
        print("Pinia 存储中的相关数据：")
        print("=" * 60)
        print(json.dumps(pinia_data, indent=2, ensure_ascii=False))

        # 截图
        cli.screenshot("d:/filework/excel-to-diagram/test_results/11_appselect_options.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
