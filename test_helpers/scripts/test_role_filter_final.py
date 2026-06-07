import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI
import time

def test_role_filter():
    print("=" * 60)
    print("角色管理页面过滤功能测试")
    print("=" * 60)

    cli = PlaywrightCLI(headless=True)

    print("\n[Step 1-4] 认证 + 导航到角色管理页面")
    page = cli.authenticated_navigate(
        '/system/role',
        wait_for_selector='.el-table',
        timeout=15000
    )
    print("  表格已加载")

    time.sleep(3)

    print("\n[Step 5] 截图查看角色列表页面")
    cli.screenshot('test_role_final_step1_list.png')
    print("  已保存: test_output/test_role_final_step1_list.png")

    print("\n[Step 6] 检查 metaList store 和列配置")
    columns_config = page.evaluate("""
        () => {
            const app = document.querySelector('#app')?.__vue_app__
            if (!app) return { error: 'Vue app not found' }
            const pinia = app.config.globalProperties.$pinia
            const storeNames = Array.from(pinia._s.keys())
            let metaListStore = pinia._s.get('metaList')
            let boCrudStore = pinia._s.get('boCrud')
            return {
                storeNames: storeNames,
                hasMetaList: !!metaListStore,
                hasBoCrud: !!boCrudStore,
                metaListColumns: metaListStore?.columns?.map(c => ({
                    prop: c.prop, label: c.label,
                    filter_type: c.filter_type, filterable: c.filterable,
                    filter_options: c.filter_options
                })),
                boCrudColumns: boCrudStore?.columns?.map(c => ({
                    prop: c.prop, label: c.label,
                    filter_type: c.filter_type, filterable: c.filterable
                }))
            }
        }
    """)
    print(f"  Store 名称: {columns_config['storeNames']}")
    print(f"  有 metaList: {columns_config['hasMetaList']}")
    print(f"  有 boCrud: {columns_config['hasBoCrud']}")

    columns = columns_config.get('metaListColumns') or columns_config.get('boCrudColumns')
    if columns:
        filterable_cols = [c for c in columns if c.get('filterable')]
        for col in filterable_cols:
            print(f"    - {col['prop']} (label: {col['label']}, filter_type: {col['filter_type']})")
        is_system_col = next((c for c in columns if c['prop'] == 'is_system'), None)
        if is_system_col:
            print(f"\n  is_system 列: filterable={is_system_col['filterable']}, filter_type={is_system_col['filter_type']}, filter_options={is_system_col['filter_options']}")
        else:
            print(f"\n  [警告] 未找到 is_system 列!")
    else:
        print(f"\n  [警告] 未找到列配置!")

    print("\n[Step 7] 查找系统角色列")
    table_info = page.evaluate("""
        () => {
            const table = document.querySelector('.el-table')
            if (!table) return { found: false, message: '表格未找到' }
            const headers = table.querySelectorAll('.el-table__header th')
            let targetIndex = -1, headerText = '', filterIcon = null
            headers.forEach((header, index) => {
                const text = header.textContent.trim()
                if (text.includes('系统角色')) {
                    targetIndex = index; headerText = text
                    filterIcon = header.querySelector('.table-header-filter-icon, .filter-trigger, [class*="filter"]')
                }
            })
            if (targetIndex === -1) return {
                found: false, message: '系统角色列未找到',
                allHeaders: Array.from(headers).map(h => h.textContent.trim())
            }
            return {
                found: true, headerText: headerText, index: targetIndex,
                hasFilterIcon: !!filterIcon,
                filterIconHTML: filterIcon?.outerHTML?.substring(0, 200)
            }
        }
    """)
    if table_info['found']:
        print(f"  找到系统角色列: {table_info['headerText']}")
        print(f"  有过滤图标: {table_info['hasFilterIcon']}")
    else:
        print(f"  [警告] {table_info['message']}")

    print("\n[Step 8] 点击过滤图标")
    click_result = page.evaluate("""
        () => {
            const table = document.querySelector('.el-table')
            if (!table) return { success: false, message: '表格未找到' }
            const headers = table.querySelectorAll('.el-table__header th')
            for (let header of headers) {
                if (header.textContent.trim().includes('系统角色')) {
                    const filterIcon = header.querySelector('.table-header-filter-icon, .filter-trigger, [class*="filter"]')
                    if (filterIcon) { filterIcon.click(); return { success: true, clicked: 'filterIcon' } }
                    header.click(); return { success: true, clicked: 'header' }
                }
            }
            return { success: false, message: '系统角色列未找到' }
        }
    """)
    print(f"  点击结果: {click_result}")
    time.sleep(2)

    print("\n[Step 9] 截图查看过滤面板")
    cli.screenshot('test_role_final_step2_filter.png')
    print("  已保存: test_output/test_role_final_step2_filter.png")

    print("\n[Step 10] 检查过滤面板类型")
    panel_info = page.evaluate("""
        () => {
            const selects = document.querySelectorAll('.el-select')
            const inputs = document.querySelectorAll('input[placeholder*="搜索"], input[placeholder*="输入"], input[placeholder*="filter"]')
            let filterComponents = []
            document.querySelectorAll('*').forEach(el => {
                if (el.__vueParentComponent) {
                    const comp = el.__vueParentComponent
                    const type = comp.type
                    if (type && (type.name === 'TableHeaderFilter' || type.__name === 'TableHeaderFilter')) {
                        filterComponents.push({
                            props: { filterType: comp.props?.filterType, options: comp.props?.options, placeholder: comp.props?.placeholder }
                        })
                    }
                }
            })
            return {
                selectCount: selects.length, inputCount: inputs.length,
                inputPlaceholders: Array.from(inputs).map(i => i.placeholder),
                filterComponents: filterComponents
            }
        }
    """)
    print(f"  下拉选择框数量: {panel_info['selectCount']}")
    print(f"  文本输入框数量: {panel_info['inputCount']}")
    for i, comp in enumerate(panel_info['filterComponents'][:5]):
        print(f"    [{i}] filterType: {comp['props']['filterType']}, placeholder: {comp['props']['placeholder']}")

    is_select_filter = panel_info['selectCount'] > 0 and panel_info['inputCount'] == 0
    is_text_filter = panel_info['inputCount'] > 0 and any('搜索' in p or '输入' in p for p in panel_info['inputPlaceholders'])

    if is_select_filter:
        print("\n  [DECORATIVE] 过滤面板正确显示为下拉选择框!")
    elif is_text_filter:
        print("\n  [DECORATIVE] 过滤面板错误显示为文本输入框!")
    else:
        print(f"\n  ? 过滤面板类型不确定")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

    cli.close()

if __name__ == '__main__':
    test_role_filter()