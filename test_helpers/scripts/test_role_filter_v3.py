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
time.sleep(2)

print("\nStep 3: 检查认证状态")
auth_check = cli.evaluate("""
    () => {
        const app = document.querySelector('#app')?.__vue_app__
        if (!app) {
            return { error: 'Vue app not found' }
        }

        const pinia = app.config.globalProperties.$pinia

        // 检查 auth store
        const authStore = pinia._s.get('auth')

        if (!authStore) {
            return { error: 'auth store not found', piniaStores: Array.from(pinia._s.keys()) }
        }

        return {
            loggedIn: authStore.loggedIn,
            user: authStore.user?.username,
            sessionReady: authStore.sessionReady,
            token: authStore.token ? 'exists' : 'none'
        }
    }
""")

print(f"  认证状态: {auth_check}")

print("\nStep 4: 如果未登录，尝试自动登录")
if auth_check.get('loggedIn') != True:
    print("  当前未登录，尝试填写登录表单")

    # 检查是否有登录表单
    login_check = cli.evaluate("""
        () => {
            const usernameInput = document.querySelector('input[placeholder*="用户名"], input[placeholder*="账号"]')
            const passwordInput = document.querySelector('input[placeholder*="密码"]')
            const loginBtns = document.querySelectorAll('.el-button')
            const loginBtn = Array.from(loginBtns).find(btn => btn.textContent.includes('登录'))

            return {
                hasUsernameInput: !!usernameInput,
                hasPasswordInput: !!passwordInput,
                hasLoginBtn: !!loginBtn,
                usernamePlaceholder: usernameInput?.placeholder,
                passwordPlaceholder: passwordInput?.placeholder
            }
        }
    """)

    print(f"  登录表单检查: {login_check}")

    if login_check['hasUsernameInput'] and login_check['hasPasswordInput']:
        print("  填写登录表单")
        cli.fill('input[placeholder*="用户名"], input[placeholder*="账号"]', 'admin')
        cli.fill('input[placeholder*="密码"]', 'admin')
        time.sleep(0.5)

        # 点击登录按钮
        login_btn = cli.evaluate("""
            () => {
                const loginBtns = document.querySelectorAll('.el-button')
                const btn = Array.from(loginBtns).find(b => b.textContent.includes('登录'))
                if (btn) {
                    btn.click()
                    return 'clicked'
                }
                return 'not found'
            }
        """)
        print(f"  点击登录按钮: {login_btn}")

        time.sleep(3)

print("\nStep 5: 再次检查认证状态")
auth_check2 = cli.evaluate("""
    () => {
        const app = document.querySelector('#app')?.__vue_app__
        if (!app) {
            return { error: 'Vue app not found' }
        }

        const pinia = app.config.globalProperties.$pinia
        const authStore = pinia._s.get('auth')

        if (!authStore) {
            return { error: 'auth store not found', piniaStores: Array.from(pinia._s.keys()) }
        }

        return {
            loggedIn: authStore.loggedIn,
            user: authStore.user?.username,
            sessionReady: authStore.sessionReady,
            token: authStore.token ? 'exists' : 'none'
        }
    }
""")

print(f"  认证状态: {auth_check2}")

print("\nStep 6: 截图查看当前页面")
cli.screenshot('role_v3_step1_auth.png')

print("\nStep 7: 导航到角色管理页面")
cli.evaluate("""
    () => {
        const router = document.querySelector('#app').__vue_app__
            .config.globalProperties.$router
        router.push('/system/role')
    }
""")

time.sleep(5)

print("\nStep 8: 截图查看角色列表页面")
cli.screenshot('role_v3_step2_list.png')

print("\nStep 9: 查找系统角色列")
column_check = cli.evaluate("""
    () => {
        const app = document.querySelector('#app')?.__vue_app__
        if (!app) return { error: 'Vue app not found' }

        const pinia = app.config.globalProperties.$pinia

        // 查找所有可能的 store
        const storeNames = Array.from(pinia._s.keys())

        // 尝试查找 metaList 或 boCrud store
        let metaListStore = pinia._s.get('metaList')
        let boCrudStore = pinia._s.get('boCrud')
        let roleStore = pinia._s.get('role')

        return {
            storeNames: storeNames,
            hasMetaList: !!metaListStore,
            hasBoCrud: !!boCrudStore,
            hasRole: !!roleStore,
            metaListColumns: metaListStore?.columns?.map(c => ({ prop: c.prop, label: c.label, filter_type: c.filter_type })),
            boCrudState: boCrudStore ? {
                loading: boCrudStore.loading,
                currentView: boCrudStore.currentView
            } : null
        }
    }
""")

print(f"  列配置: {column_check}")

print("\nStep 10: 查找表格中的系统角色列")
table_check = cli.evaluate("""
    () => {
        // 查找表格
        const table = document.querySelector('.el-table')
        if (!table) {
            return { found: false, message: '表格未找到' }
        }

        // 查找表头
        const headers = table.querySelectorAll('.el-table__header th')
        let targetIndex = -1
        let headerText = ''

        headers.forEach((header, index) => {
            const text = header.textContent.trim()
            if (text.includes('系统角色')) {
                targetIndex = index
                headerText = text
            }
        })

        if (targetIndex === -1) {
            return {
                found: false,
                message: '系统角色列未找到',
                allHeaders: Array.from(headers).map(h => h.textContent.trim())
            }
        }

        return {
            found: true,
            headerText: headerText,
            index: targetIndex,
            headerHTML: headers[targetIndex].innerHTML.substring(0, 500)
        }
    }
""")

print(f"  表格检查: {table_check}")

print("\nStep 11: 点击过滤图标")
click_result = cli.evaluate("""
    () => {
        const table = document.querySelector('.el-table')
        if (!table) return { success: false, message: '表格未找到' }

        const headers = table.querySelectorAll('.el-table__header th')

        for (let header of headers) {
            const text = header.textContent.trim()
            if (text.includes('系统角色')) {
                // 查找过滤图标
                const filterIcon = header.querySelector('.table-header-filter-icon, .filter-trigger, [class*="filter"]')
                if (filterIcon) {
                    filterIcon.click()
                    return { success: true, clicked: 'filterIcon' }
                }

                // 如果没有图标，点击整个单元格
                header.click()
                return { success: true, clicked: 'header' }
            }
        }

        return { success: false, message: '系统角色列未找到' }
    }
""")

print(f"  点击结果: {click_result}")

time.sleep(2)

print("\nStep 12: 截图查看过滤面板")
cli.screenshot('role_v3_step3_filter.png')

print("\nStep 13: 检查过滤面板类型")
panel_check = cli.evaluate("""
    () => {
        // 查找下拉选择框
        const selects = document.querySelectorAll('.el-select')
        // 查找文本输入框
        const inputs = document.querySelectorAll('input[placeholder*="搜索"], input[placeholder*="输入"], input[placeholder*="filter"]')

        // 查找 TableHeaderFilter 组件
        const allElements = document.querySelectorAll('*')
        let filterComponents = []

        allElements.forEach(el => {
            if (el.__vueParentComponent) {
                const comp = el.__vueParentComponent
                const type = comp.type
                if (type && (type.name === 'TableHeaderFilter' || type.__name === 'TableHeaderFilter')) {
                    filterComponents.push({
                        props: {
                            filterType: comp.props?.filterType,
                            options: comp.props?.options,
                            placeholder: comp.props?.placeholder
                        }
                    })
                }
            }
        })

        return {
            selectCount: selects.length,
            inputCount: inputs.length,
            inputPlaceholders: Array.from(inputs).map(i => i.placeholder),
            filterComponents: filterComponents
        }
    }
""")

print(f"  面板检查: {panel_check}")

print("\n测试完成")
cli.close()
