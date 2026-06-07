"""检查 TableHeaderFilter props"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 访问用户与权限管理页面...")

        page = cli.authenticated_navigate('/user-permission', timeout=60000)
        cli.wait_for_timeout(5000)

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
        cli.wait_for_timeout(5000)

        # 检查 TableHeaderFilter 的组件实例
        print("\n3. 检查 TableHeaderFilter 组件...")
        result = cli.evaluate('''() => {
            const trigger = document.querySelector('.filter-trigger');
            if (!trigger) return { error: 'No trigger found' };

            const th = trigger.closest('th');
            const thText = th ? th.innerText.trim() : '';

            // 向上遍历找到 TableHeaderFilter 组件
            let vueInstance = trigger.__vueParentComponent;
            let depth = 0;
            const ancestors = [];

            while (vueInstance && depth < 20) {
                const type = vueInstance.type?.name || vueInstance.type?.__name || 'unknown';
                const propsKeys = vueInstance.props ? Object.keys(vueInstance.props) : [];
                ancestors.push({
                    depth,
                    type,
                    propsCount: propsKeys.length,
                    propsKeys: propsKeys.slice(0, 5)
                });

                if (type === 'TableHeaderFilter') {
                    return {
                        thText,
                        found: true,
                        depth,
                        props: vueInstance.props
                    };
                }

                vueInstance = vueInstance.parent;
                depth++;
            }

            return {
                thText,
                found: false,
                depth,
                ancestors
            };
        }''')

        print(f"结果: {result}")

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
