"""测试 FK value_help 多选功能"""
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

        # 点击父组列的 filter-trigger
        print("3. 点击父组列的 filter-trigger...")
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
        page.wait_for_timeout(1000)
        cli.screenshot('vh_step1.png')

        # 检查 popover 内容
        popover = cli.evaluate('''() => {
            const panel = document.querySelector('.filter-panel');
            if (!panel) return { hasPanel: false };

            const hasValueHelp = !!panel.querySelector('.value-help-field');
            const hasSelect = !!panel.querySelector('.el-select');
            const hasInput = !!panel.querySelector('.el-input');

            return {
                hasPanel: true,
                hasValueHelp,
                hasSelect,
                hasInput
            };
        }''')
        print(f"Popover: {popover}")

        if popover.get('hasValueHelp'):
            print("\n[OK] FK value_help 组件已正确显示！")

            # 检查是否有 el-select（多选）
            select_info = cli.evaluate('''() => {
                const select = document.querySelector('.filter-panel .el-select');
                if (!select) return { exists: false };
                return {
                    exists: true,
                    isMultiple: select.classList.contains('is-multiple'),
                    hasCollapseTags: select.classList.contains('collapse-tags')
                };
            }''')
            print(f"Select: {select_info}")

            if select_info.get('exists') and select_info.get('isMultiple'):
                print("\n[OK] 多选功能已启用！")
                return True
            else:
                print("\n[WARNING] 多选功能未启用")
                return False
        else:
            print("\n[X] FK value_help 组件未正确显示")
            return False

    except Exception as e:
        print(f"测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cli.close()

if __name__ == '__main__':
    print("=" * 60)
    print("测试 FK value_help 多选功能")
    print("=" * 60)

    result = test()

    print("\n" + "=" * 60)
    print(f"测试结果: {'PASS' if result else 'FAIL'}")
    print("=" * 60)
