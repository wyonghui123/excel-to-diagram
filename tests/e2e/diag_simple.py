"""
简化诊断脚本：测试点击勾选后的展开状态
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

        # 等待 Vue app
        page.wait_for_function("""() => {
            const app = document.querySelector('#app')?.__vue_app__
            if (!app) return false
            const pinia = app.config.globalProperties.$pinia
            const store = pinia._s.get('auth')
            return !!(store && store.sessionReady && store.user)
        }""", timeout=15000)
        print("[1] Vue app ready")

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
        print("[2] 产品/版本已选择")

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
        print("[3] 对象范围已选择")

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
        print("[4] 关系范围面板已展开")

        # 手动展开"同服务模块"
        page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return
            for (const [key, node] of Object.entries(store.nodesMap || {})) {
                const name = node.data?.name || ''
                if (name.includes('同服务模块') && !node.expanded) {
                    node.expand()
                }
            }
        }""")
        time.sleep(1)

        # 记录点击前展开状态
        before = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return {}
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return {}
            let count = 0
            const names = []
            for (const [, n] of Object.entries(store.nodesMap || {})) {
                if (n.expanded && !n.isLeaf) {
                    count++
                    names.push(n.data?.name || '')
                }
            }
            return { count, names }
        }""")
        print(f"[5] 点击前展开: {json.dumps(before, ensure_ascii=False)}")

        # 点击勾选叶子节点
        page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return
            for (const [key, node] of Object.entries(store.nodesMap || {})) {
                if (node.isLeaf && node.visible !== false && !node.checked) {
                    const parent = node.parent
                    if (parent && (parent.data?.name || '').includes('同服务模块')) {
                        const el = document.querySelector(
                            `.el-tree-node[data-key="${key}"] .el-checkbox__input`
                        )
                        if (el) {
                            el.click()
                            return
                        }
                    }
                }
            }
        }""")
        time.sleep(2)

        # 记录点击后展开状态
        after = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return {}
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return {}
            let count = 0
            const names = []
            for (const [, n] of Object.entries(store.nodesMap || {})) {
                if (n.expanded && !n.isLeaf) {
                    count++
                    names.push(n.data?.name || '')
                }
            }
            return { count, names }
        }""")
        print(f"[6] 点击后展开: {json.dumps(after, ensure_ascii=False)}")

        # 判断结果
        if before.get('count', 0) > 0 and after.get('count', 0) == 0:
            print("\n[X] 问题1 FAIL: 点击勾选后所有节点被收起")
        elif before.get('count', 0) == after.get('count', 0):
            print("\n[OK] 问题1 PASS: 展开状态保持")
        else:
            print(f"\n[WARNING] 问题1: 部分节点变化 {before.get('count', 0)} -> {after.get('count', 0)}")

        # 截图
        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_simple.png')

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
