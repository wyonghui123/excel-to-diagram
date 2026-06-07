"""检查 TableHeaderFilter 组件的 props 和控制台日志"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 访问用户与权限管理页面...")

        page = cli.authenticated_navigate('/user-permission')
        cli.wait_for_timeout(3000)

        # 等待页面完全加载
        cli.wait_for_timeout(2000)

        # 注入日志收集器（在页面加载后）
        print("\n2. 注入日志收集器...")
        cli.evaluate('''() => {
            window.__logs__ = window.__logs__ || [];
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
            console.log('[TEST] Logger injected at', Date.now());
        }''')

        # 点击用户组管理 Tab
        print("\n3. 点击用户组管理 Tab...")
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

        # 获取日志
        print("\n4. 获取控制台日志...")
        logs = cli.evaluate('() => window.__logs__ || []')
        print(f"总日志数: {len(logs)}")

        # 过滤相关日志
        enrich_logs = [l for l in logs if 'enrichColumnsWithFieldMeta' in l.get('message', '')]
        print(f"\n_enrichColumnsWithFieldMeta 相关日志: {len(enrich_logs)}")
        for log in enrich_logs:
            print(f"  [{log['method']}] {log['message']}")

        # 过滤 useMetaList 相关日志
        meta_logs = [l for l in logs if 'useMetaList' in l.get('message', '')]
        print(f"\nuseMetaList 相关日志: {len(meta_logs)}")
        for log in meta_logs[-20:]:  # 只显示最后20条
            print(f"  [{log['method']}] {log['message'][:200]}")

        # 检查 TableHeaderFilter 组件的 props
        print("\n5. 检查 TableHeaderFilter 组件的 props...")
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
