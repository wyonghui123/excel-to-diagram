"""检查 TableHeaderFilter 组件的 props"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 访问用户与权限管理页面...")
        page = cli.authenticated_navigate('/user-permission')
        cli.wait_for_timeout(3000)

        # 点击用户组管理 Tab
        print("2. 点击用户组管理 Tab...")
        cli.evaluate('''() => {
            const tabItems = document.querySelectorAll('[role="tab"]');
            for (const tab of tabItems) {
                if (tab.innerText.trim() === '用户组管理') {
                    tab.click();
                    return true;
                }
            }
            return false;
        }''')
        cli.wait_for_timeout(3000)

        # 检查 TableHeaderFilter 组件的 props
        print("\n3. 检查 TableHeaderFilter 组件的 props...")
        props = cli.evaluate('''() => {
            // 找到所有 filter-trigger
            const triggers = document.querySelectorAll('.filter-trigger');
            const results = [];

            triggers.forEach((trigger, idx) => {
                // 找到父 th
                const th = trigger.closest('th');
                const thText = th ? th.innerText.trim() : '';

                // 找到 Vue 组件实例
                let vueInstance = trigger.__vueParentComponent;
                let depth = 0;
                while (vueInstance && depth < 20) {
                    // 检查 props
                    if (vueInstance.props) {
                        results.push({
                            thText,
                            filterType: vueInstance.props.filterType,
                            valueHelpConfig: vueInstance.props.valueHelpConfig ? '有' : '无',
                            valueHelpConfigKeys: vueInstance.props.valueHelpConfig ?
                                Object.keys(vueInstance.props.valueHelpConfig) : []
                        });
                        return;
                    }
                    vueInstance = vueInstance.parent;
                    depth++;
                }

                results.push({
                    thText,
                    error: 'No props found'
                });
            });

            return results;
        }''')

        print(f"TableHeaderFilter props: {props}")

        # 检查父组列的 props
        for p in props:
            if '父组' in p.get('thText', ''):
                print(f"\n父组列的 props:")
                print(f"  filterType: {p.get('filterType')}")
                print(f"  valueHelpConfig: {p.get('valueHelpConfig')}")
                print(f"  valueHelpConfigKeys: {p.get('valueHelpConfigKeys')}")

        print("\n测试完成!")

    except Exception as e:
        print(f"测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cli.close()

if __name__ == '__main__':
    test()
