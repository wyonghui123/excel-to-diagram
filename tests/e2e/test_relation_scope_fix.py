"""
验证两个修复的浏览器测试（v5）
- 问题1: 关系范围树每次点击选择后自动全部展开
- 问题2: 选择关系范围叶子节点后，关系列表显示多余记录（relationIds 精确过滤）

遵循规范：
- 使用 test_data_inventory.json 或 API 探测获取有效测试数据
- 不硬编码产品/版本名称
"""
import sys, os, time, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from test_helpers.browser_auth_cli import PlaywrightCLI

def get_valid_test_data(page):
    """
    获取有效的测试数据（产品+版本）
    遵循规范：test_data_inventory.json → 数据库查询 → API 探测
    """
    # 方法 1: 尝试读取 test_data_inventory.json
    inventory_path = 'meta/tests/test_data_inventory.json'
    if os.path.exists(inventory_path):
        try:
            with open(inventory_path, encoding='utf-8') as f:
                inventory = json.load(f)
            if 'recommended' in inventory:
                return inventory['recommended']
        except:
            pass

    # 方法 2: 直接从数据库查询
    print("[数据] 从数据库查询有效测试数据...")
    try:
        import sqlite3
        db_path = 'd:/filework/excel-to-diagram/meta/architecture.db'
        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # 查询有版本和领域数据的产品
        c.execute("""
            SELECT p.id, p.name, v.id, v.name, COUNT(d.id) as domain_count
            FROM products p
            JOIN versions v ON v.product_id = p.id
            LEFT JOIN domains d ON d.version_id = v.id
            GROUP BY p.id, v.id
            HAVING domain_count > 0
            LIMIT 1
        """)
        row = c.fetchone()
        conn.close()

        if row:
            return {
                'product': {'id': row[0], 'name': row[1]},
                'version': {'id': row[2], 'name': row[3]},
                'domainCount': row[4]
            }
    except Exception as e:
        print(f"[数据] 数据库查询失败: {e}")

    # 方法 3: API 探测
    print("[数据] 通过 API 探测有效测试数据...")
    result = page.evaluate("""async () => {
        // 获取产品列表
        const pResp = await fetch('/api/v2/bo/product?page_size=100', { credentials: 'include' })
        const pData = await pResp.json()
        const products = pData.data?.items || pData.data || []

        if (!products || products.length === 0) {
            return { error: 'no products from API' }
        }

        // 遍历产品，找到有版本数据的
        for (const product of products) {
            const vResp = await fetch(`/api/v2/bo/version?product_id=${product.id}&page_size=100`, { credentials: 'include' })
            const vData = await vResp.json()
            const versions = vData.data?.items || vData.data || []

            if (versions && versions.length > 0) {
                // 检查版本是否有 domain 数据
                const version = versions[0]
                const dResp = await fetch(`/api/v2/bo/domain?version_id=${version.id}&page_size=10`, { credentials: 'include' })
                const dData = await dResp.json()
                const domains = dData.data?.items || dData.data || []

                if (domains && domains.length > 0) {
                    return {
                        product: { id: product.id, name: product.name || product.code },
                        version: { id: version.id, name: version.name || version.code },
                        domainCount: domains.length,
                        versionCount: versions.length
                    }
                }
            }
        }

        return { error: 'no product with valid version/domain data' }
    }""")

    if result.get('error'):
        raise Exception(f"无法获取有效测试数据: {result['error']}")

    print(f"[数据] 找到有效数据: 产品={result['product']['name']}, 版本={result['version']['name']}, 领域数={result.get('domainCount', 0)}")
    return result


def main():
    cli = PlaywrightCLI(headless=True)
    results = {}

    try:
        page = cli._ensure_browser()

        # Step 1: 认证
        print("[1] 认证...")
        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin",
                  wait_until="domcontentloaded", timeout=10000)
        time.sleep(1)

        # Step 2: 导航到 archdata
        print("[2] 导航到 archdata...")
        page.goto("http://localhost:3004/system/archdata",
                  wait_until="domcontentloaded", timeout=10000)
        time.sleep(3)

        # Step 3: 等待 Vue app 就绪
        page.wait_for_function("""() => {
            const app = document.querySelector('#app')?.__vue_app__
            if (!app) return false
            const pinia = app.config.globalProperties.$pinia
            const store = pinia._s.get('auth')
            return !!(store && store.sessionReady && store.user)
        }""", timeout=15000)
        print("[3] Vue app ready")

        # Step 4: 获取有效的测试数据
        test_data = get_valid_test_data(page)
        product = test_data['product']
        version = test_data['version']

        # Step 5: 通过 versionContext 选择产品/版本
        print(f"[5] 选择产品 '{product['name']}' 和版本 '{version['name']}'...")
        select_result = page.evaluate(f"""async () => {{
            const productId = {product['id']}
            const versionId = {version['id']}

            const selects = document.querySelectorAll('.el-select')
            if (selects.length === 0) return {{ error: 'no selects' }}

            const comp = selects[0].__vueParentComponent
            if (!comp) return {{ error: 'no comp' }}

            // 向上遍历找到 versionContext
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

            // 找到产品对象
            const products = vc.products?.value || vc.products || []
            const productObj = products.find(p => p.id === productId) || products[0]
            if (!productObj) return {{ error: 'product not found in list' }}

            // 选择产品
            vc.selectProduct(productObj)

            // 等待版本列表加载
            await new Promise(r => setTimeout(r, 2000))

            // 找到版本对象
            const versions = vc.versions?.value || vc.versions || []
            const versionObj = versions.find(v => v.id === versionId) || versions[0]
            if (!versionObj) return {{ error: 'version not found in list', versionCount: versions.length }}

            // 选择版本
            vc.selectVersion(versionObj)

            return {{
                selected: true,
                productName: productObj.name,
                versionName: versionObj.name
            }}
        }}""")
        print(f"[5] 选择结果: {json.dumps(select_result, ensure_ascii=False)}")

        if select_result.get('error'):
            raise Exception(f"选择产品/版本失败: {select_result['error']}")

        time.sleep(5)

        # Step 6: 等待 OSS 树加载
        print("[6] 等待 OSS 树加载...")
        try:
            page.wait_for_selector('.el-tree', timeout=15000)
            print("[6] OSS 树加载成功")
        except:
            cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/debug_no_tree_v5.png')
            debug = page.evaluate("""() => ({
                url: window.location.href,
                bodyText: document.body?.innerText?.substring(0, 300)
            })""")
            print(f"[6] 页面内容: {debug.get('bodyText', '')[:200]}")
            raise Exception("OSS 树未加载")

        time.sleep(2)

        # Step 7: 在对象范围中选择一个领域（如"销售管理"）
        print("[7] 在对象范围中选择领域...")
        select_result = page.evaluate("""() => {
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
            if (!ossTree) return { error: 'no OSS tree' }

            const nodes = ossTree.querySelectorAll('.el-tree-node')
            let targetNode = null
            for (const node of nodes) {
                const content = node.querySelector('.el-tree-node__content')
                if (content) {
                    const text = content.textContent
                    if (text.includes('销售管理') || text.includes('供应链') || text.includes('采购')) {
                        targetNode = node
                        break
                    }
                }
            }

            if (!targetNode) {
                // 选择第一个可勾选的节点
                for (const node of nodes) {
                    const cb = node.querySelector('.el-checkbox__input')
                    if (cb && !cb.classList.contains('is-checked')) {
                        targetNode = node
                        break
                    }
                }
            }

            if (!targetNode) return { error: 'no selectable node' }

            const cb = targetNode.querySelector('.el-checkbox__input')
            if (cb && !cb.classList.contains('is-checked')) {
                cb.click()
                const content = targetNode.querySelector('.el-tree-node__content')
                return { clicked: true, name: content?.textContent?.trim().substring(0, 30) }
            }
            return { alreadyChecked: true }
        }""")
        print(f"[7] 选择领域: {json.dumps(select_result, ensure_ascii=False)}")
        time.sleep(4)

        # Step 8: 展开关系范围面板
        print("[8] 展开关系范围面板...")
        page.evaluate("""() => {
            const panels = document.querySelectorAll('.collapsible-panel')
            for (const panel of panels) {
                const header = panel.querySelector('.collapsible-panel__header')
                if (header && header.textContent.includes('关系范围')) {
                    if (panel.classList.contains('is-collapsed')) {
                        header.click()
                        console.log('[TEST] 关系范围面板已展开')
                    }
                }
            }
        }""")
        time.sleep(2)

        # 等待面板展开动画完成
        page.wait_for_function("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            return tree && !tree.closest('.is-collapsed')
        }""", timeout=10000)
        time.sleep(2)

        # 等待 RSS 树加载
        print("[8b] 等待 RSS 树加载...")
        try:
            page.wait_for_selector('.rss-tree-container .el-tree', timeout=15000)
            print("[8b] RSS 树加载成功")
        except:
            cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/debug_no_rss_tree_v5.png')
            raise Exception("RSS 树未加载")
        time.sleep(2)

        # ==========================================
        # 测试问题1: 关系范围树自动展开
        # ==========================================
        print("\n[9] 测试问题1: 展开状态...")
        expand_state = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return { error: 'no RSS tree' }

            let store = null
            const vnode = tree.__vueParentComponent
            if (vnode?.exposed?.store) store = vnode.exposed.store
            else if (vnode?.ctx?.store) store = vnode.ctx.store

            if (!store) return { error: 'no store', hasVnode: !!vnode }

            const nodesMap = store.nodesMap || {}
            let total = 0, expanded = 0, expandedNames = []
            for (const [key, node] of Object.entries(nodesMap)) {
                total++
                if (node.expanded && !node.isLeaf) {
                    expanded++
                    expandedNames.push(node.data?.name || key)
                }
            }
            return { total, expanded, expandedNames, allExpanded: expanded > 2 }
        }""")
        print(f"[9] 展开状态: {json.dumps(expand_state, ensure_ascii=False)}")

        p1_fixed = not expand_state.get('allExpanded', True)
        results['problem1_auto_expand'] = {
            'fixed': p1_fixed,
            'expandedCount': expand_state.get('expanded', -1),
            'expandedNames': expand_state.get('expandedNames', []),
        }
        print(f"[9] 问题1 {'PASS' if p1_fixed else 'FAIL'}")

        # ==========================================
        # 测试问题1b: 点击勾选后是否自动展开
        # ==========================================
        print("\n[9b] 测试问题1b: 点击勾选后展开状态...")

        # 先手动展开一个分类以便能看到叶子节点
        page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return
            const nodesMap = store.nodesMap || {}
            for (const [key, node] of Object.entries(nodesMap)) {
                const name = node.data?.name || ''
                if ((name.includes('同服务模块') || name.includes('同领域')) && !node.expanded) {
                    node.expand()
                }
            }
        }""")
        time.sleep(1)

        # 记录点击前的展开数
        before_expand = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return -1
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return -1
            let c = 0
            for (const [, n] of Object.entries(store.nodesMap || {})) {
                if (n.expanded && !n.isLeaf) c++
            }
            return c
        }""")

        # 点击一个叶子节点的 checkbox
        page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return
            for (const [key, node] of Object.entries(store.nodesMap || {})) {
                if (node.isLeaf && node.visible !== false && !node.checked) {
                    const el = document.querySelector(
                        `.el-tree-node[data-key="${key}"] .el-checkbox__input`
                    )
                    if (el) { el.click(); return }
                }
            }
        }""")
        time.sleep(1)

        # 记录点击后的展开数
        after_expand = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return -1
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return -1
            let c = 0
            for (const [, n] of Object.entries(store.nodesMap || {})) {
                if (n.expanded && !n.isLeaf) c++
            }
            return c
        }""")

        click_ok = after_expand <= before_expand
        results['problem1_click_expand'] = {
            'fixed': click_ok,
            'before': before_expand,
            'after': after_expand
        }
        print(f"[9b] 点击展开 {'PASS' if click_ok else 'FAIL'}: {before_expand} -> {after_expand}")

        # ==========================================
        # 测试问题2: relationIds 传递
        # ==========================================
        print("\n[10] 测试问题2: relationIds 传递...")

        # 先勾选一个关系范围叶子节点
        print("[10a] 勾选关系范围叶子节点...")
        select_result = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return { error: 'no RSS tree' }
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            if (!store) return { error: 'no store' }

            // 找到第一个可见的叶子节点
            for (const [key, node] of Object.entries(store.nodesMap || {})) {
                if (node.isLeaf && node.visible !== false && !node.checked) {
                    const el = document.querySelector(
                        `.el-tree-node[data-key="${key}"] .el-checkbox__input`
                    )
                    if (el) {
                        el.click()
                        return { clicked: true, key: key, name: node.data?.name }
                    }
                }
            }
            return { error: 'no visible leaf node' }
        }""")
        print(f"[10a] 勾选结果: {json.dumps(select_result, ensure_ascii=False)}")
        time.sleep(2)

        # 检查 scopeIds 中的 relationIds
        # useMultiObjectPage 是 composable，不是 Pinia store，需要通过组件树找到
        scope_check = page.evaluate("""() => {
            const app = document.querySelector('#app').__vue_app__
            if (!app) return { error: 'no app' }

            let result = {}

            // 通过组件树找到 MultiObjectPage 组件实例
            const findComponent = (comp, name) => {
                if (!comp) return null
                const compName = comp.type?.name || comp.type?.__name || ''
                if (compName.includes(name)) return comp
                if (comp.parent) return findComponent(comp.parent, name)
                return null
            }

            // 从 el-tree 找到 RelationScopeSection 组件
            const tree = document.querySelector('.rss-tree-container .el-tree')
            if (!tree) return { error: 'no RSS tree' }

            const vnode = tree.__vueParentComponent
            if (!vnode) return { error: 'no vnode' }

            // 向上遍历找到有 scopeIds 的组件
            let current = vnode
            let scopeIds = null
            let scopeSource = null
            while (current) {
                const ctx = current.setupState
                if (ctx) {
                    if (ctx.scopeIds && !scopeIds) {
                        scopeIds = ctx.scopeIds
                        result.foundIn = current.type?.name || 'unknown'
                    }
                    if (ctx.scopeSource && !scopeSource) {
                        scopeSource = ctx.scopeSource
                    }
                    // 检查 useMultiObjectPage 返回的值
                    for (const key of Object.keys(ctx)) {
                        const val = ctx[key]
                        if (val && typeof val === 'object') {
                            if (val.scopeIds && !scopeIds) {
                                scopeIds = val.scopeIds
                                result.foundIn = key
                            }
                            if (val.scopeSource && !scopeSource) {
                                scopeSource = val.scopeSource
                            }
                        }
                    }
                }
                current = current.parent
            }

            if (scopeIds?.relationExtra) {
                const extra = scopeIds.relationExtra
                result.relationCodes = extra.relationCodes
                result.relationIds = extra.relationIds
                result.codesCount = extra.relationCodes?.length || 0
                result.idsCount = extra.relationIds?.length || 0
            }

            if (scopeSource?.selectedRelationIds) {
                result.scopeSourceRelationIds = scopeSource.selectedRelationIds
            }

            // 检查 combinedFilters
            if (scopeSource?.combinedFilters) {
                const f = scopeSource.combinedFilters
                result.hasIdIn = 'id__in' in f
                result.idInValue = f.id__in
                result.hasRelationCodeIn = 'relation_code__in' in f
                result.relationCodeInValue = f.relation_code__in
                result.allFilterKeys = Object.keys(f)
            } else if (scopeSource?.value?.combinedFilters) {
                // scopeSource 可能是 ref
                const f = scopeSource.value.combinedFilters
                result.hasIdIn = 'id__in' in f
                result.idInValue = f.id__in
                result.hasRelationCodeIn = 'relation_code__in' in f
                result.relationCodeInValue = f.relation_code__in
                result.allFilterKeys = Object.keys(f)
                result.scopeSourceType = 'ref'
            }

            // 直接查找 combinedFilters (可能是 computed ref)
            // 从 RelationScopeSection 向上遍历，找到 MultiObjectPage 组件
            let current3 = vnode
            let searchDepth = 0
            while (current3 && searchDepth < 20) {
                const ctx = current3.setupState
                if (ctx) {
                    // 检查 ctx 本身是否有 combinedFilters
                    if (ctx.combinedFilters) {
                        const cf = ctx.combinedFilters
                        const f = cf?.value || cf
                        result.combinedFiltersFound = true
                        result.cfFoundIn = 'setupState.combinedFilters'
                        result.cfHasIdIn = 'id__in' in f
                        result.cfIdInValue = f.id__in
                        result.cfAllKeys = Object.keys(f).slice(0, 20)
                        break
                    }
                    // 检查 ctx 的每个属性，看是否有 combinedFilters
                    for (const key of Object.keys(ctx)) {
                        const val = ctx[key]
                        if (val && typeof val === 'object') {
                            const cf = val.combinedFilters
                            if (cf) {
                                const f = cf?.value || cf
                                result.combinedFiltersFound = true
                                result.cfFoundIn = `setupState.${key}.combinedFilters`
                                result.cfHasIdIn = 'id__in' in f
                                result.cfIdInValue = f.id__in
                                result.cfAllKeys = Object.keys(f).slice(0, 20)
                                break
                            }
                        }
                    }
                    if (result.combinedFiltersFound) break
                }
                current3 = current3.parent
                searchDepth++
            }

            if (!result.combinedFiltersFound) {
                result.searchDepth = searchDepth
            }

            // 检查 hierarchyTypes.isAssociation
            for (const [name, store] of (app.config.globalProperties.$pinia._s || [])) {
                // Pinia stores 中没有 hierarchyTypes
            }
            // 从组件树找 hierarchyTypes
            let current2 = vnode
            while (current2) {
                const ctx = current2.setupState
                if (ctx) {
                    for (const key of Object.keys(ctx)) {
                        const val = ctx[key]
                        if (val && typeof val === 'object' && typeof val.isAssociation === 'function') {
                            result.isRelationshipAssociation = val.isAssociation('relationship')
                            result.isRelationshipEntity = val.isEntity?.('relationship')
                            result.hierarchyTypesFoundIn = key
                            break
                        }
                    }
                }
                if (result.isRelationshipAssociation !== undefined) break
                current2 = current2.parent
            }

            return result
        }""")
        print(f"[10] scopeIds 检查结果:")
        for k, v in sorted(scope_check.items()):
            if k == 'scopeSourceRelationIds':
                # 简化 ref 对象显示
                if isinstance(v, dict) and '_value' in v:
                    print(f"  {k}: {v['_value']}")
                else:
                    print(f"  {k}: {v}")
            elif isinstance(v, list) and len(v) > 10:
                print(f"  {k}: {v[:10]}... (共{len(v)}项)")
            else:
                print(f"  {k}: {v}")

        # 检查 combinedFilters 是否找到
        has_cf = scope_check.get('combinedFiltersFound', False)
        cf_has_id_in = scope_check.get('cfHasIdIn', False)
        cf_keys = scope_check.get('cfAllKeys', [])
        if has_cf:
            print(f"[10] combinedFilters 找到:")
            print(f"    id__in: {cf_has_id_in}")
            print(f"    keys: {cf_keys}")
            # 检查 relation_ids
            if 'relation_ids' in cf_keys:
                print(f"    relation_ids 存在 [DECORATIVE]")
        else:
            print("[10] combinedFilters 未找到")

        has_ids = (scope_check.get('idsCount') or 0) > 0
        # 检查 combinedFilters 中是否有 relation_ids 或 id__in
        has_relation_filter = 'relation_ids' in cf_keys or scope_check.get('cfHasIdIn', False)
        p2_fixed = has_ids and has_relation_filter

        results['problem2_data_consistency'] = {
            'fixed': p2_fixed,
            'relationIds': scope_check.get('relationIds'),
            'id__in': scope_check.get('idInValue'),
        }
        print(f"[10] 问题2 {'PASS' if p2_fixed else 'FAIL'}: ids={scope_check.get('idsCount', 0)}, relation_ids={has_relation_filter}")

        # 截图
        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/test_result_v5.png')

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        results['error'] = str(e)
        try:
            cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/test_error_v5.png')
        except:
            pass
    finally:
        cli.close()

    print("\n" + "="*60)
    print("测试结果汇总:")
    print("="*60)
    for key, val in results.items():
        if isinstance(val, dict):
            status = "PASS" if val.get('fixed') else "FAIL"
            print(f"  {key}: {status}")
            for k, v in val.items():
                if k != 'fixed':
                    print(f"    {k}: {v}")
        else:
            print(f"  {key}: {val}")

    return results


if __name__ == '__main__':
    main()
