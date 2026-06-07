"""检查 auth store 状态"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 访问首页...")

        page = cli._ensure_browser()
        page.goto("http://localhost:3004", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(5000)

        # 检查 #app
        print("\n2. 检查 #app...")
        app_exists = page.evaluate('''() => !!document.querySelector('#app')''')
        print(f"  #app exists: {app_exists}")

        vue_app = page.evaluate('''() => !!document.querySelector('#app')?.__vue_app__''')
        print(f"  __vue_app__ exists: {vue_app}")

        # 如果 __vue_app__ 不存在，等待更长时间
        if not vue_app:
            print("  等待 Vue 应用挂载...")
            for i in range(10):
                page.wait_for_timeout(1000)
                vue_app = page.evaluate('''() => !!document.querySelector('#app')?.__vue_app__''')
                print(f"  尝试 {i+1}: __vue_app__ exists: {vue_app}")
                if vue_app:
                    break

        if vue_app:
            # 检查 pinia
            pinia = page.evaluate('''() => {
                const app = document.querySelector('#app').__vue_app__;
                return {
                    exists: true,
                    pinia: !!app.config.globalProperties.$pinia,
                    piniaStores: app.config.globalProperties.$pinia?._s ? Array.from(app.config.globalProperties.$pinia._s.keys()) : []
                }
            }''')
            print(f"  Pinia: {pinia}")

            # 检查 auth store
            auth = page.evaluate('''() => {
                const app = document.querySelector('#app').__vue_app__;
                const pinia = app.config.globalProperties.$pinia;
                const store = pinia?._s?.get('auth');
                return store ? {
                    user: store.user,
                    sessionReady: store.sessionReady
                } : null
            }''')
            print(f"  Auth store: {auth}")
        else:
            print("  Vue 应用未挂载，检查 HTML 内容...")
            html = page.evaluate('() => document.body.innerHTML.substring(0, 500)')
            print(f"  HTML: {html}")

        # 登录
        print("\n3. 登录...")
        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(1000)

        # 返回首页
        print("\n4. 返回首页...")
        page.goto("http://localhost:3004", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        # 检查 auth store
        if vue_app:
            auth = page.evaluate('''() => {
                const app = document.querySelector('#app').__vue_app__;
                const pinia = app.config.globalProperties.$pinia;
                const store = pinia?._s?.get('auth');
                return store ? {
                    user: store.user,
                    sessionReady: store.sessionReady
                } : null
            }''')
            print(f"  Auth store after login: {auth}")

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
