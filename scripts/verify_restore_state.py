"""前端验证: 架构管理 -> 图表展示 -> 返回 状态恢复"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from test_helpers.browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI()

# 1. 导航到架构数据管理
print("=== Step 1: 导航到架构数据管理 ===")
result = cli.authenticated_navigate('/system/archdata', wait_for_selector='.momp-container', timeout=15000)
print(f"  导航结果: {'OK' if result.get('success') else result}")

# 截图初始状态
cli.screenshot('d:/filework/verify_step1_archdata.png')
print("  截图: verify_step1_archdata.png")

# 2. 检查产品/版本是否已加载
state = cli.evaluate("""
    () => {
        const app = document.querySelector('#app')?.__vue_app__
        if (!app) return { error: 'no app' }
        const pinia = app.config.globalProperties.$pinia
        if (!pinia) return { error: 'no pinia' }
        // 查找可能的 store
        const stores = {}
        pinia._s.forEach((store, key) => {
            stores[key] = Object.keys(store.$state || {})
        })
        return {
            stores: Object.keys(pinia._s._map || {}),
            url: window.location.href,
            sessionStorage: Object.keys(sessionStorage)
        }
    }
""")
print(f"  Store 信息: {state}")

# 3. 查看 activeTab 和 scopeIds 状态
state2 = cli.evaluate("""
    () => {
        // 找到 MultiObjectManagementPage 的 setup 数据
        // 由于 Vue 3 不容易直接访问 setup, 我们通过 DOM 推断
        const tabs = document.querySelectorAll('.el-tabs__item, .momp-tab, [role="tab"]')
        const activeTabs = []
        tabs.forEach(t => {
            if (t.classList.contains('is-active') || t.getAttribute('aria-selected') === 'true') {
                activeTabs.push(t.textContent.trim())
            }
        })
        return {
            activeTabs,
            tabsCount: tabs.length,
            bodyClasses: document.body.className,
            url: window.location.href
        }
    }
""")
print(f"  Tab 状态: {state2}")

cli.close()
print("=== 完成 ===")
