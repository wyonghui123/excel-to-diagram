"""
诊断: 检查 ObjectScopeSection 的 props.versionId 和 loadTreeData 调用
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

        print("[1] 页面已加载")

        # 检查页面状态: 是否显示"请先选择版本"
        body_text = page.evaluate("""() => document.body?.innerText?.substring(0, 300) || ''""")
        print(f"[2] 页面文本: {body_text}")

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

        # 检查 after version selection
        body_text2 = page.evaluate("""() => document.body?.innerText?.substring(0, 300) || ''""")
        print(f"\n[3] 选择版本后页面文本: {body_text2}")

        # 检查 ObjectScopeSection 的 props
        oss_props = page.evaluate("""() => {
            // 展开所有面板
            const panels = document.querySelectorAll('.collapsible-panel')
            for (const panel of panels) {
                const header = panel.querySelector('.collapsible-panel__header')
                if (header && panel.classList.contains('is-collapsed')) header.click()
            }

            const trees = document.querySelectorAll('.el-tree')
            if (!trees.length) return { error: 'no trees', treeCount: trees.length }

            for (const tree of trees) {
                const vnode = tree.__vueParentComponent
                let current = vnode
                while (current) {
                    const ctx = current.setupState
                    if (ctx?.treeData !== undefined) {
                        // This is ObjectScopeSection
                        // Check props
                        const props = current.props
                        return {
                            componentName: current.type?.name || '?',
                            versionId: props?.versionId,
                            treeDataLength: ctx.treeData?.length || (ctx.treeData?.length ?? '??'),
                            firstNode: ctx.treeData?.[0] ? {
                                name: ctx.treeData[0].name,
                                type: ctx.treeData[0].type,
                                childrenCount: ctx.treeData[0].children?.length || 0
                            } : null,
                            tree_children_samples: (ctx.treeData || []).slice(0, 3).map(n => ({
                                name: (n.name||'').substring(0,20),
                                type: n.type,
                                children: n.children ? n.children.length : 0
                            }))
                        }
                    }
                    current = current.parent
                }
            }
            return { error: 'no ObjectScopeSection found', searchedTrees: trees.length }
        }""")

        print(f"\n[4] ObjectScopeSection:")
        for k, v in oss_props.items():
            print(f"  {k}: {v}")

        # Check versionContext singleton
        vc_check = page.evaluate("""() => {
            const selects = document.querySelectorAll('.el-select')
            if (!selects.length) return { error: 'no selects' }
            const comp = selects[0].__vueParentComponent
            let current = comp
            let vc = null
            while (current) {
                const ctx = current.setupState
                if (ctx && ctx.versionContext) { vc = ctx.versionContext; break }
                current = current.parent
            }
            if (!vc) return { error: 'no vc' }

            return {
                selectedProductId: vc.selectedProductId?.value || vc.selectedProductId,
                selectedVersionId: vc.selectedVersionId?.value || vc.selectedVersionId,
                selectedProduct: vc.selectedProduct?.value?.name || vc.selectedProduct?.name,
                selectedVersion: vc.selectedVersion?.value?.name || vc.selectedVersion?.name
            }
        }""")
        print(f"\n[5] versionContext:")
        for k, v in vc_check.items():
            print(f"  {k}: {v}")

        # Screenshot
        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_final_data.png')

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
