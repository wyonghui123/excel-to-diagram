"""
精准诊断：追踪 checkbox 点击 → handleBoCheck → handleObjectScopeChange 完整事件链
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
        print("[1] 产品/版本已选择")

        # 诊断：检查 OSS 树节点
        oss_info = page.evaluate("""() => {
            const trees = document.querySelectorAll('.el-tree')
            let ossTree = null
            for (const tree of trees) {
                const parent = tree.closest('.collapsible-panel')
                if (parent) {
                    const header = parent.querySelector('.collapsible-panel__header')
                    if (header && header.textContent.includes('对象范围')) {
                        // 展开面板
                        if (parent.classList.contains('is-collapsed')) header.click()
                        ossTree = tree
                        break
                    }
                }
            }
            if (!ossTree) return { error: 'no OSS tree' }

            // 获取 Vue 组件实例
            const vnode = ossTree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store

            const nodes = []
            for (const [key, node] of Object.entries(store?.nodesMap || {})) {
                nodes.push({
                    key: key.substring(0, 40),
                    name: (node.data?.name || '').substring(0, 30),
                    type: node.data?.type || '?',
                    isLeaf: node.isLeaf,
                    expanded: node.expanded,
                    visible: node.visible !== false,
                    checkbox: !!document.querySelector(`.el-tree-node[data-key="${key}"] .el-checkbox__input`)
                })
            }

            return {
                totalNodes: nodes.length,
                typeCounts: {
                    domain: nodes.filter(n => n.type === 'domain').length,
                    sub_domain: nodes.filter(n => n.type === 'sub_domain').length,
                    service_module: nodes.filter(n => n.type === 'service_module').length,
                    business_object: nodes.filter(n => n.type === 'business_object').length,
                },
                visibleBranch: nodes.filter(n => !n.isLeaf && n.visible).length,
                visibleLeaf: nodes.filter(n => n.isLeaf && n.visible).length,
                samples: nodes.slice(0, 10)
            }
        }""")
        print(f"\n[2] OSS 树诊断:")
        print(f"  总节点: {oss_info.get('totalNodes', 0)}")
        print(f"  类型分布: {oss_info.get('typeCounts', {})}")
        print(f"  可见分支: {oss_info.get('visibleBranch', 0)}")
        print(f"  可见叶子: {oss_info.get('visibleLeaf', 0)}")
        print(f"  前10个节点:")
        for n in oss_info.get('samples', []):
            print(f"    [{n['type']}] {n['name']} isLeaf={n['isLeaf']} visible={n['visible']} cb={n['checkbox']}")

        # 点击"采购管理" checkbox
        print("\n[3] 点击'采购管理'checkbox...")
        click_result = page.evaluate("""() => {
            const treeEl = document.querySelector('.collapsible-panel .el-tree')
            if (!treeEl) return { error: 'no tree' }

            const allNodes = treeEl.querySelectorAll('.el-tree-node')
            let target = null
            for (const node of allNodes) {
                const label = node.querySelector('.el-tree-node__label')
                if (label && (label.textContent || '').includes('采购管理')) {
                    target = node
                    break
                }
            }
            if (!target) {
                // 列出所有可见节点
                const names = [...allNodes].map(n => {
                    const label = n.querySelector('.el-tree-node__label')
                    const style = window.getComputedStyle(n)
                    return (label?.textContent || '').substring(0, 30) + (style.display === 'none' ? ' [隐藏]' : '')
                }).filter(Boolean)
                return { error: '采购管理 not found', allNames: names.slice(0, 20) }
            }

            // 检查节点状态
            const isExpanded = !target.classList.contains('is-leaf') && target.querySelector('.el-tree-node__expand-icon:not(.is-leaf)')
            const label = target.querySelector('.el-tree-node__label')
            console.log('[TEST] 找到采购管理:', label?.textContent, 'expanded:', !!isExpanded)

            // 先展开
            const expandIcon = target.querySelector('.el-tree-node__expand-icon')
            if (expandIcon && !expandIcon.classList.contains('expanded')) {
                expandIcon.click()
            }

            // 尝试多种点击方式
            const checkbox = target.querySelector('.el-checkbox')
            const checkboxInput = target.querySelector('.el-checkbox__input')
            const content = target.querySelector('.el-tree-node__content')

            if (checkboxInput && !checkboxInput.classList.contains('is-checked')) {
                checkboxInput.click()
                return { clicked: 'el-checkbox__input', label: label?.textContent?.substring(0, 30) }
            }
            if (checkbox && !checkbox.classList.contains('is-checked')) {
                checkbox.click()
                return { clicked: 'el-checkbox', label: label?.textContent?.substring(0, 30) }
            }
            if (content) {
                content.click()
                return { clicked: 'el-tree-node__content', label: label?.textContent?.substring(0, 30) }
            }
            return { error: 'could not click', hasCheckboxInput: !!checkboxInput, hasCheckbox: !!checkbox }
        }""")
        print(f"  结果: {json.dumps(click_result, ensure_ascii=False)}")
        time.sleep(3)

        # 检查点击后的状态
        after_state = page.evaluate("""() => {
            const treeEl = document.querySelector('.collapsible-panel .el-tree')
            if (!treeEl) return { error: 'no tree' }

            const vnode = treeEl.__vueParentComponent
            const ctx = vnode?.setupState

            // 检查 checkedBoIds
            const checkedBoIds = ctx?.checkedBoIds?.value || ctx?.checkedBoIds || []

            // 检查 selectedBoIds (scopeSource)
            let current = vnode
            let scopeSource = null
            while (current) {
                const s = current.setupState
                if (s?.scopeSource) { scopeSource = s.scopeSource; break }
                current = current.parent
            }

            const ssBoIds = scopeSource?.selectedBoIds?.value || scopeSource?.selectedBoIds || []
            const ssDomainIds = scopeSource?.selectedDomainIds?.value || scopeSource?.selectedDomainIds || []

            // 检查 USE_FILTERSOURCE
            const useFS = import.meta.env.VITE_FEATURE_SCOPETREE_FILTERSOURCE

            return {
                checkedBoIds,
                ssBoIds,
                ssDomainIds,
                USE_FILTERSOURCE: typeof useFS === 'string' ? useFS : String(useFS),
                // 检查树组件的 checked 状态
                getCheckedKeys: treeEl.__vueParentComponent?.exposed?.getCheckedKeys?.() || []
            }
        }""")
        print(f"\n[4] 点击后状态:")
        for k, v in after_state.items():
            print(f"  {k}: {v}")

        # 截图
        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_precise.png')

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
