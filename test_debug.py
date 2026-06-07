"""调试 value_help 列 - 强制刷新"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 访问用户与权限管理页面...")

        # 增加重试次数
        for attempt in range(3):
            try:
                page = cli.authenticated_navigate('/user-permission')
                cli.wait_for_timeout(3000)
                break
            except Exception as e:
                print(f"尝试 {attempt + 1} 失败: {e}")
                if attempt < 2:
                    cli.close()
                    cli = PlaywrightCLI()
                else:
                    raise

        # 注入日志收集器（在页面加载后）
        cli.evaluate('''() => {
            window.__logs__ = [];
            const origLog = console.log;
            console.log = function(...args) {
                window.__logs__.push(args.map(a =>
                    typeof a === 'object' ? JSON.stringify(a) : String(a)
                ).join(' '));
                origLog.apply(console, args);
            };
            console.warn('[DEBUG] Logger injected');
        }''')

        # 等待日志注入生效
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
        cli.wait_for_timeout(3000)

        # 检查日志
        print("\n3. 检查控制台日志...")
        logs = cli.evaluate('() => window.__logs__ || []')
        print(f"总日志数: {len(logs)}")

        # 过滤相关日志
        filter_logs = [l for l in logs if 'filterService' in l or 'backfill' in l or 'value_help' in l or 'useMetaList' in l or 'apiFilterConfigs' in l]
        print(f"过滤相关日志: {filter_logs[:20]}")

        # 检查父组和管理员列的 filter_type
        print("\n4. 检查列的 filter_type...")

        # 点击父组列的 filter-trigger
        print("\n5. 点击父组列的 filter-trigger...")
        result = cli.evaluate('''() => {
            const ths = document.querySelectorAll('.el-table__header th');
            for (const th of ths) {
                const text = th.innerText.trim();
                if (text === '父组') {
                    const trigger = th.querySelector('.filter-trigger');
                    if (trigger) {
                        trigger.click();
                        return { clicked: true, column: text };
                    }
                    return { clicked: false, column: text, hasTrigger: false };
                }
            }
            return { clicked: false, reason: 'column not found' };
        }''')
        print(f"点击结果: {result}")
        cli.wait_for_timeout(1000)

        # 检查 popover 内容
        popover = cli.evaluate('''() => {
            const panel = document.querySelector('.filter-panel');
            if (!panel) return { hasPanel: false };
            return {
                hasPanel: true,
                hasValueHelp: !!panel.querySelector('.value-help-field'),
                hasSelect: !!panel.querySelector('.el-select'),
                hasInput: !!panel.querySelector('.el-input'),
                panelHTML: panel.innerHTML.substring(0, 1000)
            };
        }''')
        print(f"Popover: hasPanel={popover.get('hasPanel')}, hasValueHelp={popover.get('hasValueHelp')}, hasSelect={popover.get('hasSelect')}, hasInput={popover.get('hasInput')}")
        if popover.get('hasPanel'):
            print(f"Panel HTML: {popover.get('panelHTML')}")

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
