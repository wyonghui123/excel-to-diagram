"""
最终端到端验证 v39.7: 用 waitForFunction 等组件挂载完成
"""
import time
import json
from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:3004"
API = "http://localhost:3010"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()

    page.goto(f"{API}/api/v1/auth/dev-login?username=admin", wait_until="networkidle", timeout=15000)
    page.goto(f"{FRONTEND}/system/archdata", wait_until="networkidle", timeout=15000)
    page.wait_for_function("window.__archPage !== undefined", timeout=15000)
    time.sleep(1)

    test_state = {
        "activeTab": "relationship",
        "scopeIds": {
            "domain": {"selected": [1], "effective": [1]},
            "business_object": {"selected": [100, 200, 300], "effective": [100, 200, 300]},
            "relationExtra": {
                "relationCodes": ["R1", "R2", "R3"],
                "relationIds": ["id-1", "id-2", "id-3", "id-4", "id-5"],
                "categoryTypes": [],
                "filterRelationCodes": []
            }
        },
        "tabFilters": {},
        "initialBoIds": [100, 200, 300],
        "initialRelationCodes": ["R1", "R2", "R3"],
        "versionId": 1,
        "productId": 1,
        "savedAt": 1700000000000
    }

    # === 第一次切回 ===
    print("=== 第一次切回 ===")
    page.evaluate("""(s) => {
        sessionStorage.setItem('archManagerStateBeforeDiagram', JSON.stringify(s))
        sessionStorage.setItem('returningFromDiagram', 'true')
    }""", test_state)
    page.reload(wait_until="networkidle")
    page.wait_for_function("window.__archPage !== undefined", timeout=15000)
    time.sleep(1)

    first = page.evaluate("""() => ({
        flag: sessionStorage.getItem('returningFromDiagram'),
        dataKept: !!sessionStorage.getItem('archManagerStateBeforeDiagram'),
        scopeIds: window.__archPage ? {
            boIds: window.__archPage.scopeIds?.business_object?.selected,
            codes: window.__archPage.scopeIds?.relationExtra?.relationCodes
        } : null
    })""")
    print(f"  {json.dumps(first, ensure_ascii=False)[:200]}")
    first_pass = first['flag'] is None and first['dataKept'] and first['scopeIds']['boIds'] == [100, 200, 300]
    print(f"  {'✓' if first_pass else '✗'} 第一次: flag cleared, data kept, scopeIds restored")

    # === 第二次切回（用户改了选择）===
    print("\n=== 第二次切回（修改后） ===")
    page.evaluate("""() => {
        // 模拟用户改了选择
        if (window.__archPage) {
            window.__archPage.scopeIds.business_object.selected = [100, 200, 300, 400, 500]
            window.__archPage.scopeIds.relationExtra.relationCodes = ['R1', 'R2', 'R3', 'R4']
        }
    }""")
    # 模拟离开时 onBeforeRouteLeave 重新 save
    page.evaluate("""(s) => {
        // 模拟 saveStateForDiagram: 用修改后的状态
        const newState = JSON.parse(JSON.stringify(s))
        newState.initialBoIds = [100, 200, 300, 400, 500]
        newState.initialRelationCodes = ['R1', 'R2', 'R3', 'R4']
        newState.scopeIds.business_object.selected = [100, 200, 300, 400, 500]
        newState.scopeIds.relationExtra.relationCodes = ['R1', 'R2', 'R3', 'R4']
        sessionStorage.setItem('archManagerStateBeforeDiagram', JSON.stringify(newState))
        sessionStorage.setItem('returningFromDiagram', 'true')
    }""", test_state)
    page.reload(wait_until="networkidle")
    page.wait_for_function("window.__archPage !== undefined", timeout=15000)
    time.sleep(1)

    second = page.evaluate("""() => ({
        flag: sessionStorage.getItem('returningFromDiagram'),
        dataKept: !!sessionStorage.getItem('archManagerStateBeforeDiagram'),
        scopeIds: window.__archPage ? {
            boIds: window.__archPage.scopeIds?.business_object?.selected,
            codes: window.__archPage.scopeIds?.relationExtra?.relationCodes
        } : null
    })""")
    print(f"  {json.dumps(second, ensure_ascii=False)[:200]}")
    second_pass = (second['scopeIds']
                  and second['scopeIds']['boIds'] == [100, 200, 300, 400, 500]
                  and second['scopeIds']['codes'] == ['R1', 'R2', 'R3', 'R4'])
    print(f"  {'✓' if second_pass else '✗'} 第二次: 修改后状态正确恢复 (5 BO, 4 关系码)")

    # === 总结 ===
    print("\n" + "=" * 50)
    if first_pass and second_pass:
        print("✓✓✓ 状态稳定性修复验证通过！")
        print("  → 第一次切回: ✓ flag 清掉, 数据保留, 状态恢复")
        print("  → 第二次切回: ✓ 新状态正确恢复")
    else:
        print("✗ 仍有异常, 需要继续排查")
        print(f"  第一次: {first_pass}")
        print(f"  第二次: {second_pass}")

    browser.close()
