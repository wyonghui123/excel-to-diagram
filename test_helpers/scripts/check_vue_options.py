"""
深入检查下拉框选项的 Vue 数据
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

        # 检查对话框中的 Vue 组件实例
        vue_data = cli.evaluate("""
            () => {
                // 找到对话框
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return { error: 'no dialog' };

                // 获取 Vue 实例
                const vueInstance = dialog.__vue_app__ || dialog.__vue_parent__;
                if (!vueInstance) return { error: 'no vue instance' };

                // 尝试获取 el-select 的 Vue 实例
                const select = dialog.querySelector('.el-select');
                if (!select) return { error: 'no select' };

                // Vue 3: el-select 的实例在 __vueParentComponent 或 __vueInstance
                let selectVue = select.__vueParentComponent;
                if (!selectVue) {
                    const vueEl = select.__vue__;
                    if (vueEl) selectVue = vueEl;
                }

                if (!selectVue) return { error: 'no select vue instance' };

                // 获取 options
                const options = selectVue.props?.options || selectVue.options || selectVue.$props?.options;

                return {
                    hasVue: true,
                    selectVueKeys: selectVue ? Object.keys(selectVue).slice(0, 30) : [],
                    props: selectVue?.props ? Object.keys(selectVue.props) : [],
                    optionsCount: Array.isArray(options) ? options.length : 'N/A',
                    optionsSample: Array.isArray(options) ? options.slice(0, 5).map(o => ({
                        value: o.value,
                        label: o.label,
                        icon: o.icon
                    })) : options
                };
            }
        """)

        print("=" * 60)
        print("Vue 组件数据：")
        print("=" * 60)
        print(json.dumps(vue_data, indent=2, ensure_ascii=False))

        # 检查 _dynamicCategoryConfig
        dynamic_config = cli.evaluate("""
            () => {
                // 尝试找到 annotationConfig 模块的运行时数据
                const win = window;

                // 检查是否有全局的 _dynamicCategoryConfig
                const keys = Object.keys(win).filter(k => k.includes('dynamic') || k.includes('Category') || k.includes('annotation'));
                return keys;
            }
        """)
        print(f"\n动态配置相关全局变量: {dynamic_config}")

        # 检查 CATEGORY_CONFIG 的运行时值
        cat_config = cli.evaluate("""
            () => {
                // 尝试导入 annotationConfig
                return new Promise((resolve) => {
                    // 在模块系统中查找
                    const mod = window.__vite_module_cache__;
                    if (mod) {
                        for (const [url, val] of mod) {
                            if (url.includes('annotationConfig')) {
                                resolve({ found: true, url, type: typeof val });
                            }
                        }
                    }

                    // 尝试动态 import
                    import('/src/composables/useMermaid/annotation/annotationConfig.js')
                        .then(m => {
                            const cfg = m.CATEGORY_CONFIG;
                            resolve({
                                important: cfg.important,
                                warning: cfg.warning,
                                info: cfg.info,
                                tip: cfg.tip
                            });
                        })
                        .catch(e => resolve({ error: e.message }));
                });
            }
        """)

        print(f"\nCATEGORY_CONFIG 运行时值: {json.dumps(cat_config, indent=2, ensure_ascii=False)}")

        # 截图
        cli.screenshot("d:/filework/excel-to-diagram/test_results/06_vue_data.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
