"""检查调试日志"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 登录...")

        page = cli._ensure_browser()

        # 先登录
        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(1000)

        # 创建新上下文
        context = cli._browser.new_context()
        page2 = context.new_page()

        # 在页面加载之前注入日志收集器
        page2.add_init_script("""
            () => {
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
            }
        """)

        print("2. 加载首页...")
        page2.goto("http://localhost:3004", wait_until="networkidle", timeout=30000)
        page2.wait_for_timeout(2000)

        print("3. 导航到用户与权限管理页面...")
        page2.evaluate("""
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
        page2.wait_for_timeout(3000)

        print("4. 点击用户组管理 Tab...")
        page2.evaluate('''() => {
            const tabItems = document.querySelectorAll('[role="tab"]');
            for (const tab of tabItems) {
                if (tab.innerText.trim() === '用户组管理') {
                    tab.click();
                    return true;
                }
            }
            return false;
        }''')
        page2.wait_for_timeout(5000)

        # 获取日志
        print("\n5. 获取日志...")
        logs = page2.evaluate('() => window.__logs__ || []')
        print(f"总日志数: {len(logs)}")

        # 显示 visibleColumns 相关日志
        enrich_logs = [l for l in logs if 'visibleColumns' in l.get('message', '')]
        print(f"\nvisibleColumns 相关日志: {len(enrich_logs)}")
        for log in enrich_logs:
            print(f"  {log['message'][:150]}")

        # 检查表格
        print("\n6. 检查表格...")
        table_info = page2.evaluate('''() => {
            const ths = document.querySelectorAll('.el-table__header th');
            return Array.from(ths).map(th => th.innerText.trim());
        }''')
        print(f"表格列: {table_info}")

        # 检查 TableHeaderFilter props
        print("\n7. 检查 TableHeaderFilter props...")
        props = page2.evaluate('''() => {
            const triggers = document.querySelectorAll('.filter-trigger');
            const results = [];

            triggers.forEach((trigger) => {
                const th = trigger.closest('th');
                const thText = th ? th.innerText.trim() : '';

                let vueInstance = trigger.__vueParentComponent;
                let depth = 0;
                while (vueInstance && depth < 20) {
                    if (vueInstance.type?.name === 'TableHeaderFilter') {
                        results.push({
                            thText,
                            props: vueInstance.props
                        });
                        return;
                    }
                    vueInstance = vueInstance.parent;
                    depth++;
                }
            });

            return results;
        }''')

        print(f"TableHeaderFilter props 数量: {len(props)}")

        # 显示父组和管理员的 props
        for p in props:
            if '父组' in p.get('thText', '') or '管理' in p.get('thText', ''):
                print(f"\n{p['thText']}:")
                print(f"  filterType: {p['props'].get('filterType', 'NOT_SET')}")
                print(f"  valueHelpConfig: {'有' if p['props'].get('valueHelpConfig') else '无'}")

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
