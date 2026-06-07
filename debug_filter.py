"""详细检查前端 columns 中的 filter_type - 等待页面完全加载"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 访问用户与权限管理页面...")
        cli.authenticated_navigate('/user-permission')

        # 等待表格出现
        print("2. 等待表格加载...")
        cli.wait_for_timeout(5000)

        # 等待 Vue 初始化
        print("3. 等待 Vue 初始化...")
        max_wait = 30
        for i in range(max_wait):
            ready = cli.evaluate('''() => {
                const pinia = window.__pinia__;
                if (!pinia) return false;
                const stores = pinia._s;
                for (const [name, store] of stores) {
                    const state = store.$state || {};
                    if (state.columns && state.columns.length > 0) {
                        return true;
                    }
                }
                return false;
            }''')
            if ready:
                print(f"   Vue 初始化完成，耗时 {i+1} 秒")
                break
            cli.wait_for_timeout(1000)
        else:
            print("   Vue 未初始化")

        cli.screenshot('page.png')

        # 检查 Vue 组件中的 columns
        print("\n4. 检查 Vue 组件中的 columns...")
        columns_info = cli.evaluate('''() => {
            const pinia = window.__pinia__;
            if (!pinia) return { error: 'No Pinia' };

            const stores = pinia._s;
            for (const [name, store] of stores) {
                const state = store.$state || {};
                if (state.columns && state.columns.length > 0) {
                    const statusCol = state.columns.find(c => c.key === 'status' || c.prop === 'status');
                    if (statusCol) {
                        return {
                            storeName: name,
                            statusFilterType: statusCol.filter_type,
                            statusFilterOptions: statusCol.filter_options?.length,
                            allFilterTypes: state.columns.map(c => ({
                                key: c.key || c.prop,
                                filter_type: c.filter_type,
                                filter_options: (c.filter_options || []).length
                            }))
                        };
                    }
                }
            }
            return { error: 'No status column found' };
        }''')
        print(f"Columns 信息: {columns_info}")

        # 如果找到了，打印所有列的 filter_type
        if 'allFilterTypes' in columns_info:
            print("\n所有列的 filter_type:")
            for col in columns_info['allFilterTypes']:
                print(f"  {col['key']}: filter_type={col['filter_type']}, filter_options={col['filter_options']}")

        # 检查 filter-trigger 的 popover 内容
        print("\n5. 点击状态列的 filter-trigger...")
        cli.evaluate('''() => {
            const ths = document.querySelectorAll('.el-table__header th');
            for (const th of ths) {
                if (th.innerText.trim() === '状态') {
                    const trigger = th.querySelector('.filter-trigger');
                    if (trigger) {
                        trigger.click();
                        return true;
                    }
                }
            }
            return false;
        }''')
        cli.wait_for_timeout(1000)
        cli.screenshot('popover.png')

        # 检查 popover 内容
        popover = cli.evaluate('''() => {
            const panel = document.querySelector('.filter-panel');
            if (!panel) return { hasPanel: false };
            return {
                hasPanel: true,
                hasSelect: !!panel.querySelector('.el-select'),
                hasInput: !!panel.querySelector('.el-input'),
                panelHTML: panel.innerHTML.substring(0, 1000)
            };
        }''')
        print(f"\nPopover: hasPanel={popover.get('hasPanel')}, hasSelect={popover.get('hasSelect')}, hasInput={popover.get('hasInput')}")
        if popover.get('hasPanel'):
            print(f"Panel HTML: {popover.get('panelHTML', '')[:500]}")

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
    test()
