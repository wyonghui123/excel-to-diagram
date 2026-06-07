"""
通过 Vue DevTools 协议检查下拉框的 options 来源
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

        # 获取对话框中所有 Vue 组件实例
        vue_components = cli.evaluate("""
            () => {
                // 获取对话框
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return { error: 'no dialog' };

                // Vue 3: 通过 __vueParentComponent 向上查找组件实例
                let comp = dialog.__vueParentComponent;
                if (!comp) comp = dialog.__vue__;

                const results = [];

                // 递归收集组件信息
                function collectComponent(c, depth = 0) {
                    if (depth > 10 || !c) return;

                    const info = {
                        type: c.type?.name || c.type?.__file || String(c.type),
                        props: c.props ? Object.keys(c.props).slice(0, 20) : [],
                        data: c.data ? Object.keys(c.data).slice(0, 10) : [],
                        options: c.options ? c.options?.slice?.(0, 5) : undefined,
                        childrenCount: c.subTree ? 1 : 0
                    };

                    results.push(info);

                    // 遍历子组件（通过 vnode）
                    if (c.subTree) {
                        collectChildren(c.subTree, depth + 1);
                    }
                }

                function collectChildren(vnode, depth = 0) {
                    if (depth > 15 || !vnode) return;

                    if (vnode.component) {
                        collectComponent(vnode.component, depth);
                    }
                    if (vnode.children) {
                        if (Array.isArray(vnode.children)) {
                            vnode.children.forEach(child => collectChildren(child, depth + 1));
                        } else if (vnode.children.component) {
                            collectComponent(vnode.children.component, depth);
                        }
                    }
                }

                collectComponent(comp);

                return results;
            }
        """)

        print("=" * 60)
        print("对话框中 Vue 组件层级：")
        print("=" * 60)
        print(f"vue_components type: {type(vue_components)}")
        if isinstance(vue_components, str):
            print(f"vue_components value: {vue_components[:500]}")
        elif isinstance(vue_components, list):
            for i, comp in enumerate(vue_components):
                if isinstance(comp, dict):
                    print(f"\n组件 {i}:")
                    print(f"  type: {str(comp.get('type', '?'))[:100]}")
                    print(f"  props: {comp.get('props', [])}")
                else:
                    print(f"\n组件 {i}: {str(comp)[:100]}")

        # 截图
        cli.screenshot("d:/filework/excel-to-diagram/test_results/09_vue_components.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
