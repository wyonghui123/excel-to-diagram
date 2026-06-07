"""
诊断脚本：检查点击勾选时的行为
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

        # 选择产品/版本
        print("[1] 选择产品/版本...")
        page.evaluate(f"""async () => {{
            const productId = 1
            const versionId = 1

            const selects = document.querySelectorAll('.el-select')
            if (selects.length === 0) return {{ error: 'no selects' }}

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

            if (!vc) return {{ error: 'no versionContext' }}

            const products = vc.products?.value || vc.products || []
            const productObj = products.find(p => p.id === productId) || products[0]
            if (!productObj) return {{ error: 'product not found' }}

            vc.selectProduct(productObj)
            await new Promise(r => setTimeout(r, 2000))

            const versions = vc.versions?.value || vc.versions || []
            const versionObj = versions.find(v => v.id === versionId) || versions[0]
            if (!versionObj) return {{ error: 'version not found' }}

            vc.selectVersion(versionObj)
            return {{ selected: true }}
        }}""")
        time.sleep(5)

        # 选择对象范围
        print("[2] 选择对象范围...")
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
            if (!ossTree) return

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
        print("[3] 展开关系范围面板...")
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

        # 手动展开"同服务模块"分类
        print("[4] 手动展开'同服务模块'分类...")
        before_expand = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return -1
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return -1

            let expandedCount = 0
            for (const [key, node] of Object.entries(store.nodesMap || {})) {
                const name = node.data?.name || ''
                if (name.includes('同服务模块') && !node.expanded) {
                    node.expand()
                    console.log('[TEST] 展开了:', name)
                }
                if (node.expanded && !node.isLeaf) expandedCount++
            }
            return expandedCount
        }""")
        print(f"[4] 展开前展开节点数: {before_expand}")
        time.sleep(1)

        # 记录当前展开状态
        before_click = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return {}
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return {}

            const expanded = []
            for (const [key, node] of Object.entries(store.nodesMap || {})) {
                if (node.expanded && !node.isLeaf) {
                    expanded.push(node.data?.name || key)
                }
            }
            return { expandedCount: expanded.length, expandedNames: expanded }
        }""")
        print(f"[5] 点击前展开状态: {json.dumps(before_click, ensure_ascii=False)}")

        # 点击勾选一个叶子节点
        print("[6] 点击勾选叶子节点...")
        click_result = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return { error: 'no tree' }
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return { error: 'no store' }

            // 找到"同服务模块"下的叶子节点
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
                            return { clicked: true, name: node.data?.name }
                        }
                    }
                }
            }
            return { error: 'no leaf node found' }
        }""")
        print(f"[6] 点击结果: {json.dumps(click_result, ensure_ascii=False)}")
        time.sleep(2)

        # 记录点击后展开状态
        after_click = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return {}
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return {}

            const expanded = []
            for (const [key, node] of Object.entries(store.nodesMap || {})) {
                if (node.expanded && !node.isLeaf) {
                    expanded.push(node.data?.name || key)
                }
            }
            return { expandedCount: expanded.length, expandedNames: expanded }
        }""")
        print(f"[7] 点击后展开状态: {json.dumps(after_click, ensure_ascii=False)}")

        # 判断问题
        if before_click.get('expandedCount', 0) > 0 and after_click.get('expandedCount', 0) == 0:
            print("\n[X] 问题1确认：点击勾选后所有节点被收起")
        elif before_click.get('expandedCount', 0) > after_click.get('expandedCount', 0):
            print(f"\n[WARNING] 部分节点被收起：{before_click.get('expandedCount', 0)} -> {after_click.get('expandedCount', 0)}")
        else:
            print("\n[OK] 问题1已修复：展开状态保持")

        # 截图
        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_collapse.png')

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
