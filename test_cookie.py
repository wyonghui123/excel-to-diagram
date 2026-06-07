"""测试 cookie 传递问题"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

def test():
    cli = PlaywrightCLI()
    try:
        print("1. 登录并获取 cookie...")

        page = cli._ensure_browser()

        # 访问 dev-login
        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=10000)
        page.wait_for_timeout(1000)

        # 检查 cookie
        cookies = page.context.cookies()
        print(f"Cookies: {len(cookies)} 个")
        for c in cookies:
            print(f"  {c['name']}: {c['value'][:30]}...")

        # 加载首页
        print("\n2. 加载首页...")
        page.goto("http://localhost:3004", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)

        # 检查 Vue 应用
        print("\n3. 检查 Vue 应用...")
        vue_info = page.evaluate("""
            () => {
                const app = document.querySelector('#app');
                return {
                    hasApp: !!app,
                    hasVueApp: !!(app?.__vue_app__),
                    appInnerHTML: app?.innerHTML?.substring(0, 200) || 'empty'
                };
            }
        """)
        print(f"Vue info: {vue_info}")

        # 如果 Vue 应用已挂载，检查 store
        if vue_info.get('hasVueApp'):
            print("\n4. 检查 Pinia store...")
            store_status = page.evaluate("""
                () => {
                    const app = document.querySelector('#app').__vue_app__;
                    const pinia = app?.config?.globalProperties?.$pinia;
                    const auth = pinia?._s?.get('auth');
                    return {
                        user: auth?.user,
                        sessionReady: auth?.sessionReady,
                        loading: auth?.loading
                    };
                }
            """)
            print(f"Store status: {store_status}")

            # 检查 /auth/me API
            print("\n5. 检查 /auth/me API...")
            response = page.evaluate("""
                async () => {
                    try {
                        const r = await fetch('/api/v1/auth/me', { credentials: 'include' });
                        const data = await r.json();
                        return { status: r.status, success: data.success, user: data.data };
                    } catch (e) {
                        return { error: e.toString() };
                    }
                }
            """)
            print(f"Auth /me response: {response}")

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
