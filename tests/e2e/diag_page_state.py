"""
诊断脚本：检查页面状态
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

        # 截图1: 产品/版本选择后
        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_step1.png')
        print("[1] 产品/版本已选择")

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

        # 截图2: 对象范围选择后
        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_step2.png')
        print("[2] 对象范围已选择")

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

        # 截图3: 关系范围面板展开后
        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_step3.png')
        print("[3] 关系范围面板已展开")

        # 检查页面内容
        page_info = page.evaluate("""() => {
            const info = {
                url: window.location.href,
                panels: [],
                trees: []
            }

            // 检查面板
            const panels = document.querySelectorAll('.collapsible-panel')
            for (const panel of panels) {
                const header = panel.querySelector('.collapsible-panel__header')
                if (header) {
                    info.panels.push({
                        title: header.textContent.substring(0, 30),
                        collapsed: panel.classList.contains('is-collapsed')
                    })
                }
            }

            // 检查树
            const trees = document.querySelectorAll('.el-tree')
            for (const tree of trees) {
                const parent = tree.closest('.collapsible-panel')
                const parentTitle = parent ? parent.querySelector('.collapsible-panel__header')?.textContent?.substring(0, 20) : 'unknown'
                const nodes = tree.querySelectorAll('.el-tree-node')
                info.trees.push({
                    parent: parentTitle,
                    nodeCount: nodes.length,
                    visibleNodes: [...nodes].filter(n => {
                        const style = window.getComputedStyle(n)
                        return style.display !== 'none' && style.visibility !== 'hidden'
                    }).length
                })
            }

            // 检查 RSS 树容器
            const rssTree = document.querySelector('.rss-tree-container')
            if (rssTree) {
                const rssNodes = rssTree.querySelectorAll('.el-tree-node')
                info.rssTree = {
                    found: true,
                    nodeCount: rssNodes.length
                }
            } else {
                info.rssTree = { found: false }
            }

            return info
        }""")
        print(f"\n[4] 页面信息:")
        print(f"  URL: {page_info.get('url', '')}")
        print(f"  面板:")
        for p in page_info.get('panels', []):
            print(f"    {p['title']} - {'收起' if p['collapsed'] else '展开'}")
        print(f"  树:")
        for t in page_info.get('trees', []):
            print(f"    {t['parent']}: {t['nodeCount']} 节点, {t['visibleNodes']} 可见")
        print(f"  RSS 树: {page_info.get('rssTree', {})}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
