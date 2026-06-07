"""
诊断脚本：检查页面 HTML
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI(headless=True)

    try:
        page = cli._ensure_browser()

        # 认证并导航
        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin",
                  wait_until="domcontentloaded", timeout=10000)
        time.sleep(1)
        page.goto("http://localhost:3004/system/archdata",
                  wait_until="networkidle", timeout=30000)
        time.sleep(5)

        page.wait_for_function("""() => {
            const app = document.querySelector('#app')?.__vue_app__
            if (!app) return false
            const pinia = app.config.globalProperties.$pinia
            const store = pinia._s.get('auth')
            return !!(store && store.sessionReady && store.user)
        }""", timeout=15000)

        # 选择产品/版本
        page.evaluate("""async () => {
            const selects = document.querySelectorAll('.el-select')
            const comp = selects[0].__vueParentComponent
            let current = comp
            let vc = null
            while (current) {
                const ctx = current.setupState
                if (ctx && ctx.versionContext) {
                    vc = ctx.versionContext
                    break
                }
                current = current.parent
            }
            if (!vc) return
            const products = vc.products?.value || vc.products || []
            if (products.length === 0) return
            vc.selectProduct(products[0])
            await new Promise(r => setTimeout(r, 2000))
            const versions = vc.versions?.value || vc.versions || []
            if (versions.length === 0) return
            vc.selectVersion(versions[0])
        }""")
        time.sleep(5)

        # 检查页面内容
        html_info = page.evaluate("""() => {
            const body = document.body
            const app = document.querySelector('#app')

            return {
                bodyText: body?.innerText?.substring(0, 500) || '',
                appExists: !!app,
                appChildren: app ? app.children.length : 0,
                appHTML: app ? app.innerHTML.substring(0, 1000) : '',
                hasElLoading: !!document.querySelector('.el-loading'),
                hasElMessage: !!document.querySelector('.el-message'),
                title: document.title
            }
        }""")

        print(f"页面信息:")
        print(f"  标题: {html_info.get('title', '')}")
        print(f"  app 存在: {html_info.get('appExists', False)}")
        print(f"  app 子元素数: {html_info.get('appChildren', 0)}")
        print(f"  有 loading: {html_info.get('hasElLoading', False)}")
        print(f"  有 message: {html_info.get('hasElMessage', False)}")
        print(f"\n  body 文本 (前500字):")
        print(f"  {html_info.get('bodyText', '')}")
        print(f"\n  app HTML (前1000字):")
        print(f"  {html_info.get('appHTML', '')}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
