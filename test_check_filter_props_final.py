"""检查 TableHeaderFilter 组件的 props"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 访问用户与权限管理页面...")

        page = cli._ensure_browser()

        # 登录
        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(1000)

        # 加载首页
        page.goto("http://localhost:3004", wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(3000)

        # 等待 Vue 应用加载
        page.wait_for_selector("#app", state="attached", timeout=10000)
        page.wait_for_timeout(2000)

        # SPA 内部导航
        page.evaluate("""
            () => {
                const app = document.querySelector('#app');
                if (app && app.__vue_app__) {
                    const router = app.__vue_app__.config.globalProperties.$router;
                    if (router) {
                        router.push('/user-permission');
                    }
                }
            }
        """)
        page.wait_for_timeout(5000)

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
        page.wait_for_timeout(3000)

        # 检查 TableHeaderFilter 的 props
        print("\n3. 检查 TableHeaderFilter props...")
        props = cli.evaluate('''() => {
            const triggers = document.querySelectorAll('.filter-trigger');
            const results = [];

            triggers.forEach((trigger) => {
                const th = trigger.closest('th');
                const thText = th ? th.innerText.trim() : '';

                let vueInstance = trigger.__vueParentComponent;
                let depth = 0;
                while (vueInstance && depth < 20) {
                    if (vueInstance.props) {
                        results.push({
                            thText,
                            filterType: vueInstance.props.filterType,
                            valueHelpConfig: vueInstance.props.valueHelpConfig ? '有' : '无',
                            allProps: vueInstance.props
                        });
                        return;
                    }
                    vueInstance = vueInstance.parent;
                    depth++;
                }
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
                all_props = p.get('allProps', {})
                print(f"  allProps: {all_props}")

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
