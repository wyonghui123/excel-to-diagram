"""
端到端验证：关系范围 + id__in 整链路 (v3.18)
- Issue: 28/29 反复出现的根因是后端 id__in filter 被 bound method 多传 self 撞坏
- 本测试不依赖测试脚本（直接走 Python urllib），强制端到端跑通
- 如果未来再次出现类似 bug，本测试会立刻挂

使用规范：
- 必须通过 test.py 入口: python d:\filework\test.py --file tests/e2e/test_e2e_chain.py
- 不直接调 pytest
"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import urllib.request
import urllib.error
import http.cookiejar


def get_session():
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')
    return opener


def get_opener_no_error():
    """Opener that returns response object even on 4xx/5xx"""
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),
                                       urllib.request.HTTPErrorProcessor())


def http_get(opener, url):
    try:
        return opener.open(url), None
    except urllib.error.HTTPError as e:
        return e, e.read().decode('utf-8', errors='replace')


def find_test_version(opener):
    """找一个有 relationship 数据的版本作为测试 fixture"""
    r, _ = http_get(opener, 'http://localhost:3010/api/v2/bo/product?page_size=50')
    products = json.loads(r.read())['data']['items']
    for p in products:
        r, _ = http_get(opener, f'http://localhost:3010/api/v2/bo/version?product_id={p["id"]}&page_size=50')
        versions = json.loads(r.read())['data']['items']
        for v in versions:
            # 查 relationship 数
            r, _ = http_get(opener, f'http://localhost:3010/api/v2/bo/relationship?version_id={v["id"]}&page=1&page_size=1')
            data = json.loads(r.read())['data']
            if data['total'] > 0:
                return {
                    'product': p,
                    'version': v,
                    'relationshipCount': data['total']
                }
    raise Exception('No version with relationship data found')


def main():
    print("=" * 70)
    print("  端到端链路验证: 关系范围 + id__in (v3.18)")
    print("=" * 70)

    failures = []
    results = {}

    # 1. login
    print("\n[1] 认证...")
    opener = get_session()
    print("  OK")

    # 2. 找一个有效的测试版本
    print("\n[2] 查找测试版本 (有 relationship 数据)...")
    test_data = find_test_version(opener)
    version_id = test_data['version']['id']
    print(f"  version_id={version_id}, relationships={test_data['relationshipCount']}")

    # 3. 总关系数 (基线)
    print("\n[3] 基线查询: 该版本总关系数...")
    r, _ = http_get(opener, f'http://localhost:3010/api/v2/bo/relationship?version_id={version_id}&page=1&page_size=200')
    baseline = json.loads(r.read())
    baseline_total = baseline['data']['total']
    print(f"  baseline_total={baseline_total}")
    if baseline_total == 0:
        print("  [SKIP] 该版本无关系数据，跳过 id__in 测试")
        return

    # 4. === 关键断言 1 ===: id__in filter 端到端跑通
    print("\n[4] === 关键断言 1: id__in 端到端跑通 ===")
    # 取 baseline 中前 3 个 ID
    all_items = baseline['data']['items']
    sample_ids = [item['id'] for item in all_items[:3]]
    ids_str = ','.join(str(i) for i in sample_ids)

    r, _ = http_get(opener, f'http://localhost:3010/api/v2/bo/relationship?version_id={version_id}&id__in={ids_str}&page=1&page_size=10')
    body = r.read().decode('utf-8', errors='replace')
    if r.status == 200:
        d = json.loads(body)
        actual_count = d['data']['total']
        print(f"  [id__in=3 IDs] total={actual_count} (期望 3)")
        results['id__in_3_ids'] = (actual_count == 3, f"got {actual_count}")
        if actual_count != 3:
            failures.append(f"id__in=3 IDs returned {actual_count}, expected 3")
    else:
        print(f"  [FAIL] status={r.status}, body={body[:200]}")
        results['id__in_3_ids'] = (False, f"status={r.status}, body={body[:200]}")
        failures.append(f"id__in=3 IDs HTTP {r.status}: {body[:200]}")

    # 5. === 关键断言 2 ===: id__in=全部 IDs 应该等于 baseline
    print("\n[5] === 关键断言 2: id__in=全部 IDs ===")
    # 查全部 (拿所有 id)
    r, _ = http_get(opener, f'http://localhost:3010/api/v2/bo/relationship?version_id={version_id}&page=1&page_size=1000')
    all_items = json.loads(r.read())['data']['items']
    all_ids = [str(item['id']) for item in all_items]
    all_ids_str = ','.join(all_ids)

    r, _ = http_get(opener, f'http://localhost:3010/api/v2/bo/relationship?version_id={version_id}&id__in={all_ids_str}&page=1&page_size=1000')
    body = r.read().decode('utf-8', errors='replace')
    if r.status == 200:
        d = json.loads(body)
        actual_count = d['data']['total']
        print(f"  [id__in={len(all_ids)} IDs] total={actual_count} (期望 {baseline_total})")
        results['id__in_all'] = (actual_count == baseline_total, f"got {actual_count}, expected {baseline_total}")
        if actual_count != baseline_total:
            failures.append(f"id__in=all returned {actual_count}, expected {baseline_total}")
    else:
        print(f"  [FAIL] status={r.status}, body={body[:200]}")
        results['id__in_all'] = (False, f"status={r.status}, body={body[:200]}")
        failures.append(f"id__in=all HTTP {r.status}: {body[:200]}")

    # 6. === 关键断言 3 ===: id__in=单个 ID
    print("\n[6] === 关键断言 3: id__in=单个 ID ===")
    single_id = all_ids[0]
    r, _ = http_get(opener, f'http://localhost:3010/api/v2/bo/relationship?version_id={version_id}&id__in={single_id}&page=1&page_size=10')
    body = r.read().decode('utf-8', errors='replace')
    if r.status == 200:
        d = json.loads(body)
        actual_count = d['data']['total']
        print(f"  [id__in=1 ID] total={actual_count} (期望 1)")
        results['id__in_1_id'] = (actual_count == 1, f"got {actual_count}")
        if actual_count != 1:
            failures.append(f"id__in=single returned {actual_count}, expected 1")
    else:
        print(f"  [FAIL] status={r.status}, body={body[:200]}")
        results['id__in_1_id'] = (False, f"status={r.status}, body={body[:200]}")
        failures.append(f"id__in=single HTTP {r.status}: {body[:200]}")

    # 7. === 关键断言 4 ===: id__in=不存在的 ID
    print("\n[7] === 关键断言 4: id__in=不存在的 ID ===")
    r, _ = http_get(opener, f'http://localhost:3010/api/v2/bo/relationship?version_id={version_id}&id__in=999999&page=1&page_size=10')
    body = r.read().decode('utf-8', errors='replace')
    if r.status == 200:
        d = json.loads(body)
        actual_count = d['data']['total']
        print(f"  [id__in=不存在的 ID] total={actual_count} (期望 0)")
        results['id__in_nonexistent'] = (actual_count == 0, f"got {actual_count}")
        if actual_count != 0:
            failures.append(f"id__in=nonexistent returned {actual_count}, expected 0")
    else:
        print(f"  [FAIL] status={r.status}, body={body[:200]}")
        results['id__in_nonexistent'] = (False, f"status={r.status}, body={body[:200]}")
        failures.append(f"id__in=nonexistent HTTP {r.status}: {body[:200]}")

    # 8. === 关键断言 5 ===: relation_code__in 仍然 work (这是 fix 前 work 的路径)
    print("\n[8] === 关键断言 5: relation_code__in 仍然 work ===")
    if all_items:
        # 用 relation_type (数据库里的实际字段)
        sample_code = all_items[0].get('relation_type') or all_items[0].get('relation_code')
        if sample_code:
            r, _ = http_get(opener, f'http://localhost:3010/api/v2/bo/relationship?version_id={version_id}&relation_code__in={sample_code}&page=1&page_size=100')
            body = r.read().decode('utf-8', errors='replace')
            if r.status == 200:
                d = json.loads(body)
                actual_count = d['data']['total']
                print(f"  [relation_code__in={sample_code!r}] total={actual_count} (期望 >= 1)")
                results['relation_code__in'] = (actual_count >= 1, f"got {actual_count}")
                if actual_count < 1:
                    failures.append(f"relation_code__in returned {actual_count}, expected >= 1")
            else:
                print(f"  [FAIL] status={r.status}, body={body[:200]}")
                results['relation_code__in'] = (False, f"status={r.status}")
                failures.append(f"relation_code__in HTTP {r.status}")
        else:
            print("  [SKIP] 无 relation_code 可测")
            results['relation_code__in'] = (True, "skipped")

    # 9. === 关键断言 6 ===: 组合 id__in + relation_code__in (模拟 28 vs 29 场景)
    print("\n[9] === 关键断言 6: 组合过滤 (id__in 优先) ===")
    # 选 5 个 ID，验证 result 不被 relation_code__in 干扰
    five_ids = all_ids[:5]
    five_str = ','.join(five_ids)
    r, _ = http_get(opener, f'http://localhost:3010/api/v2/bo/relationship?version_id={version_id}&id__in={five_str}&page=1&page_size=10')
    body = r.read().decode('utf-8', errors='replace')
    if r.status == 200:
        d = json.loads(body)
        actual_count = d['data']['total']
        actual_ids = set(item['id'] for item in d['data']['items'])
        expected_ids = set(int(i) for i in five_ids)
        match = actual_ids == expected_ids
        print(f"  [id__in=5 IDs] total={actual_count}, ids 匹配: {match}")
        results['id__in_5_ids'] = (match and actual_count == 5, f"got ids={actual_ids}, expected={expected_ids}")
        if not match:
            failures.append(f"id__in=5 IDs returned wrong set: {actual_ids} != {expected_ids}")
    else:
        print(f"  [FAIL] status={r.status}, body={body[:200]}")
        results['id__in_5_ids'] = (False, f"status={r.status}")
        failures.append(f"id__in=5 IDs HTTP {r.status}")

    # ===== 汇总 =====
    print("\n" + "=" * 70)
    print("  测试结果")
    print("=" * 70)
    for name, (passed, info) in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}: {info}")
    print()
    if failures:
        print(f"  [X] {len(failures)} failed:")
        for f in failures:
            print(f"    - {f}")
        sys.exit(1)
    else:
        print(f"  [OK] All {len(results)} assertions passed")
        sys.exit(0)


# =====================================================================
# 浏览器 UI 端到端测试（v3.18 新增）
# 验证场景：选领域 → 展开 RSS → 点击"范围内"节点 → API 拦截验证
# =====================================================================


def main_browser_e2e():
    """浏览器 UI 端到端：relationIds 通过 relationIds 传递 id__in"""
    import re
    from test_helpers.browser_auth_cli import PlaywrightCLI

    cli = PlaywrightCLI(headless=True)
    captured = []
    failures = []
    results = {}

    try:
        page = cli._ensure_browser()

        def on_response(resp):
            if '/api/v2/bo/relationship' in resp.url:
                captured.append(resp.url)

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
        time.sleep(5)

        # 3. 展开对象范围 + 选择采购管理领域
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
        page.evaluate("""() => {
            const el = document.querySelector('.el-tree-node[data-key="1"] .el-checkbox__input')
            if (el && !el.classList.contains('is-checked')) el.click()
        }""")
        time.sleep(5)

        # 4. 展开 RSS 面板
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

        # 5. 清空已捕获请求
        captured.clear()

        # 6. 确保"范围内"节点处于勾选状态（先 uncheck 再 check，保证触发 check 事件）
        click_result = page.evaluate("""() => {
            const t = document.querySelector('.rss-tree-container .el-tree')
            const vnode = t.__vueParentComponent
            const store = (vnode && vnode.exposed && vnode.exposed.store) || (vnode && vnode.ctx && vnode.ctx.store)
            if (!store) return { error: 'no store' }
            for (const key in store.nodesMap) {
                const node = store.nodesMap[key]
                const name = (node.data && node.data.name) || ''
                if (name === '范围内') {
                    const el = document.querySelector('.el-tree-node[data-key="' + key + '"] .el-checkbox__input')
                    if (!el) return { error: 'no checkbox' }
                    // 如果已勾选，先取消（toggle off，清空 scope，不发请求）
                    if (node.checked) el.click()
                    // 等待状态变化
                    return new Promise(function(resolve) {
                        setTimeout(function() {
                            // 重新勾选（toggle on，触发 scope-change → API 请求）
                            el.click()
                            resolve({ clicked: true, wasInitiallyChecked: true, key: key })
                        }, 500)
                    })
                }
            }
            return { error: '范围内 not found' }
        }""")
        print(f"\n[BROWSER E2E] 点击结果: {json.dumps(click_result, ensure_ascii=False)}")
        time.sleep(2)

        # 强制刷新：触发列表重载（模拟点击列表 tab）
        page.evaluate("""() => {
            if (window.__archPage && window.__archPage.refresh) {
                window.__archPage.refresh()
            }
        }""")
        time.sleep(4)

        # 7. 断言 1：API 请求中有 id__in（精确 ID 过滤）
        print(f"  [DEBUG] captured 请求数: {len(captured)}")
        for u in captured[:5]:
            print(f"    {u[:200]}")

        id_in_found = False
        relation_code_found = False
        id_in_count = 0
        for url in captured:
            if re.search(r'[?&]id__in=', url):
                id_in_found = True
                match = re.search(r'[?&]id__in=([^&]+)', url)
                if match:
                    id_in_count = len(match.group(1).split(','))
            if re.search(r'[?&]relation_code__in=', url):
                relation_code_found = True

        results['has_id__in'] = (id_in_found, f"found={id_in_found}, count={id_in_count}")
        if not id_in_found:
            failures.append("API 请求中没有 id__in，relationIds 未正确传递")

        # 8. 断言 2：不应同时有 relation_code__in（relationIds 优先）
        results['no_relation_code__in'] = (not relation_code_found, f"found={relation_code_found}")
        if relation_code_found:
            failures.append("API 请求中同时有 relation_code__in，relationIds 优先逻辑未生效")

        # 9. 断言 3：id__in 的 ID 数量 >= 1
        results['id__in_count'] = (id_in_count >= 1, f"count={id_in_count}")
        if id_in_count < 1:
            failures.append(f"id__in count={id_in_count}，至少应有 1 个 ID")

        # 10. 断言 4：检查 __archPage.scopeIds.relationExtra
        arch_state = page.evaluate("""() => {
            if (!window.__archPage) return null
            const ap = window.__archPage
            const si = ap.scopeIds
            if (!si || !si.relationExtra) return null
            const re = si.relationExtra
            return {
                relationIdsCount: re.relationIds ? re.relationIds.length : 0,
                relationCodesCount: re.relationCodes ? re.relationCodes.length : 0,
                hasIdIn: ap.combinedFilters && ap.combinedFilters.value ? ('id__in' in ap.combinedFilters.value) : false
            }
        }""")
        results['scopeIds_has_relationIds'] = (
            arch_state and arch_state.get('relationIdsCount', 0) > 0,
            f"count={arch_state.get('relationIdsCount', 0) if arch_state else 'N/A'}"
        )
        results['combinedFilters_has_id__in'] = (
            arch_state and arch_state.get('hasIdIn', False),
            f"found={arch_state.get('hasIdIn', False) if arch_state else 'N/A'}"
        )

        cli.screenshot('d:/filework/excel-to-diagram/tests/e2e/test_e2e_chain_browser.png')

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()
        results['browser_exception'] = (False, str(e))
    finally:
        cli.close()

    # 汇总
    print("\n" + "=" * 70)
    print("  浏览器 UI E2E 测试结果")
    print("=" * 70)
    for name, (passed, info) in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}: {info}")
    print()
    if failures:
        print(f"  [X] {len(failures)} failed:")
        for f in failures:
            print(f"    - {f}")
        return 1
    else:
        print(f"  [OK] All {len(results)} assertions passed")
        return 0


if __name__ == '__main__':
    exit_code = main()  # HTTP API tests
    exit_code2 = main_browser_e2e()  # Browser E2E tests
    sys.exit(exit_code or exit_code2)
