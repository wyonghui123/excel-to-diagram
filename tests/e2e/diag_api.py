"""
诊断：检查 API 返回的子域和服务模块数据
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

        # 选择产品/版本
        page.evaluate("""async () => {
            const selects = document.querySelectorAll('.el-select')
            const comp = selects[0].__vueParentComponent
            let current = comp
            let vc = null
            while (current) {
                const ctx = current.setupState
                if (ctx && ctx.versionContext) { vc = ctx.versionContext; break }
                current = current.parent
            }
            if (!vc) return
            const products = vc.products?.value || vc.products || []
            let product = products.find(p => p.id === 1 || (p.name || '').includes('供应链'))
            if (!product) product = products[0]
            vc.selectProduct(product)
            await new Promise(r => setTimeout(r, 3000))
            const versions = vc.versions?.value || vc.versions || []
            let version = versions.find(v => v.id === 1 || v.id === 2 || (v.name || '').includes('v1.0'))
            if (!version) version = versions[0]
            vc.selectVersion(version)
        }""")
        time.sleep(5)

        # 获取 versionContext 中的 versionId
        vc_info = page.evaluate("""() => {
            const selects = document.querySelectorAll('.el-select')
            const comp = selects[0].__vueParentComponent
            let current = comp
            let vc = null
            while (current) {
                const ctx = current.setupState
                if (ctx && ctx.versionContext) { vc = ctx.versionContext; break }
                current = current.parent
            }
            if (!vc) return { error: 'no vc' }
            const sv = vc.selectedVersion?.value || vc.selectedVersion
            const sp = vc.selectedProduct?.value || vc.selectedProduct
            return {
                versionId: sv?.id,
                versionName: sv?.name,
                productId: sp?.id,
                productName: sp?.name
            }
        }""")
        print(f"[1] versionContext: {json.dumps(vc_info, ensure_ascii=False)}")

        version_id = vc_info.get('versionId')

        # 直接通过 fetch 测试 API
        api_tests = page.evaluate(f"""async () => {{
            const versionId = {version_id}

            const results = {{}}

            // 测试 domains
            const dResp = await fetch(`/api/v2/bo/domain?version_id=${{versionId}}&page_size=1000`, {{ credentials: 'include' }})
            const dData = await dResp.json()
            const domains = dData.data?.items || dData.data || []
            results.domainCount = domains.length

            // 测试 sub_domains
            const sdResp = await fetch(`/api/v2/bo/sub_domain?version_id=${{versionId}}&page_size=1000`, {{ credentials: 'include' }})
            const sdData = await sdResp.json()
            const subDomains = sdData.data?.items || sdData.data || []
            results.subDomainCount = subDomains.length
            if (subDomains.length > 0) {{
                results.subDomainSample = subDomains.slice(0, 3).map(s => ({{
                    id: s.id, name: s.name, domain_id: s.domain_id, version_id: s.version_id
                }}))
            }}

            // 测试 service_modules
            const smResp = await fetch(`/api/v2/bo/service_module?version_id=${{versionId}}&page_size=5000`, {{ credentials: 'include' }})
            const smData = await smResp.json()
            const serviceModules = smData.data?.items || smData.data || []
            results.serviceModuleCount = serviceModules.length
            if (serviceModules.length > 0) {{
                results.serviceModuleSample = serviceModules.slice(0, 3).map(s => ({{
                    id: s.id, name: s.name, sub_domain_id: s.sub_domain_id, version_id: s.version_id
                }}))
            }}

            // 测试不带 version_id 的所有子域
            const sdAllResp = await fetch(`/api/v2/bo/sub_domain?page_size=1000`, {{ credentials: 'include' }})
            const sdAllData = await sdAllResp.json()
            const allSubDomains = sdAllData.data?.items || sdAllData.data || []
            results.allSubDomainCount = allSubDomains.length
            if (allSubDomains.length > 0) {{
                results.allSubDomainSample = allSubDomains.slice(0, 3).map(s => ({{
                    id: s.id, name: s.name, domain_id: s.domain_id, version_id: s.version_id
                }}))
            }}

            // 测试不带 version_id 的所有服务模块
            const smAllResp = await fetch(`/api/v2/bo/service_module?page_size=5000`, {{ credentials: 'include' }})
            const smAllData = await smAllResp.json()
            const allServiceModules = smAllData.data?.items || smAllData.data || []
            results.allServiceModuleCount = allServiceModules.length

            return results
        }}""")

        print(f"\n[2] API 测试 (version_id={version_id}):")
        for k, v in api_tests.items():
            if isinstance(v, list):
                print(f"  {k}: {v}")
            else:
                print(f"  {k}: {v}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
