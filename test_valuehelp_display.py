"""测试 user_group 页面的 value_help 多选显示"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 访问用户与权限管理页面...")
        cli.authenticated_navigate('/user-permission')
        cli.wait_for_timeout(5000)
        cli.screenshot('user_group_page.png')

        # 检查 Tab
        print("2. 检查 Tab...")
        tabs = cli.evaluate('''() => {
            // 检查多种可能的 Tab 选择器
            const selectors = ['.el-tabs__item', '.el-tab-item', '[role="tab"]', '.tab-item'];
            for (const selector of selectors) {
                const items = document.querySelectorAll(selector);
                if (items.length > 0) {
                    return {
                        selector,
                        tabs: Array.from(items).map(tab => tab.innerText.trim())
                    };
                }
            }
            // 检查是否有 Tab 容器
            const tabBar = document.querySelector('.el-tabs__nav, .el-tabs__header');
            return {
                hasTabBar: !!tabBar,
                html: document.body.innerHTML.substring(0, 2000)
            };
        }''')
        print(f"Tab 信息: {tabs}")

        # 点击用户组管理 Tab
        print("\n3. 点击用户组管理 Tab...")
        clicked = cli.evaluate('''() => {
            const tabItems = document.querySelectorAll('[role="tab"]');
            for (const tab of tabItems) {
                if (tab.innerText.trim() === '用户组管理') {
                    tab.click();
                    return true;
                }
            }
            return false;
        }''')
        print(f"点击结果: {clicked}")
        cli.wait_for_timeout(3000)
        cli.screenshot('user_group_tab.png')

        # 检查表格列
        print("\n4. 检查用户组表格...")
        table_info = cli.evaluate('''() => {
            const ths = document.querySelectorAll('.el-table__header th');
            return Array.from(ths).map(th => th.innerText.trim());
        }''')
        print(f"表格列: {table_info}")

        # 找到管理员列的 filter-trigger
        print("\n5. 点击管理员列的 filter-trigger...")
        result = cli.evaluate('''() => {
            const ths = document.querySelectorAll('.el-table__header th');
            for (const th of ths) {
                const text = th.innerText.trim();
                if (text === '管理员' || text === '父组') {
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
        cli.screenshot('valuehelp_popover.png')

        # 检查 popover 内容
        popover = cli.evaluate('''() => {
            const panel = document.querySelector('.filter-panel');
            if (!panel) return { hasPanel: false };
            return {
                hasPanel: true,
                hasValueHelp: !!panel.querySelector('.value-help-field'),
                hasSelect: !!panel.querySelector('.el-select'),
                hasInput: !!panel.querySelector('.el-input'),
                panelHTML: panel.innerHTML.substring(0, 1500)
            };
        }''')
        print(f"Popover: hasPanel={popover.get('hasPanel')}, hasValueHelp={popover.get('hasValueHelp')}, hasSelect={popover.get('hasSelect')}, hasInput={popover.get('hasInput')}")

        if popover.get('hasValueHelp'):
            print("\n6. 测试 value_help 多选...")

            # 检查 el-select
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

            if select_info.get('exists'):
                # 打开下拉
                print("\n7. 打开下拉...")
                cli.click('.filter-panel .el-select .el-input__wrapper')
                cli.wait_for_timeout(1000)
                cli.screenshot('select_dropdown.png')

                # 检查下拉选项
                dropdown = cli.evaluate('''() => {
                    const dropdown = document.querySelector('.el-select-dropdown');
                    const options = dropdown ? dropdown.querySelectorAll('.el-select-dropdown__item') : [];
                    return {
                        hasDropdown: !!dropdown,
                        optionCount: options.length,
                        options: Array.from(options).slice(0, 5).map(o => ({
                            text: o.innerText.trim(),
                            selected: o.classList.contains('selected')
                        }))
                    };
                }''')
                print(f"Dropdown: {dropdown.get('optionCount')} 个选项")

                if dropdown.get('optionCount', 0) > 0:
                    # 选择第一个选项
                    print("\n8. 选择第一个选项...")
                    cli.click('.el-select-dropdown__item:first-child')
                    cli.wait_for_timeout(500)

                    # 检查选中的值
                    selected = cli.evaluate('''() => {
                        const tags = document.querySelectorAll('.filter-panel .el-select__tags .el-tag');
                        return Array.from(tags).map(t => t.innerText.trim());
                    }''')
                    print(f"选中的标签: {selected}")

                    # 点击确定
                    print("\n9. 点击确定...")
                    cli.click('.filter-panel .el-button--primary')
                    cli.wait_for_timeout(1000)
                    cli.screenshot('after_confirm.png')

                    # 检查过滤触发器的显示
                    trigger_text = cli.evaluate('''() => {
                        const trigger = document.querySelector('.filter-trigger');
                        return trigger ? trigger.innerText.trim() : '';
                    }''')
                    print(f"过滤触发器文本: {trigger_text}")

                    if '管理员' in trigger_text:
                        print("[OK] 过滤触发器显示正确！")
                    else:
                        print(f"[WARNING] 过滤触发器显示可能不正确: {trigger_text}")

        print("\n测试完成!")
        return True

    except Exception as e:
        print(f"测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cli.close()

if __name__ == '__main__':
    print("=" * 60)
    print("测试 user_group 页面的 value_help 多选显示")
    print("=" * 60)

    result = test()

    print("\n" + "=" * 60)
    print(f"测试结果: {'PASS' if result else 'FAIL'}")
    print("=" * 60)
