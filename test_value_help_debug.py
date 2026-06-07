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

        # 检查父组列的 filter-trigger 的 Vue 组件
        print("\n检查父组 filter-trigger 的 Vue 组件...")
        component_info = page.evaluate('''() => {
            for (const th of document.querySelectorAll('.el-table__header th')) {
                if (th.innerText.trim() === '父组') {
                    const trigger = th.querySelector('.filter-trigger');
                    if (!trigger) return { error: 'No trigger' };

                    // 向上遍历查找 TableHeaderFilter
                    let vue = trigger.__vueParentComponent;
                    const ancestors = [];
                    while (vue) {
                        const typeName = vue.type?.name || vue.type?.__name;
                        ancestors.push({
                            type: typeName,
                            props: typeName === 'TableHeaderFilter' ? { ...vue.props } : null
                        });
                        if (typeName === 'TableHeaderFilter') break;
                        vue = vue.parent;
                    }

                    return {
                        found: true,
                        ancestors
                    };
                }
            }
            return { error: 'Column not found' };
        }''')
        print(f"组件信息: {component_info}")

        # 点击触发器
        print("\n点击触发器...")
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

        # 检查所有 popover
        print("\n检查所有 popover...")
        popovers = page.evaluate('''() => {
            const panels = document.querySelectorAll('.filter-panel');
            return Array.from(panels).map(p => ({
                innerHTML: p.innerHTML.substring(0, 300),
                hasValueHelp: !!p.querySelector('.value-help-field'),
                hasElSelect: !!p.querySelector('.el-select'),
                hasElInput: !!p.querySelector('.el-input:not(.el-select .el-input)')
            }));
        }''')
        print(f"Popovers: {popovers}")

        print("\n测试完成!")

    except Exception as e:
        print(f"异常: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    test()
