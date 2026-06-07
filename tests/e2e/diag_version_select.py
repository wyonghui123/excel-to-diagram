"""
诊断脚本：检查产品/版本选择
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

        # 检查 versionContext 状态
        vc_state = page.evaluate("""() => {
            const selects = document.querySelectorAll('.el-select')
            if (selects.length === 0) return { error: 'no selects' }

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

            const products = vc.products?.value || vc.products || []
            const versions = vc.versions?.value || vc.versions || []
            const selectedProduct = vc.selectedProduct?.value || vc.selectedProduct
            const selectedVersion = vc.selectedVersion?.value || vc.selectedVersion

            return {
                productCount: products.length,
                versionCount: versions.length,
                selectedProduct: selectedProduct ? { id: selectedProduct.id, name: selectedProduct.name } : null,
                selectedVersion: selectedVersion ? { id: selectedVersion.id, name: selectedVersion.name } : null,
                products: products.slice(0, 3).map(p => ({ id: p.id, name: p.name }))
            }
        }""")
        print(f"[1] versionContext 状态:")
        print(f"  产品数: {vc_state.get('productCount', 0)}")
        print(f"  版本数: {vc_state.get('versionCount', 0)}")
        print(f"  已选产品: {vc_state.get('selectedProduct', None)}")
        print(f"  已选版本: {vc_state.get('selectedVersion', None)}")
        print(f"  产品列表: {vc_state.get('products', [])}")

        # 选择产品/版本
        print(f"\n[2] 选择产品/版本...")
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

            const products = vc.products?.value || vc.products || []
            if (products.length === 0) return { error: 'no products' }

            // 选择有版本的产品（ID=1 或名称包含"供应链"）
            let product = products.find(p => p.id === 1 || (p.name || '').includes('供应链'))
            if (!product) product = products[0]
            console.log('[TEST] 选择产品:', product.name, 'id:', product.id)
            vc.selectProduct(product)

            await new Promise(r => setTimeout(r, 3000))

            const versions = vc.versions?.value || vc.versions || []
            if (versions.length === 0) return { error: 'no versions after selectProduct', product: product.name }

            // 选择有领域数据的版本（ID=1 或 ID=2 或名称包含"v1.0"）
            let version = versions.find(v => v.id === 1 || v.id === 2 || (v.name || '').includes('v1.0'))
            if (!version) version = versions[0]
            console.log('[TEST] 选择版本:', version.name, 'id:', version.id)
            vc.selectVersion(version)

            await new Promise(r => setTimeout(r, 2000))

            const selectedProduct = vc.selectedProduct?.value || vc.selectedProduct
            const selectedVersion = vc.selectedVersion?.value || vc.selectedVersion

            return {
                success: true,
                selectedProduct: selectedProduct ? selectedProduct.name : null,
                selectedVersion: selectedVersion ? selectedVersion.name : null
            }
        }""")
        print(f"  结果: {json.dumps(result, ensure_ascii=False)}")
        time.sleep(3)

        # 再次检查页面
        page_state = page.evaluate("""() => {
            const selects = document.querySelectorAll('.el-select')
            const selectedTexts = []

            for (const sel of selects) {
                const input = sel.querySelector('.el-input__inner')
                if (input) {
                    selectedTexts.push(input.value || input.placeholder || '')
                }
            }

            return {
                selectedTexts,
                bodyText: document.body?.innerText?.substring(0, 300) || ''
            }
        }""")
        print(f"\n[3] 页面状态:")
        print(f"  下拉框选中: {page_state.get('selectedTexts', [])}")
        print(f"  body 文本: {page_state.get('bodyText', '')[:200]}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
