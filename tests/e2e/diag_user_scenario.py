"""
诊断：用户在 采购管理领域 + 范围内 only 时，list 显示 29 条
用户报告：list 显示 29 (= 28 within + 1 cross-boundary)
期望：list 显示 28 (only within-scope)
"""
import sys, os, time, json, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from test_helpers.browser_auth_cli import PlaywrightCLI


def get_valid_test_data(page):
    """从 API 探测有效测试数据（产品+版本+领域）"""
    inventory_path = 'meta/tests/test_data_inventory.json'
    if os.path.exists(inventory_path):
        try:
            with open(inventory_path, encoding='utf-8') as f:
                inventory = json.load(f)
            if 'recommended' in inventory:
                return inventory['recommended']
        except:
            pass
    # 探测
    return page.evaluate("""async () => {
        const pResp = await fetch('/api/v2/bo/product?page_size=100', { credentials: 'include' })
        const pData = await pResp.json()
        const products = pData.data?.items || pData.data || []
        for (const product of products) {
            const vResp = await fetch(`/api/v2/bo/version?product_id=${product.id}&page_size=100`, { credentials: 'include' })
            const vData = await vResp.json()
            const versions = vData.data?.items || vData.data || []
            for (const version of versions) {
                const dResp = await fetch(`/api/v2/bo/domain?version_id=${version.id}&page_size=200`, { credentials: 'include' })
                const dData = await dResp.json()
                const domains = dData.data?.items || dData.data || []
                // 找含"采购"的领域
                for (const d of domains) {
                    const dn = d.name || d.domain_name || d.code || ''
                    if (dn.includes('采购')) {
                        return {
                            product: { id: product.id, name: product.name || product.code },
                            version: { id: version.id, name: version.name || version.code },
                            domain: { id: d.id, name: dn }
                        }
                    }
                }
            }
        }
        return { error: 'no 采购 domain found' }
    }""")


def main():
    cli = PlaywrightCLI(headless=True)
    captured_requests = []

    def on_request(req):
        if '/api/v2/bo/relationship' in req.url and 'page=1' in req.url and 'page_size=20' in req.url:
            captured_requests.append(req.url)

    try:
        page = cli._ensure_browser()
        page.on('request', on_request)

        # 1. 认证
        print("[1] 认证...")
        page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin",
                  wait_until="domcontentloaded", timeout=10000)
        time.sleep(1)

        # 2. 导航到 archdata
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
        print("[2] Vue app ready")

        # 3. 获取测试数据
        test_data = get_valid_test_data(page)
        if isinstance(test_data, dict) and test_data.get('error'):
            raise Exception(test_data['error'])
        product = test_data['product']
        version = test_data['version']
        domain = test_data.get('domain')
        print(f"[3] 数据: product={product['name']}, version={version['name']}, domain={domain.get('name', '?') if domain else 'NONE'}")

        # 4. 选择产品+版本
        print("[4] 选择产品/版本...")
        page.evaluate(f"""async () => {{
            const productId = {product['id']}
            const versionId = {version['id']}
            const selects = document.querySelectorAll('.el-select')
            let current = selects[0]?.__vueParentComponent
            let vc = null
            while (current) {{
                const ctx = current.setupState
                if (ctx && ctx.versionContext) {{ vc = ctx.versionContext; break }}
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

        # 5. 选择 采购管理领域（如果 API 探测到了）
        if domain:
            print(f"[5] 选择领域: {domain['name']}...")
            page.evaluate(f"""async () => {{
                const domainId = {domain['id']}
                const trees = document.querySelectorAll('.el-tree')
                let ossTree = null
                for (const tree of trees) {{
                    const parent = tree.closest('.collapsible-panel')
                    if (parent) {{
                        const header = parent.querySelector('.collapsible-panel__header')
                        if (header && header.textContent.includes('对象范围')) {{
                            if (parent.classList.contains('is-collapsed')) header.click()
                            ossTree = tree
                            break
                        }}
                    }}
                }}
                if (!ossTree && trees.length > 0) ossTree = trees[0]
                if (!ossTree) return
                // 通过 store 找到该 domain 并勾选
                const vnode = ossTree.__vueParentComponent
                const store = vnode?.exposed?.store || vnode?.ctx?.store
                if (!store) return
                for (const [key, node] of Object.entries(store.nodesMap || {{}})) {{
                    if (key == String(domainId) && !node.checked) {{
                        const el = document.querySelector(`.el-tree-node[data-key="${{key}}"] .el-checkbox__input`)
                        if (el) el.click()
                        return
                    }}
                }}
            }}""")
            time.sleep(5)

        # 6. 展开关系范围面板
        page.evaluate("""() => {
            const panels = document.querySelectorAll('.collapsible-panel')
            for (const panel of panels) {
                const header = panel.querySelector('.collapsible-panel__header')
                if (header && header.textContent.includes('关系范围')) {
                    if (panel.classList.contains('is-collapsed')) header.click()
                }
            }
        }""")
        time.sleep(3)
        page.wait_for_selector('.rss-tree-container .el-tree', timeout=15000)
        time.sleep(3)

        # 7. 打印树结构（看 INTERNAL 节点信息）
        print("\n[7] RSS 树结构:")
        tree_info = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            const result = []
            for (const [key, node] of Object.entries(store.nodesMap || {})) {
                const data = node.data || {}
                result.push({
                    id: key,
                    name: data.name,
                    count: data.count,
                    hasRelationIds: Array.isArray(data.relationIds),
                    relationIdsCount: data.relationIds?.length || 0,
                    level: data.level,
                    isLeaf: node.isLeaf
                })
            }
            return result
        }""")
        for n in tree_info:
            marker = '[LEAF]' if n['isLeaf'] else '[PARENT]'
            rid = f"  relationIds={n['relationIdsCount']}" if n['hasRelationIds'] else ''
            print(f"  {marker} {n['name']} (count={n['count']}, level={n['level']}){rid}")

        # 清空已捕获的请求
        captured_requests.clear()

        # 8. 点击 "范围内" 根节点（INTERNAL）
        print("\n[8] 点击 '范围内' 根节点...")
        click_result = page.evaluate("""() => {
            const tree = document.querySelector('.rss-tree-container .el-tree')
            const vnode = tree.__vueParentComponent
            const store = vnode?.exposed?.store || vnode?.ctx?.store
            for (const [key, node] of Object.entries(store.nodesMap || {})) {
                const name = node.data?.name || ''
                if (name.includes('范围内') && !name.includes('与外部')) {
                    const el = document.querySelector(`.el-tree-node[data-key="${key}"] .el-checkbox__input`)
                    if (el) {
                        el.click()
                        return { clicked: true, key, name, wasChecked: node.checked }
                    }
                }
            }
            return { error: 'INTERNAL root not found' }
        }""")
        print(f"  点击结果: {json.dumps(click_result, ensure_ascii=False)}")
        time.sleep(3)

        # 9. 检查被捕获的 API 请求
        print("\n[9] 捕获的 relationship API 请求:")
        for url in captured_requests:
            # 解析 id__in 和 relation_code__in
            match = re.search(r'[?&]id__in=([^&]+)', url)
            rcmatch = re.search(r'[?&]relation_code__in=([^&]+)', url)
            id_in = match.group(1) if match else None
            rc_in = rcmatch.group(1) if rcmatch else None
            id_count = len(id_in.split(',')) if id_in else 0
            rc_count = len(rc_in.split(',')) if rc_in else 0
            print(f"  URL: {url[:200]}...")
            print(f"  id__in: {id_in}  (count={id_count})")
            print(f"  relation_code__in: {rc_in}  (count={rc_count})")

        # 10. 检查列表实际显示的数量
        list_count = page.evaluate("""() => {
            // 找关系列表的表格或卡片
            const tables = document.querySelectorAll('.el-table__body-wrapper tr.el-table__row, .bo-list-item, [data-testid="relation-list-item"]')
            return tables.length
        }""")
        print(f"\n[10] 列表显示行数: {list_count}")

        # 11. 从后端直接调用对比
        print("\n[11] 对比：后端直接调用")
        direct_check = page.evaluate(f"""async () => {{
            const versionId = {version['id']}
            // 不加任何关系范围过滤，看总共多少
            const baseResp = await fetch(`/api/v2/bo/relationship?version_id=${{versionId}}&page=1&page_size=200`, {{ credentials: 'include' }})
            const baseData = await baseResp.json()
            return {{ total: baseData.data?.total }}
        }}""")
        print(f"  后端 base total: {direct_check}")

        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_user_scenario.png')

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        try:
            cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/diag_user_scenario_error.png')
        except:
            pass
    finally:
        cli.close()


if __name__ == '__main__':
    main()
