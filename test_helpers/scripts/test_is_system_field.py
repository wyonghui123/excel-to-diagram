import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI
import time

def test_is_system_field():
    print("=" * 60)
    print("测试 is_system 字段配置")
    print("=" * 60)

    cli = PlaywrightCLI(headless=True)

    print("\n[Step 1-4] 认证 + 导航到角色管理页面")
    page = cli.authenticated_navigate(
        '/system/role',
        wait_for_selector='.el-table',
        timeout=15000
    )
    print("  页面已加载")

    time.sleep(3)

    print("\n[Step 5] 检查过滤配置")
    filter_check = page.evaluate("""
        () => {
            const app = document.querySelector('#app')?.__vue_app__
            if (!app) return { error: 'Vue app not found' }
            const pinia = app.config.globalProperties.$pinia

            let columns = null
            let metaListStore = pinia._s.get('metaList')
            let boCrudStore = pinia._s.get('boCrud')

            if (metaListStore?.columns) {
                columns = metaListStore.columns
            } else if (boCrudStore?.columns) {
                columns = boCrudStore.columns
            }

            if (!columns) return { error: 'columns not found' }

            const isSystemCol = columns.find(c => c.prop === 'is_system' || c.key === 'is_system')
            return {
                found: !!isSystemCol,
                filter_type: isSystemCol?.filter_type,
                filterable: isSystemCol?.filterable,
                filter_options: isSystemCol?.filter_options
            }
        }
    """)
    print(f"  过滤配置检查: {filter_check}")

    print("\n[Step 6] 点击过滤图标")
    page.evaluate("""
        () => {
            const table = document.querySelector('.el-table')
            if (!table) return

            const headers = table.querySelectorAll('.el-table__header th')
            for (let header of headers) {
                if (header.textContent.includes('系统角色')) {
                    const filterIcon = header.querySelector('.table-header-filter-icon')
                    if (filterIcon) {
                        filterIcon.click()
                    }
                }
            }
        }
    """)
    time.sleep(2)

    print("\n[Step 7] 截图查看过滤面板")
    cli.screenshot('test_is_system_filter.png')
    print("  截图已保存: test_is_system_filter.png")

    print("\n[Step 8] 检查过滤面板类型")
    panel_check = page.evaluate("""
        () => {
            const selects = document.querySelectorAll('.el-select')
            const inputs = document.querySelectorAll('input[placeholder*="搜索"], input[placeholder*="输入"]')

            return {
                selectCount: selects.length,
                inputCount: inputs.length,
                inputPlaceholders: Array.from(inputs).map(i => i.placeholder)
            }
        }
    """)
    print(f"  下拉选择框数量: {panel_check['selectCount']}")
    print(f"  文本输入框数量: {panel_check['inputCount']}")
    print(f"  输入框 placeholder: {panel_check['inputPlaceholders']}")

    if panel_check['selectCount'] > 0:
        print("\n[OK] 过滤功能正常！显示为下拉选择框")
    else:
        print("\n[X] 过滤功能异常！显示为文本输入框")

    print("\n[Step 9] 点击第一行的查看按钮，进入详情页面")
    page.evaluate("""
        () => {
            const table = document.querySelector('.el-table')
            if (!table) return

            const rows = table.querySelectorAll('.el-table__body tr')
            if (rows.length > 0) {
                const viewBtn = rows[0].querySelector('.el-button, [class*="action"], [class*="btn"]')
                if (viewBtn) {
                    viewBtn.click()
                }
            }
        }
    """)
    time.sleep(3)

    print("\n[Step 10] 截图查看详情页面")
    cli.screenshot('test_is_system_detail.png')
    print("  截图已保存: test_is_system_detail.png")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

    print("\n请检查截图:")
    print("  - test_is_system_filter.png: 过滤面板")
    print("  - test_is_system_detail.png: 详情页面")

    cli.close()

if __name__ == '__main__':
    test_is_system_field()