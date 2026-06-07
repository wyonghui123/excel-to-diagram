"""检查 TableHeaderFilter 组件的 props"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 访问用户与权限管理页面...")

        page = cli.authenticated_navigate('/user-permission', timeout=30000)
        cli.wait_for_timeout(5000)

        # 注入日志收集器
        print("  注入日志收集器...")
        cli.evaluate('''() => {
            window.__logs__ = [];
            ['log', 'warn', 'error'].forEach(method => {
                const orig = console[method];
                console[method] = (...args) => {
                    window.__logs__.push({
                        method,
                        message: args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ')
                    });
                    orig.apply(console, args);
                };
            });
            console.log('[TEST] Logger ready');
        }''')
        cli.wait_for_timeout(1000)

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

        # 检查 Vue 组件中的 columns
        print("\n3. 检查 columns 中的 filter_type...")
        columns = cli.evaluate('''() => {
            const app = document.querySelector('#app')?.__vue_app__
            if (!app) return { error: 'No Vue app' };

            // 检查 Pinia stores
            const pinia = app.config.globalProperties.$pinia
            if (!pinia) return { error: 'No Pinia' };

            const stores = pinia._s;
            for (const [name, store] of stores) {
                const state = store.$state || {};

                // 检查是否有 columns
                if (state.columns && state.columns.length > 0) {
                    const parentCol = state.columns.find(c => c.key === 'parent_id' || c.prop === 'parent_id');
                    const managerCol = state.columns.find(c => c.key === 'manager_id' || c.prop === 'manager_id');

                    return {
                        storeName: name,
                        parent_id: parentCol ? {
                            filter_type: parentCol.filter_type,
                            valueHelpConfig: parentCol.valueHelpConfig ? '有' : '无'
                        } : null,
                        manager_id: managerCol ? {
                            filter_type: managerCol.filter_type,
                            valueHelpConfig: managerCol.valueHelpConfig ? '有' : '无'
                        } : null
                    };
                }
            }
            return { error: 'No columns found' };
        }''')
        print(f"Columns: {columns}")

        # 检查 TableHeaderFilter 的 props
        print("\n4. 检查 TableHeaderFilter props...")
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

        # 检查日志
        print("\n5. 检查日志...")
        logs = cli.evaluate('() => window.__logs__ || []')
        print(f"总日志数: {len(logs)}")
        enrich_logs = [l for l in logs if 'enrichColumnsWithFieldMeta' in l.get('message', '') or 'backfill' in l.get('message', '')]
        print(f"Enrich 相关日志: {len(enrich_logs)}")
        for log in enrich_logs[-10:]:
            print(f"  [{log['method']}] {log['message'][:200]}")

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
