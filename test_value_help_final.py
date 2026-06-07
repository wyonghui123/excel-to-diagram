"""测试 FK value_help 多选功能"""
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

        # 点击父组列的 filter-trigger
        print("点击父组列的 filter-trigger...")
        page.evaluate('''() => {
            for (const th of document.querySelectorAll('.el-table__header th')) {
                if (th.innerText.trim() === '父组') {
                    const trigger = th.querySelector('.filter-trigger');
                    if (trigger) { trigger.click(); }
                    return;
                }
            }
        }''')
        page.wait_for_timeout(2000)

        # 检查 popover - 查找包含 value-help-field 的 popover
        print("检查 popover...")
        popover = page.evaluate('''() => {
            const panels = document.querySelectorAll('.filter-panel');
            for (const panel of panels) {
                if (panel.querySelector('.value-help-field')) {
                    const vhField = panel.querySelector('.value-help-field');
                    const select = vhField.querySelector('.el-select');
                    const innerInput = vhField.querySelector('.el-input');

                    return {
                        hasPanel: true,
                        hasValueHelp: true,
                        hasElSelect: !!select,
                        hasInnerInput: !!innerInput,
                        isMultiple: select?.classList.contains('is-multiple') || false,
                        hasCollapseTags: select?.classList.contains('collapse-tags') || false,
                        selectHTML: select?.outerHTML?.substring(0, 500) || 'N/A'
                    };
                }
            }
            return { hasPanel: false };
        }''')
        print(f"Popover: {popover}")

        if popover.get('hasValueHelp'):
            print("\n[OK] FK value_help 组件已正确显示！")

            if popover.get('hasElSelect') and popover.get('isMultiple'):
                print("[OK] 多选功能已启用！")
                return True
            else:
                print("[WARNING] 多选功能未启用")
                print(f"  hasElSelect: {popover.get('hasElSelect')}")
                print(f"  isMultiple: {popover.get('isMultiple')}")
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
