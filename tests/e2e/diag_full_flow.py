"""
完整流程诊断：选择 采购管理领域 → 关系范围树初始 → 点击"范围内"
"""
import sys, os, time, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from test_helpers.browser_auth_cli import PlaywrightCLI


def main():
    cli = PlaywrightCLI(headless=True)
    captured = []

    def on_request(req):
        if '/api/v2/bo/relationship' in req.url:
            captured.append({
                'time': time.time(),
                'url': req.url
            })

    try:
        page = cli._ensure_browser()
        page.on('request', on_request)

        # 1. 认证 + 导航
        print("[1] 认证 + 导航...")
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

        # 2. 选择 v1 (id=1, 29 条关系)
        print("[2] 选择产品/版本 (供应链管理系统 + 新测试2)...")
        select_result = page.evaluate("""async () => {
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
            return { product: productObj.id, version: versionObj.id }
        }""")
        print(f"  select_result: {json.dumps(select_result, ensure_ascii=False)}")
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

        # 4. 等待 OSS 树加载
        page.wait_for_selector('.el-tree', timeout=15000)
        time.sleep(2)

        # 5. 选择 '采购管理' 领域 (id=1)
        print("[3] 选择 '采购管理' 领域...")
        page.evaluate("""() => {
            const trees = document.querySelectorAll('.el-tree')
            for (let i = 0; i < trees.length; i++) {
                const tree = trees[i]
                const parent = tree.closest('.collapsible-panel')
                if (parent) {
                    const h = parent.querySelector('.collapsible-panel__header')
                    if (h && h.textContent && h.textContent.indexOf('对象范围') >= 0) {
                        const el = document.querySelector('.el-tree-node[data-key="1"] .el-checkbox__input')
                        if (el && !el.classList.contains('is-checked')) {
                            el.click()
                            return 'clicked'
                        }
                        return 'already'
                    }
                }
            }
            return 'no tree'
        }""")
        time.sleep(5)

        # 6. 展开关系范围面板 + 等待 RSS 树
        print("[4] 展开关系范围面板 + 等待 RSS 树...")
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

        # 7. 列出 RSS 树
        print("\n[5] RSS 树 (清空已捕获请求后):")
        captured.clear()
        tree_info = page.evaluate("""() => {
            const t = document.querySelector('.rss-tree-container .el-tree')
            if (!t) return null
            const vnode = t.__vueParentComponent
            const store = (vnode && vnode.exposed && vnode.exposed.store) || (vnode && vnode.ctx && vnode.ctx.store)
            if (!store) return null
            const result = []
            for (const key in store.nodesMap) {
                const node = store.nodesMap[key]
                const data = node.data || {}
                result.push({
                    id: key,
                    name: data.name,
                    count: data.count,
                    level: data.level,
                    isLeaf: node.isLeaf,
                    checked: node.checked,
                    relationIdsCount: (data.relationIds && data.relationIds.length) || 0
                })
            }
            return result
        }""")
        for n in (tree_info or []):
            m = '[L]' if n['isLeaf'] else '[P]'
            ck = '*' if n['checked'] else ' '
            print(f"  {m} {ck} {n['name']} (id={n['id']}, count={n['count']}, level={n['level']})")

        # 8. 找 '范围内' 根节点
        print("\n[6] '范围内' 根节点状态:")
        scope_info = page.evaluate("""() => {
            const t = document.querySelector('.rss-tree-container .el-tree')
            const vnode = t.__vueParentComponent
            const store = (vnode && vnode.exposed && vnode.exposed.store) || (vnode && vnode.ctx && vnode.ctx.store)
            for (const key in store.nodesMap) {
                const node = store.nodesMap[key]
                const data = node.data || {}
                const name = data.name || ''
                if (name === '范围内' || (name.indexOf('范围内') >= 0 && name.indexOf('与外部') < 0)) {
                    return {
                        id: key,
                        name: data.name,
                        count: data.count,
                        checked: node.checked,
                        indeterminate: node.indeterminate,
                        relationIdsCount: (data.relationIds && data.relationIds.length) || 0,
                        isLeaf: node.isLeaf
                    }
                }
            }
            return null
        }""")
        print(f"  {json.dumps(scope_info, ensure_ascii=False)}")

        # 9. 当前 __archPage 状态
        arch_before = page.evaluate("""() => {
            if (!window.__archPage) return { error: 'no __archPage' }
            const ap = window.__archPage
            const si = ap.scopeIds
            if (!si) return { error: 'no scopeIds' }
            const re = si.relationExtra
            return {
                relationIdsCount: re ? ((re.relationIds && re.relationIds.length) || 0) : 0,
                relationCodesCount: re ? ((re.relationCodes && re.relationCodes.length) || 0) : 0,
                categoryTypes: re ? re.categoryTypes : null,
                filterRelationCodes: re ? re.filterRelationCodes : null,
                hasIdInFilter: ap.combinedFilters && ap.combinedFilters.value ? ('id__in' in ap.combinedFilters.value) : null,
                idInValue: ap.combinedFilters && ap.combinedFilters.value ? ap.combinedFilters.value.id__in : null,
                relationCodeInValue: ap.combinedFilters && ap.combinedFilters.value ? ap.combinedFilters.value.relation_code__in : null
            }
        }""")
        print(f"\n[7] 点击前 __archPage:")
        print(f"  {json.dumps(arch_before, ensure_ascii=False)}")

        # 10. 点击 '范围内' 根节点
        print("\n[8] 点击 '范围内' 根节点...")
        captured.clear()
        click = page.evaluate("""() => {
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
                        return { clicked: true, wasChecked: node.checked, key: key }
                    }
                }
            }
            return null
        }""")
        print(f"  点击: {json.dumps(click, ensure_ascii=False)}")
        time.sleep(3)

        # 11. 抓取点击后的 API 请求
        print(f"\n[9] 点击后 API 请求 ({len(captured)} 个):")
        for c in captured:
            url = c['url']
            m = re.search(r'[?&]id__in=([^&]+)', url)
            rcm = re.search(r'[?&]relation_code__in=([^&]+)', url)
            catm = re.search(r'[?&]category_types__in=([^&]+)', url)
            print(f"  URL: {url[:200]}")
            if m:
                ids = m.group(1).split(',')
                print(f"    id__in: {len(ids)} 个 ID")
            if rcm:
                print(f"    relation_code__in: {rcm.group(1)}")
            if catm:
                print(f"    category_types__in: {catm.group(1)}")

        # 12. __archPage 点击后状态
        arch_after = page.evaluate("""() => {
            if (!window.__archPage) return null
            const ap = window.__archPage
            const si = ap.scopeIds
            const re = si.relationExtra
            return {
                relationIdsCount: re ? ((re.relationIds && re.relationIds.length) || 0) : 0,
                relationCodesCount: re ? ((re.relationCodes && re.relationCodes.length) || 0) : 0,
                hasIdInFilter: ap.combinedFilters && ap.combinedFilters.value ? ('id__in' in ap.combinedFilters.value) : null,
                idInValue: ap.combinedFilters && ap.combinedFilters.value ? ap.combinedFilters.value.id__in : null,
                relationCodeInValue: ap.combinedFilters && ap.combinedFilters.value ? ap.combinedFilters.value.relation_code__in : null
            }
        }""")
        print(f"\n[10] 点击后 __archPage:")
        print(f"  {json.dumps(arch_after, ensure_ascii=False)}")

        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_full_flow.png')

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        try:
            cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_full_flow_err.png')
        except: pass
    finally:
        cli.close()


if __name__ == '__main__':
    main()
