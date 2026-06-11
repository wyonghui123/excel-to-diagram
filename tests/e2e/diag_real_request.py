"""
抓真实 API 请求：选 采购管理领域 + 点击"范围内" 后 关系列表的 API URL
"""
import sys, os, time, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from test_helpers.browser_auth_cli import PlaywrightCLI


def main():
    cli = PlaywrightCLI(headless=True)
    captured = []

    def on_response(resp):
        if '/api/v2/bo/relationship' in resp.url:
            try:
                body = resp.body().decode('utf-8', errors='replace')[:500]
            except:
                body = '(body read failed)'
            captured.append({
                'status': resp.status,
                'url': resp.url,
                'body': body
            })

    try:
        page = cli._ensure_browser()
        page.on('response', on_response)

        # 1. 认证 + 导航
        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin",
                  wait_until="domcontentloaded", timeout=10000)
        time.sleep(1)
        page.goto("http://localhost:3004/system/archdata",
                  wait_until="domcontentloaded", timeout=10000)
        time.sleep(3)
        page.wait_for_function("""() => {
            const app = document.querySelector('#app')?.__vue_app__
            const pinia = app.config.globalProperties.$pinia
            return pinia._s.get('auth')?.sessionReady
        }""", timeout=15000)

        # 2. 选择 v1
        page.evaluate("""async () => {
            const selects = document.querySelectorAll('.el-select')
            let vc = null
            for (let i = 0; i < selects.length; i++) {
                let c = selects[i].__vueParentComponent
                while (c) {
                    if (c.setupState && c.setupState.versionContext) { vc = c.setupState.versionContext; break }
                    c = c.parent
                }
                if (vc) break
            }
            const products = (vc.products && vc.products.value) || vc.products || []
            const productObj = products.find(function(p) { return (p.name && p.name.indexOf('供应链') >= 0) || p.id === 1 })
            vc.selectProduct(productObj)
            await new Promise(function(r) { setTimeout(r, 2000) })
            const versions = (vc.versions && vc.versions.value) || vc.versions || []
            const versionObj = versions.find(function(v) { return v.id === 1 }) || versions[0]
            vc.selectVersion(versionObj)
        }""")
        time.sleep(6)

        # 3. 展开对象范围面板
        page.evaluate("""() => {
            const panels = document.querySelectorAll('.collapsible-panel')
            for (let i = 0; i < panels.length; i++) {
                const p = panels[i]
                const h = p.querySelector('.collapsible-panel__header')
                if (h && h.textContent && h.textContent.indexOf('对象范围') >= 0 && p.classList.contains('is-collapsed')) {
                    h.click()
                }
            }
        }""")
        time.sleep(2)
        page.wait_for_selector('.el-tree', timeout=15000)
        time.sleep(2)

        # 4. 选 采购管理
        page.evaluate("""() => {
            const el = document.querySelector('.el-tree-node[data-key="1"] .el-checkbox__input')
            if (el && !el.classList.contains('is-checked')) el.click()
        }""")
        time.sleep(5)

        # 5. 展开关系范围
        page.evaluate("""() => {
            const panels = document.querySelectorAll('.collapsible-panel')
            for (let i = 0; i < panels.length; i++) {
                const p = panels[i]
                const h = p.querySelector('.collapsible-panel__header')
                if (h && h.textContent && h.textContent.indexOf('关系范围') >= 0 && p.classList.contains('is-collapsed')) {
                    h.click()
                }
            }
        }""")
        time.sleep(3)
        page.wait_for_selector('.rss-tree-container .el-tree', timeout=15000)
        time.sleep(3)

        # 6. 清空 captured + 先 uncheck 已有勾选，再 check "范围内"
        captured.clear()
        # 6a. 先清空所有 RSS 勾选
        page.evaluate("""() => {
            const t = document.querySelector('.rss-tree-container .el-tree')
            const vnode = t.__vueParentComponent
            const store = (vnode && vnode.exposed && vnode.exposed.store) || (vnode && vnode.ctx && vnode.ctx.store)
            // 全清
            const clearBtn = document.querySelector('.rss-tree-container .rss-action-btn[title*="清空"], .rss-tree-container button')
            // 找 "清空" 按钮
            const buttons = document.querySelectorAll('.rss-tree-container button, .rss-action-btn')
            for (let i = 0; i < buttons.length; i++) {
                const txt = buttons[i].textContent || ''
                if (txt.indexOf('清空') >= 0 || txt.indexOf('清除') >= 0) {
                    buttons[i].click()
                    return 'cleared'
                }
            }
            return 'no clear btn'
        }""")
        time.sleep(2)
        # 6b. 然后点击 "范围内" (此时应该是 uncheck 状态)
        click_result = page.evaluate("""() => {
            const t = document.querySelector('.rss-tree-container .el-tree')
            const vnode = t.__vueParentComponent
            const store = (vnode && vnode.exposed && vnode.exposed.store) || (vnode && vnode.ctx && vnode.ctx.store)
            for (const key in store.nodesMap) {
                const node = store.nodesMap[key]
                const name = (node.data && node.data.name) || ''
                if (name === '范围内') {
                    return { checked: node.checked, willClick: !node.checked }
                }
            }
            return null
        }""")
        print(f"  '范围内' 状态: {json.dumps(click_result, ensure_ascii=False)}")

        if click_result and click_result.get('willClick'):
            page.evaluate("""() => {
                const t = document.querySelector('.rss-tree-container .el-tree')
                const vnode = t.__vueParentComponent
                const store = (vnode && vnode.exposed && vnode.exposed.store) || (vnode && vnode.ctx && vnode.ctx.store)
                for (const key in store.nodesMap) {
                    const node = store.nodesMap[key]
                    const name = (node.data && node.data.name) || ''
                    if (name === '范围内') {
                        const el = document.querySelector('.el-tree-node[data-key="' + key + '"] .el-checkbox__input')
                        if (el) {
                            el.click()
                            return { clicked: true, key: key }
                        }
                    }
                }
                return { error: 'not found' }
            }""")
        time.sleep(5)

        # 7. 输出捕获
        print(f"\n=== 捕获 {len(captured)} 个关系 API 响应 ===")
        for i, c in enumerate(captured):
            url = c['url']
            print(f"\n[{i}] status={c['status']}")
            print(f"    URL: {url[:300]}")
            print(f"    body: {c['body'][:300]}")

        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_real_request.png')

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
    finally:
        cli.close()


if __name__ == '__main__':
    main()
