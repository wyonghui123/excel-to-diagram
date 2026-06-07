"""检查 columns 数组中的值"""
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

        # 检查 Pinia store 中的 columns
        print("\n3. 检查 Pinia store 中的 columns...")
        columns = cli.evaluate('''() => {
            const app = document.querySelector('#app')?.__vue_app__
            if (!app) return { error: 'No Vue app' };

            const pinia = app.config.globalProperties.$pinia
            if (!pinia) return { error: 'No Pinia' };

            const stores = pinia._s;
            for (const [name, store] of stores) {
                const state = store.$state || {};
                if (state.columns && state.columns.length > 0) {
                    return {
                        storeName: name,
                        columns: state.columns.map(c => ({
                            key: c.key,
                            prop: c.prop,
                            label: c.label,
                            filter_type: c.filter_type,
                            valueHelpConfig: c.valueHelpConfig ? '有' : '无'
                        }))
                    };
                }
            }
            return { error: 'No columns found' };
        }''')
        print(f"Store columns: {columns}")

        # 检查是否有 parent_id 或 manager_id 列
        for col in columns.get('columns', []):
            key = col.get('key', '') or col.get('prop', '')
            if 'parent' in key.lower() or 'manager' in key.lower():
                print(f"\nFK 列: {col}")

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
