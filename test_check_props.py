"""检查 visibleColumns"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        page = cli._ensure_browser()

        # 登录
        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(1000)

        # 加载首页
        page.goto("http://localhost:3004", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        # 等待 Vue 应用
        page.wait_for_selector("#app", timeout=10000)
        page.wait_for_timeout(2000)

        # 导航
        page.evaluate("() => { document.querySelector('#app').__vue_app__.config.globalProperties.$router.push('/user-permission'); }")
        page.wait_for_timeout(5000)

        # 点击用户组管理 Tab
        page.evaluate('''() => {
            for (const tab of document.querySelectorAll('[role="tab"]')) {
                if (tab.innerText.trim() === '用户组管理') { tab.click(); return; }
            }
        }''')
        page.wait_for_timeout(5000)

        # 检查 MetaListPage 的 visibleColumns
        print("\n检查 MetaListPage visibleColumns...")
        columns = page.evaluate('''() => {
            const table = document.querySelector('.el-table');
            if (!table) return { error: 'No table found' };

            // 找到 MetaListPage 组件
            let el = table;
            let metaListPage = null;

            for (let i = 0; i < 15 && el; i++) {
                const vue = el.__vueParentComponent;
                if (vue && vue.type && (vue.type.name === 'MetaListPage' || vue.type.__name === 'MetaListPage')) {
                    metaListPage = vue;
                    break;
                }
                el = el.parentElement;
            }

            if (!metaListPage) return { error: 'MetaListPage not found' };

            // 获取 setupState
            const setupState = metaListPage.setupState;
            if (!setupState) return { error: 'No setupState' };

            const cols = setupState.visibleColumns;
            if (!cols) return { error: 'No visibleColumns' };

            const colsValue = cols.value || cols;
            if (!Array.isArray(colsValue)) return { error: 'cols.value is not an array', type: typeof colsValue };

            return {
                success: true,
                columns: colsValue.map(c => ({
                    key: c.key || c.prop,
                    label: c.label,
                    filter_type: c.filter_type,
                    valueHelpConfig: c.valueHelpConfig ? '有' : '无'
                }))
            };
        }''')

        print(f"结果: {columns}")

        # 找到 FK 列
        if columns.get('success'):
            for col in columns['columns']:
                key = col.get('key', '')
                if 'parent' in key.lower() or 'manager' in key.lower():
                    print(f"\nFK 列: {col}")

        # 检查 TableHeaderFilter 的 props
        print("\n检查 TableHeaderFilter props...")
        props = page.evaluate('''() => {
            const triggers = document.querySelectorAll('.filter-trigger');
            const results = [];

            for (const trigger of triggers) {
                const th = trigger.closest('th');
                const thText = th?.innerText?.trim() || '';

                let vue = trigger.__vueParentComponent;
                while (vue) {
                    if (vue.type && (vue.type.name === 'TableHeaderFilter' || vue.type.__name === 'TableHeaderFilter')) {
                        results.push({
                            thText,
                            filterType: vue.props.filterType,
                            valueHelpConfig: vue.props.valueHelpConfig ? '有' : '无'
                        });
                        break;
                    }
                    vue = vue.parent;
                }
            }

            return results;
        }''')

        print("\n所有列的 filterType:")
        for p in props:
            print(f"  {p['thText']}: filterType={p['filterType']}, valueHelpConfig={p['valueHelpConfig']}")

        print("\n测试完成!")

    except Exception as e:
        print(f"异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    test()
