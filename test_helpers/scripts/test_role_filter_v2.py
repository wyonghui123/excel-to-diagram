import sys
sys.path.insert(0, '.')

from test_helpers.browser_auth_cli import PlaywrightCLI
import time

cli = PlaywrightCLI()

print("Step 1: 执行 dev-login 认证")
try:
    cli.request('http://localhost:3010/api/v1/auth/dev-login?username=admin')
    print("  dev-login 请求成功")
except Exception as e:
    print(f"  dev-login 失败: {e}")

print("\nStep 2: 打开浏览器并导航到首页")
cli.goto('http://localhost:3004/')
time.sleep(3)

print("\nStep 3: 截图查看首页")
cli.screenshot('role_step1_home.png')

print("\nStep 4: 使用 router.push 导航到角色管理页面")
result = cli.evaluate("""
    () => {
        try {
            const router = document.querySelector('#app').__vue_app__
                .config.globalProperties.$router
            router.push('/system/role')
            return { success: true }
        } catch (e) {
            return { success: false, error: e.message }
        }
    }
""")
print(f"  导航结果: {result}")

time.sleep(3)

print("\nStep 5: 截图查看角色列表页面")
cli.screenshot('role_step2_list.png')

print("\nStep 6: 查找系统角色列的配置")
config_result = cli.evaluate("""
    () => {
        // 尝试从 Vue app 获取列配置
        const app = document.querySelector('#app')?.__vue_app__
        if (!app) {
            return { found: false, message: 'Vue app not found' }
        }

        const pinia = app.config.globalProperties.$pinia

        // 获取 metaList store
        const metaListStore = pinia._s.get('metaList')

        if (metaListStore) {
            const columns = metaListStore.columns || []
            const isSystemCol = columns.find(col => col.prop === 'is_system')

            return {
                found: true,
                hasMetaList: true,
                columnCount: columns.length,
                isSystemColumn: isSystemCol,
                allColumns: columns.map(c => ({
                    prop: c.prop,
                    label: c.label,
                    filter_type: c.filter_type,
                    filterable: c.filterable,
                    filter_options: c.filter_options
                }))
            }
        }

        return {
            found: true,
            hasMetaList: false,
            message: 'metaList store not found'
        }
    }
""")

print(f"  列配置: {config_result}")

print("\nStep 7: 查找并点击过滤图标")
click_result = cli.evaluate("""
    () => {
        // 查找包含"系统角色"文本的表头单元格
        const headers = document.querySelectorAll('.el-table__header th')
        let targetIndex = -1
        let filterIcon = null

        headers.forEach((header, index) => {
            const text = header.textContent.trim()
            if (text.includes('系统角色')) {
                targetIndex = index
                // 查找过滤图标
                filterIcon = header.querySelector('.table-header-filter-icon, .filter-trigger, [class*="filter"]')
            }
        })

        if (targetIndex === -1) {
            return { found: false, message: '未找到系统角色列' }
        }

        // 尝试点击过滤图标
        if (filterIcon) {
            filterIcon.click()
            return { found: true, clicked: 'filterIcon', iconClass: filterIcon.className }
        } else {
            // 如果没有找到图标，尝试点击整个单元格
            const header = headers[targetIndex]
            header.click()
            return { found: true, clicked: 'header', hasIcon: false }
        }
    }
""")

print(f"  点击结果: {click_result}")

time.sleep(2)

print("\nStep 8: 截图查看过滤面板")
cli.screenshot('role_step3_filter_panel.png')

print("\nStep 9: 检查过滤面板的类型")
panel_result = cli.evaluate("""
    () => {
        // 查找下拉选择框
        const selects = document.querySelectorAll('.el-select, [class*="select-dropdown"]')
        // 查找文本输入框
        const inputs = document.querySelectorAll('input[placeholder*="搜索"], input[placeholder*="输入"]')

        // 查找 TableHeaderFilter 组件实例
        const allElements = document.querySelectorAll('*')
        let filterComponents = []

        allElements.forEach(el => {
            if (el.__vueParentComponent) {
                const componentType = el.__vueParentComponent.type
                if (componentType && (componentType.name === 'TableHeaderFilter' || componentType.__name === 'TableHeaderFilter')) {
                    filterComponents.push({
                        props: el.__vueParentComponent.props,
                        // 简化 props 输出
                        filterType: el.__vueParentComponent.props?.filterType,
                        options: el.__vueParentComponent.props?.options
                    })
                }
            }
        })

        return {
            selectCount: selects.length,
            inputCount: inputs.length,
            inputPlaceholders: Array.from(inputs).map(i => i.placeholder),
            filterComponents: filterComponents,
            // 也检查所有可见的 input 元素
            visibleInputs: Array.from(document.querySelectorAll('input:not([type="hidden"])'))
                .filter(i => i.offsetParent !== null)  // 只保留可见元素
                .map(i => ({
                    placeholder: i.placeholder,
                    type: i.type
                }))
        }
    }
""")

print(f"  面板检查结果:")
print(f"    - 下拉选择框数量: {panel_result['selectCount']}")
print(f"    - 文本输入框数量: {panel_result['inputCount']}")
print(f"    - 输入框 placeholder: {panel_result['inputPlaceholders']}")
print(f"    - TableHeaderFilter 组件: {len(panel_result['filterComponents'])} 个")
for i, comp in enumerate(panel_result['filterComponents'][:3]):  # 只显示前3个
    print(f"      [{i}] filterType: {comp['filterType']}, options: {comp['options']}")

print("\nStep 10: 再次检查 Vue 组件中的 is_system 列配置")
final_check = cli.evaluate("""
    () => {
        const app = document.querySelector('#app')?.__vue_app__
        if (!app) return { error: 'Vue app not found' }

        const pinia = app.config.globalProperties.$pinia
        const metaListStore = pinia._s.get('metaList')

        if (!metaListStore) return { error: 'metaList store not found' }

        const isSystemCol = metaListStore.columns?.find(col => col.prop === 'is_system')

        return {
            is_system_column: isSystemCol,
            columns_with_filter: metaListStore.columns?.filter(c => c.filterable).map(c => ({
                prop: c.prop,
                filter_type: c.filter_type
            }))
        }
    }
""")

print(f"  is_system 列配置: {final_check}")

print("\n测试完成，截图保存在:")
print("  - role_step1_home.png")
print("  - role_step2_list.png")
print("  - role_step3_filter_panel.png")

cli.close()
