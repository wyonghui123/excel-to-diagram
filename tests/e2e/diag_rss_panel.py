"""
诊断脚本：检查关系范围面板内容
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

        # 选择有数据的产品/版本
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

        # 检查关系范围面板内容
        panel_info = page.evaluate("""() => {
            const panels = document.querySelectorAll('.collapsible-panel')
            let rssPanel = null
            for (const panel of panels) {
                const header = panel.querySelector('.collapsible-panel__header')
                if (header && header.textContent.includes('关系范围')) {
                    rssPanel = panel
                    break
                }
            }

            if (!rssPanel) return { error: 'no RSS panel' }

            const body = rssPanel.querySelector('.collapsible-panel__body')
            const tree = rssPanel.querySelector('.el-tree')
            const empty = rssPanel.querySelector('.el-tree__empty-block')
            const loading = rssPanel.querySelector('.el-loading')

            return {
                bodyText: body?.innerText?.substring(0, 300) || '',
                hasTree: !!tree,
                hasEmpty: !!empty,
                hasLoading: !!loading,
                emptyText: empty?.querySelector('.el-tree__empty-text')?.textContent || '',
                treeNodes: tree ? tree.querySelectorAll('.el-tree-node').length : 0
            }
        }""")

        print(f"关系范围面板信息:")
        print(f"  有树: {panel_info.get('hasTree', False)}")
        print(f"  有空状态: {panel_info.get('hasEmpty', False)}")
        print(f"  有加载: {panel_info.get('hasLoading', False)}")
        print(f"  空状态文本: {panel_info.get('emptyText', '')}")
        print(f"  树节点数: {panel_info.get('treeNodes', 0)}")
        print(f"\n  body 文本:")
        print(f"  {panel_info.get('bodyText', '')}")

        # 截图
        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_rss_panel.png')

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()

if __name__ == '__main__':
    main()
