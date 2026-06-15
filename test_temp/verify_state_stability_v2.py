"""
直接验证 v39.7 状态保留机制 (避开 UI 触发)

核心: sessionStorage 的 STATE_RESTORE_KEY 数据在第一次 restore 后必须保留
     用于第二次/多次 restore
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

    # 1. 登录
    page.goto(f"{API}/api/v1/auth/dev-login?username=admin", wait_until="networkidle", timeout=15000)
    page.goto(f"{FRONTEND}/system/archdata", wait_until="networkidle", timeout=15000)
    time.sleep(2)

    # 2. 模拟"用户从 chart 返回"场景：直接设置 sessionStorage
    print("=== Step 1: 模拟 saveStateForDiagram 写入 ===")
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
    page.evaluate("""(state) => {
        sessionStorage.setItem('archManagerStateBeforeDiagram', JSON.stringify(state))
        sessionStorage.setItem('returningFromDiagram', 'true')
    }""", test_state)

    after_save = page.evaluate("""() => ({
        data: !!sessionStorage.getItem('archManagerStateBeforeDiagram'),
        flag: sessionStorage.getItem('returningFromDiagram')
    })""")
    print(f"  After save: {after_save}")
    assert after_save['data'] == True, "Data should be set"
    assert after_save['flag'] == 'true', "Flag should be set"

    # 3. 重新加载管理页 (模拟 SPA 重建触发 onMounted → restoreStateFromDiagram)
    print("\n=== Step 2: Reload 触发第一次 restore ===")
    page.reload(wait_until="networkidle")
    time.sleep(2)

    after_first = page.evaluate("""() => ({
        data: sessionStorage.getItem('archManagerStateBeforeDiagram')?.substring(0, 50) + '...',
        flag: sessionStorage.getItem('returningFromDiagram'),
        dataKept: !!sessionStorage.getItem('archManagerStateBeforeDiagram')
    })""")
    print(f"  After first restore: {after_first}")

    # v39.7 验证: flag 应被清掉, 但数据应保留
    if after_first['flag'] is None and after_first['dataKept']:
        print("  ✓✓✓ 第一次 restore 行为正确：flag 清掉 + 数据保留")
    else:
        print(f"  ✗ 行为异常: flag={after_first['flag']}, dataKept={after_first['dataKept']}")

    # 4. 修改状态后重新保存 (模拟用户在管理页改了选择)
    print("\n=== Step 3: 修改状态 + 模拟第二次切回 ===")
    page.evaluate("""() => {
        // 模拟 router 检测到 from=chart, to=archdata, 设置 flag
        sessionStorage.setItem('returningFromDiagram', 'true')
    }""")
    after_set_flag = page.evaluate("""() => ({
        flag: sessionStorage.getItem('returningFromDiagram'),
        dataKept: !!sessionStorage.getItem('archManagerStateBeforeDiagram')
    })""")
    print(f"  After set flag again: {after_set_flag}")

    # 5. 重新加载管理页 (模拟第二次 SPA 重建)
    print("\n=== Step 4: Reload 触发第二次 restore ===")
    page.reload(wait_until="networkidle")
    time.sleep(2)

    after_second = page.evaluate("""() => ({
        flag: sessionStorage.getItem('returningFromDiagram'),
        dataKept: !!sessionStorage.getItem('archManagerStateBeforeDiagram')
    })""")
    print(f"  After second restore: {after_second}")

    # 6. 验证
    print("\n=== 验证 ===")
    if after_second['flag'] is None and after_second['dataKept']:
        print("  ✓✓✓ 第二次 restore 也能成功！数据仍然保留")
        print("  → 修复前: 第二次 restore 时数据已被清掉, 状态为空")
        print("  → 修复后: 数据始终保留, 多次 restore 都能拿到正确状态")
    else:
        print(f"  ✗ 第二次 restore 异常: flag={after_second['flag']}, dataKept={after_second['dataKept']}")

    # 7. 也测试数据被覆盖的场景 (第二次 save 后, 数据应是新值)
    print("\n=== Step 5: 验证数据会被新 save 覆盖 ===")
    new_state = {**test_state, "initialBoIds": [999, 888]}  # 改数据
    page.evaluate("""(state) => {
        sessionStorage.setItem('archManagerStateBeforeDiagram', JSON.stringify(state))
        sessionStorage.setItem('returningFromDiagram', 'true')
    }""", new_state)
    page.reload(wait_until="networkidle")
    time.sleep(2)

    after_overwrite = page.evaluate("""() => {
        const data = JSON.parse(sessionStorage.getItem('archManagerStateBeforeDiagram') || '{}')
        return { boIds: data.initialBoIds }
    }""")
    print(f"  After overwrite: {after_overwrite}")
    if after_overwrite.get('boIds') == [999, 888]:
        print("  ✓ 新 save 数据正确覆盖了旧数据")
    else:
        print(f"  ✗ 数据未正确覆盖: {after_overwrite}")

    browser.close()
    print("\n=== Done ===")
