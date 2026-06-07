"""调试页面加载"""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from test_helpers.browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True)

# Step 1: 认证
print("[1] dev-login via browser...")
page = cli._ensure_browser()
page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin",
          wait_until="domcontentloaded", timeout=10000)
time.sleep(1)

# Step 2: 加载首页
print("[2] 加载首页...")
page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=10000)
time.sleep(3)

# Step 3: 等待 store 就绪
print("[3] 等待 store...")
try:
    page.wait_for_function("""() => {
        const app = document.querySelector('#app')?.__vue_app__
        if (!app) return false
        const pinia = app.config.globalProperties.$pinia
        const store = pinia._s.get('auth')
        return !!(store && store.sessionReady && store.user)
    }""", timeout=15000)
    print("[3] Store ready")
except:
    print("[3] Store not ready, continuing...")

# Step 4: SPA 导航
print("[4] SPA navigate to archdata...")
page.evaluate("""() => {
    const router = document.querySelector('#app').__vue_app__
        .config.globalProperties.$router
    router.push('/system/archdata')
}""")
time.sleep(5)

# Step 5: 检查页面内容
print("[5] 检查页面...")
result = page.evaluate("""() => {
    return {
        url: window.location.href,
        hasTree: !!document.querySelector('.el-tree'),
        hasPanel: !!document.querySelector('.collapsible-panel'),
        hasVersionSelect: !!document.querySelector('.version-select, .el-select'),
        bodyText: document.body?.innerText?.substring(0, 1000),
        allClasses: [...new Set([...document.querySelectorAll('[class]')].map(e => e.className).join(' ').split(' '))].filter(c => c.includes('scope') || c.includes('tree') || c.includes('panel')).slice(0, 20)
    }
}""")
print(f"URL: {result.get('url')}")
print(f"hasTree: {result.get('hasTree')}")
print(f"hasPanel: {result.get('hasPanel')}")
print(f"hasVersionSelect: {result.get('hasVersionSelect')}")
print(f"relevant classes: {result.get('allClasses')}")
print(f"bodyText (first 500): {result.get('bodyText', '')[:500]}")

# 截图
cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/debug_page2.png')
print("Screenshot saved")

cli.close()
