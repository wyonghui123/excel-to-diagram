"""
诊断脚本：追踪 filterAndCollapse 调用链
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

        # 注入追踪代码
        print("[1] 注入追踪代码...")
        page.evaluate("""() => {
            // 拦截 console.log
            window._traceLog = []
            const origLog = console.log
            console.log = function(...args) {
                const msg = args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ')
                window._traceLog.push(msg)
                origLog.apply(console, args)
            }
        }""")

        # 选择产品/版本
        print("[2] 选择产品/版本...")
        page.evaluate(f"""async () => {{
            const productId = 1
            const versionId = 1
            const selects = document.querySelectorAll('.el-select')
            const comp = selects[0].__vueParentComponent
            let current = comp
            let vc = null
            while (current) {{
                const ctx = current.setupState
                if (ctx && ctx.versionContext) {{
                    vc = ctx.versionContext
                    break
                }}
                current = current.parent
            }}
            const products = vc.products?.value || vc.products || []
            const productObj = products.find(p => p.id === productId) || products[0]
            vc.selectProduct(productObj)
            await new Promise(r => setTimeout(r, 2000))
            const versions = vc.versions?.value || vc.versions || []
            const versionObj = versions.find(v => v.id === versionId) || versions[0]
            vc.selectVersion(versionObj)
        }}""")
        time.sleep(5)

        # 选择对象范围
        print("[3] 选择对象范围...")
        page.evaluate("""() => {
            const trees = document.querySelectorAll('.el-tree')
            let ossTree = null
            for (const tree of trees) {
                const parent = tree.closest('.collapsible-panel')
                if (parent) {
                    const header = parent.querySelector('.collapsible-panel__header')
                    if (header && header.textContent.includes('对象范围')) {
                        if (parent.classList.contains('is-collapsed')) header.click()
                        ossTree = tree
                        break
                    }
                }
            }
            if (!ossTree && trees.length > 0) ossTree = trees[0]
            const nodes = ossTree.querySelectorAll('.el-tree-node')
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

        # 手动展开一个分类
        print("[4] 手动展开分类...")
        page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            for (const [key, node] of Object.entries(store.nodesMap || {})) {
                const name = node.data?.name || ''
                if (name.includes('同服务模块') && !node.expanded) {
                    node.expand()
                }
            }
        }""")
        time.sleep(1)

        # 清空追踪日志
        page.evaluate("""() => { window._traceLog = [] }""")

        # 点击勾选
        print("[5] 点击勾选...")
        page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store

            for (const [key, node] of Object.entries(store.nodesMap || {})) {
                if (node.isLeaf && node.visible !== false && !node.checked) {
                    const parent = node.parent
                    if (parent && (parent.data?.name || '').includes('同服务模块')) {
                        const el = document.querySelector(
                            `.el-tree-node[data-key="${key}"] .el-checkbox__input`
                        )
                        if (el) {
                            console.log('[TEST] 点击勾选:', node.data?.name)
                            el.click()
                            return
                        }
                    }
                }
            }
        }""")
        time.sleep(2)

        # 读取追踪日志
        trace_log = page.evaluate("""() => window._traceLog || []""")
        print(f"\n[6] 追踪日志 ({len(trace_log)} 条):")
        for log in trace_log[-30:]:
            print(f"  {log}")

        # 检查展开状态
        expanded = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            let count = 0
            for (const [, n] of Object.entries(store.nodesMap || {})) {
                if (n.expanded && !n.isLeaf) count++
            }
            return count
        }""")
        print(f"\n[7] 展开节点数: {expanded}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
