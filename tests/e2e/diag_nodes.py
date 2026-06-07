"""
诊断脚本：检查关系范围树的节点
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
            if (products.length === 0) return
            vc.selectProduct(products[0])
            await new Promise(r => setTimeout(r, 2000))
            const versions = vc.versions?.value || vc.versions || []
            if (versions.length === 0) return
            vc.selectVersion(versions[0])
        }""")
        time.sleep(5)

        # 选择对象范围"销售管理"
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
                            if (content && content.textContent.includes('销售管理')) {
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

        # 列出所有节点
        nodes_info = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return { error: 'no tree' }
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return { error: 'no store' }

            const nodes = []
            for (const [key, node] of Object.entries(store.nodesMap || {})) {
                nodes.push({
                    key: key.substring(0, 50),
                    name: (node.data?.name || '').substring(0, 30),
                    isLeaf: node.isLeaf,
                    expanded: node.expanded,
                    visible: node.visible,
                    checked: node.checked
                })
            }

            // 按名称排序
            nodes.sort((a, b) => (a.name || '').localeCompare(b.name || ''))

            return { total: nodes.length, nodes: nodes.slice(0, 30) }
        }""")
        print(f"节点信息:")
        print(f"  总数: {nodes_info.get('total', 0)}")
        print(f"  前30个节点:")
        for n in nodes_info.get('nodes', []):
            flags = []
            if n['isLeaf']: flags.append('leaf')
            if n['expanded']: flags.append('展开')
            if n['checked']: flags.append('勾选')
            if n['visible'] is False: flags.append('隐藏')
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            print(f"    {n['name']}{flag_str}")

        # 截图
        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_nodes.png')

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
