"""检查 Vue 组件中的数据"""
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

        # 检查 Vue 组件中的数据
        print("\n3. 检查 Vue 组件中的 visibleColumns...")
        data = cli.evaluate('''() => {
            // 找到 el-table 组件
            const table = document.querySelector('.el-table');
            if (!table) return { error: 'No table' };

            // 尝试找到 Vue 组件实例
            const vueInstance = table.__vueParentComponent;
            if (!vueInstance) return { error: 'No Vue instance' };

            // 向上遍历找到有 visibleColumns 的组件
            let current = vueInstance;
            let depth = 0;
            while (current && depth < 20) {
                const ctx = current.setupState;
                if (ctx && ctx.visibleColumns) {
                    const cols = ctx.visibleColumns;
                    if (cols && cols.value) {
                        return {
                            found: true,
                            columns: cols.value.map(c => ({
                                key: c.key,
                                prop: c.prop,
                                label: c.label,
                                filter_type: c.filter_type,
                                valueHelpConfig: c.valueHelpConfig ? '有' : '无'
                            }))
                        };
                    }
                }
                current = current.parent;
                depth++;
            }

            return { error: 'No visibleColumns found', depth };
        }''')
        print(f"Vue data: {data}")

        # 检查是否有 parent_id 或 manager_id 列
        for col in data.get('columns', []):
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
