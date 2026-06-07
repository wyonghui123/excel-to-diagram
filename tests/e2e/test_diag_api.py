"""
诊断脚本 v3: 深入检查 versionContext 的版本加载
"""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI(headless=True)

    try:
        page = cli._ensure_browser()

        # 认证
        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin",
                  wait_until="domcontentloaded", timeout=10000)
        time.sleep(1)

        # 导航到前端
        page.goto("http://localhost:3004/system/archdata",
                  wait_until="domcontentloaded", timeout=10000)
        time.sleep(3)

        page.wait_for_function("""() => {
            const app = document.querySelector('#app')?.__vue_app__
            if (!app) return false
            const pinia = app.config.globalProperties.$pinia
            const store = pinia._s.get('auth')
            return !!(store && store.sessionReady && store.user)
        }""", timeout=15000)

        # 获取 versionContext 并手动调用 fetchVersions
        print("[1] 获取 versionContext...")
        result = page.evaluate("""async () => {
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

            if (!vc) return { error: 'no versionContext' }

            // 获取产品列表
            const products = vc.products?.value || vc.products
            if (!products || products.length === 0) {
                await new Promise(r => setTimeout(r, 3000))
            }
            const pVal = vc.products?.value || vc.products
            if (!pVal || pVal.length === 0) return { error: 'no products after wait' }

            const product = pVal[0]

            // 手动调用 fetchVersions
            const productId = product.id
            const fetchResult = await vc.fetchVersions(productId)

            // 检查版本列表
            const versions = vc.versions?.value || vc.versions

            return {
                product: product.name,
                productId: productId,
                versionCount: versions?.length || 0,
                versions: (versions || []).map(v => ({ id: v.id, name: v.name })),
                fetchResultType: typeof fetchResult
            }
        }""")
        print(f"[1] 结果: {json.dumps(result, ensure_ascii=False)}")

        # 如果版本列表还是空，直接测试 API
        if result.get('versionCount', 0) == 0:
            print("\n[2] 直接测试版本 API...")
            api_result = page.evaluate("""async () => {
                const productId = %d
                const url = '/api/v2/bo/version?product_id=' + productId + '&page_size=100'
                try {
                    const resp = await fetch(url, { credentials: 'include' })
                    const data = await resp.json()
                    return {
                        status: resp.status,
                        url: url,
                        dataType: typeof data.data,
                        dataKeys: data.data ? Object.keys(data.data).slice(0, 10) : [],
                        totalItems: data.data?.items?.length || data.data?.total || 0,
                        rawSnippet: JSON.stringify(data).substring(0, 500)
                    }
                } catch(e) {
                    return { error: e.message }
                }
            }""" % result.get('productId', 0))
            print(f"[2] API 结果: {json.dumps(api_result, ensure_ascii=False)}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
