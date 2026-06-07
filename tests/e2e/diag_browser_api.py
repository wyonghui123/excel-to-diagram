"""
诊断脚本：在浏览器中直接测试 API 并追踪 loadTreeData 调用
"""
import sys, os, time, json
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

        # 在浏览器中调用 API
        api_results = page.evaluate("""async () => {
            // 直接调用 v2 API
            const results = {}

            // Sub domains with version_id=1
            let r = await fetch('/api/v2/bo/sub_domain?version_id=1&page_size=1000', { credentials: 'include' })
            let d = await r.json()
            let items = d.data?.items || d.data || []
            results.subDomain_count_v1 = items.length
            if (items.length > 0) {
                results.subDomain_sample_v1 = items.slice(0, 3).map(i => ({
                    id: i.id, name: (i.name||'').substring(0,30),
                    domain_id: i.domain_id, version_id: i.version_id
                }))
            }

            // Service modules with version_id=1
            r = await fetch('/api/v2/bo/service_module?version_id=1&page_size=5000', { credentials: 'include' })
            d = await r.json()
            items = d.data?.items || d.data || []
            results.serviceModule_count_v1 = items.length

            // Domains with version_id=1
            r = await fetch('/api/v2/bo/domain?version_id=1&page_size=1000', { credentials: 'include' })
            d = await r.json()
            items = d.data?.items || d.data || []
            results.domain_count_v1 = items.length
            if (items.length > 0) {
                results.domain_sample_v1 = items.slice(0, 3).map(i => ({
                    id: i.id, name: (i.name||'').substring(0,30),
                    version_id: i.version_id
                }))
            }

            // Check response status for sub_domain
            r = await fetch('/api/v2/bo/sub_domain?version_id=1&page_size=1000', { credentials: 'include' })
            results.subDomain_status = r.status
            results.subDomain_raw = (await r.text()).substring(0, 500)

            return results
        }""")

        print("API 结果 (浏览器内):")
        for k, v in api_results.items():
            print(f"  {k}: {v}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
