"""
精准诊断 v2：检查 OSS 树数据结构 + 事件链
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

        # 诊断 OSS 树
        oss_info = page.evaluate("""() => {
            // 展开对象范围面板
            const panels = document.querySelectorAll('.collapsible-panel')
            for (const panel of panels) {
                const header = panel.querySelector('.collapsible-panel__header')
                if (header && header.textContent.includes('对象范围')) {
                    if (panel.classList.contains('is-collapsed')) header.click()
                }
            }

            const trees = document.querySelectorAll('.el-tree')
            let ossTree = null
            for (const tree of trees) {
                const parent = tree.closest('.collapsible-panel')
                if (parent) {
                    const h = parent.querySelector('.collapsible-panel__header')
                    if (h && h.textContent.includes('对象范围')) {
                        ossTree = tree
                        break
                    }
                }
            }
            if (!trees.length) return { error: 'no trees' }

            const vnode = trees[0].__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store

            // 检查 treeData (原始数据)
            const treeData = store?.data || store?.root?.data || []

            // 递归提取树结构
            function extractTree(nodes, depth) {
                const result = []
                if (!nodes) return result
                for (const n of nodes) {
                    const item = {
                        d: depth,
                        n: (n.data?.name || n.label || '').substring(0, 30),
                        t: n.data?.type || n.type || '?',
                        l: !!n.isLeaf,
                        c: n.childNodes ? n.childNodes.length : (n.children ? n.children.length : 0)
                    }
                    if (depth < 3) {
                        if (n.childNodes?.length) item.children = extractTree(n.childNodes, depth + 1)
                        else if (n.children?.length) item.children = extractTree(n.children, depth + 1)
                    }
                    result.push(item)
                }
                return result
            }

            const rootNodes = store?.root?.childNodes || []
            const structure = extractTree(rootNodes, 0)

            return {
                totalNodes: rootNodes.length,
                treeDataLength: Array.isArray(treeData) ? treeData.length : 'n/a',
                structure: structure.slice(0, 15)
            }
        }""")

        print(f"\n[2] OSS 树结构:")
        def print_tree(nodes, indent=0):
            for n in nodes:
                leaf_str = "[SYMBOL]" if n['l'] else "[SYMBOL]"
                print(f"  {'  ' * indent}{leaf_str} [{n['t']}] {n['n']} (children={n['c']})")
                if n.get('children'):
                    print_tree(n['children'], indent + 1)

        print_tree(oss_info.get('structure', []))

        # 现在点击 checkbox 并追踪
        print("\n[3] 点击 checkbox 并追踪事件链...")
        trace_result = page.evaluate("""() => {
            // 找到 OSS 树组件
            const trees = document.querySelectorAll('.el-tree')
            if (!trees.length) return { error: 'no trees' }

            const treeEl = trees[0]
            const vnode = treeEl.__vueParentComponent
            const ctx = vnode.setupState

            // 检查 USE_FILTERSOURCE
            const useFS = true  // 已知默认 true

            // 找到 ObjectScopeSection 的 setupState 检查 guard
            let guardActive = null
            let hasScopeChangeHandler = false

            // 遍历找到 ObjectScopeSection 的父组件设置
            let current = vnode
            let relationScopeTree = null
            while (current) {
                const s = current.setupState
                if (s?.selectedBoIds !== undefined) {
                    // 这是 RelationScopeTree
                    relationScopeTree = current
                }
                current = current.parent
            }

            // 点击"采购管理" checkbox
            const allTreeNodes = treeEl.querySelectorAll('.el-tree-node')
            let clicked = false
            for (const tn of allTreeNodes) {
                const label = tn.querySelector('.el-tree-node__label')
                if (!label) continue
                const text = label.textContent || ''
                if (text.includes('采购管理')) {
                    const cbInput = tn.querySelector('.el-checkbox__input')
                    if (cbInput) {
                        cbInput.click()
                        clicked = true
                    }
                    break
                }
            }

            return { clicked }
        }""")
        print(f"  点击结果: {json.dumps(trace_result, ensure_ascii=False)}")
        time.sleep(3)

        # 检查点击后的 scopeSource
        after_state = page.evaluate("""() => {
            const trees = document.querySelectorAll('.el-tree')
            const vnode = trees[0].__vueParentComponent

            // 向上找到 RelationScopeTree
            let current = vnode
            let scopeSource = null
            while (current) {
                const s = current.setupState
                if (s?.scopeSource) { scopeSource = s.scopeSource; break }
                current = current.parent
            }

            const result = {
                selectedBoIds: scopeSource?.selectedBoIds?.value || scopeSource?.selectedBoIds || [],
                selectedDomainIds: scopeSource?.selectedDomainIds?.value || scopeSource?.selectedDomainIds || [],
                selectedSubDomainIds: scopeSource?.selectedSubDomainIds?.value || scopeSource?.selectedSubDomainIds || [],
                selectedServiceModuleIds: scopeSource?.selectedServiceModuleIds?.value || scopeSource?.selectedServiceModuleIds || [],
                hasScopeSource: !!scopeSource
            }

            // 也检查树自身的 checkedKeys
            const treeVnode = trees[0].__vueParentComponent
            result.treeCheckedKeys = treeVnode?.exposed?.getCheckedKeys?.() || []

            return result
        }""")

        print(f"\n[4] 点击后 scopeSource:")
        for k, v in after_state.items():
            print(f"  {k}: {v}")

        # 检查关系范围树
        print("\n[5] 检查关系范围面板...")
        rss_info = page.evaluate("""() => {
            // 展开关系范围面板
            const panels = document.querySelectorAll('.collapsible-panel')
            for (const panel of panels) {
                const header = panel.querySelector('.collapsible-panel__header')
                if (header && header.textContent.includes('关系范围')) {
                    if (panel.classList.contains('is-collapsed')) header.click()
                }
            }

            // 找 RSS 树
            const rssTree = document.querySelector('.rss-tree-container .el-tree')
            if (!rssTree) return { error: 'no RSS tree', bodyText: document.body?.innerText?.substring(0, 500) }

            const vnode = rssTree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store

            const nodes = []
            for (const [k, n] of Object.entries(store?.nodesMap || {})) {
                nodes.push({
                    n: (n.data?.name || '').substring(0, 30),
                    t: n.data?.type || '?',
                    l: n.isLeaf,
                    v: n.visible !== false
                })
            }

            return {
                nodeCount: nodes.length,
                samples: nodes.slice(0, 10)
            }
        }""")

        print(f"  RSS 树: {json.dumps(rss_info, ensure_ascii=False)}")

        # 截图
        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_precise2.png')

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
