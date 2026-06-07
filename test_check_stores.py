"""检查所有 Pinia stores"""
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

        # 检查所有 Pinia stores
        print("\n3. 检查所有 Pinia stores...")
        stores = cli.evaluate('''() => {
            const app = document.querySelector('#app')?.__vue_app__
            if (!app) return { error: 'No Vue app' };

            const pinia = app.config.globalProperties.$pinia
            if (!pinia) return { error: 'No Pinia' };

            const storeNames = [];
            pinia._s.forEach((store, name) => {
                const state = store.$state || {};
                const keys = Object.keys(state);
                storeNames.push({
                    name,
                    stateKeys: keys,
                    hasColumns: keys.includes('columns'),
                    hasMetaList: keys.includes('metaList') || keys.includes('metaConfig')
                });
            });

            return { storeNames };
        }''')
        print(f"Stores: {stores}")

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
