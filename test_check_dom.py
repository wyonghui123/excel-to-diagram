"""检查 DOM 中的表格列"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 访问用户与权限管理页面...")
        page = cli.authenticated_navigate('/user-permission')
        cli.wait_for_timeout(3000)

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

        # 检查 DOM 中的表格列
        print("\n3. 检查表格列的 DOM...")
        columns = cli.evaluate('''() => {
            const ths = document.querySelectorAll('.el-table__header th');
            return Array.from(ths).map(th => {
                const text = th.innerText.trim();
                const filterTrigger = th.querySelector('.filter-trigger');
                const cell = th.querySelector('.cell');

                // 获取 th 的所有属性
                const attrs = {};
                for (const attr of th.attributes) {
                    attrs[attr.name] = attr.value;
                }

                // 获取 cell 的内容
                const cellHtml = cell ? cell.innerHTML.substring(0, 500) : '';

                return {
                    text,
                    hasFilterTrigger: !!filterTrigger,
                    attrs,
                    cellHtml: cellHtml.replace(/\\s+/g, ' ')
                };
            });
        }''')

        for col in columns:
            print(f"\n列: {col['text']}")
            print(f"  hasFilterTrigger: {col['hasFilterTrigger']}")
            print(f"  attrs: {col['attrs']}")

            # 检查是否有父组或管理员列
            if '父' in col['text'] or '管理' in col['text']:
                print(f"  cellHtml: {col['cellHtml']}")

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
