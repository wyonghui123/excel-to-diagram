"""
诊断脚本：检查 selectedBoIds 是否更新
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
                if (ctx && ctx.versionContext) {
                    vc = ctx.versionContext
                    break
                }
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

        # 检查 scopeSource 状态
        before = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return {}
            const vnode = tree.__vueParentComponent

            let current = vnode
            let scopeSource = null
            while (current) {
                const ctx = current.setupState
                if (ctx?.scopeSource) {
                    scopeSource = ctx.scopeSource
                    break
                }
                current = current.parent
            }

            if (!scopeSource) return { error: 'no scopeSource' }

            return {
                selectedBoIds: scopeSource.selectedBoIds?.value || scopeSource.selectedBoIds || [],
                selectedDomainIds: scopeSource.selectedDomainIds?.value || scopeSource.selectedDomainIds || []
            }
        }""")
        print(f"[1] 选择对象范围前:")
        print(f"  selectedBoIds: {before.get('selectedBoIds', [])}")
        print(f"  selectedDomainIds: {before.get('selectedDomainIds', [])}")

        # 选择对象范围
        page.evaluate("""() => {
            const trees = document.querySelectorAll('.el-tree')
            for (const tree of trees) {
                const parent = tree.closest('.collapsible-panel')
                if (parent) {
                    const header = parent.querySelector('.collapsible-panel__header')
                    if (header && header.textContent.includes('对象范围')) {
                        if (parent.classList.contains('is-collapsed')) header.click()
                        const nodes = tree.querySelectorAll('.el-tree-node')
                        for (const node of nodes) {
                            const content = node.querySelector('.el-tree-node__content')
                            if (content && (content.textContent.includes('采购管理') || content.textContent.includes('销售管理'))) {
                                const cb = node.querySelector('.el-checkbox__input')
                                if (cb && !cb.classList.contains('is-checked')) {
                                    cb.click()
                                    return
                                }
                            }
                        }
                    }
                }
            }
        }""")
        time.sleep(4)

        # 再次检查
        after = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return {}
            const vnode = tree.__vueParentComponent

            let current = vnode
            let scopeSource = null
            while (current) {
                const ctx = current.setupState
                if (ctx?.scopeSource) {
                    scopeSource = ctx.scopeSource
                    break
                }
                current = current.parent
            }

            if (!scopeSource) return { error: 'no scopeSource' }

            return {
                selectedBoIds: scopeSource.selectedBoIds?.value || scopeSource.selectedBoIds || [],
                selectedDomainIds: scopeSource.selectedDomainIds?.value || scopeSource.selectedDomainIds || []
            }
        }""")
        print(f"\n[2] 选择对象范围后:")
        print(f"  selectedBoIds: {after.get('selectedBoIds', [])}")
        print(f"  selectedDomainIds: {after.get('selectedDomainIds', [])}")

        # 展开关系范围面板
        page.evaluate("""() => {
            const panels = document.querySelectorAll('.collapsible-panel')
            for (const panel of panels) {
                const header = panel.querySelector('.collapsible-panel__header')
                if (header && header.textContent.includes('关系范围')) {
                    if (panel.classList.contains('is-collapsed')) header.click()
                }
            }
        }""")
        time.sleep(4)

        # 检查树节点
        tree_check = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return {}
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return {}

            return { nodeCount: Object.keys(store.nodesMap || {}).length }
        }""")
        print(f"\n[3] 关系范围树节点数: {tree_check.get('nodeCount', 0)}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
