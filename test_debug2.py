"""调试 columns.value 中的 filter_type"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 访问用户与权限管理页面...")

        cli.authenticated_navigate('/user-permission')
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

        # 检查 Vue 组件状态
        print("\n3. 检查 Vue 组件中的 columns 状态...")
        columns_state = cli.evaluate('''() => {
            // 尝试从 Pinia store 获取
            const pinia = window.__pinia__;
            if (!pinia) return { error: 'No Pinia' };

            const stores = pinia._s;
            for (const [name, store] of stores) {
                const state = store.$state || {};
                if (state.columns && state.columns.length > 0) {
                    // 找到 parent_id 和 manager_id 列
                    const parentCol = state.columns.find(c => c.key === 'parent_id' || c.prop === 'parent_id');
                    const managerCol = state.columns.find(c => c.key === 'manager_id' || c.prop === 'manager_id');
                    return {
                        storeName: name,
                        columns: state.columns.map(c => ({
                            key: c.key || c.prop,
                            filter_type: c.filter_type,
                            value_help: c.value_help ? '有' : '无',
                            valueHelpConfig: c.valueHelpConfig ? '有' : '无',
                        })),
                        parent_id: parentCol,
                        manager_id: managerCol
                    };
                }
            }
            return { error: 'No columns found' };
        }''')
        print(f"Columns 状态: {columns_state}")

        # 检查父组和管理员列
        for col in columns_state.get('columns', []):
            if 'parent' in col.get('key', '').lower() or 'manager' in col.get('key', '').lower():
                print(f"\n关键列: {col}")

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
