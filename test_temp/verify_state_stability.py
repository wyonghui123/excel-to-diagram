"""
端到端验证 v39.7 状态稳定性修复

用户场景：
1. 架构管理页选择范围内+范围内与外部
2. 点击展示图表 → 跳到 chart tab
3. 第一次切回管理页 → OK
4. 再切到 chart tab
5. 第二次切回管理页 → 不应清空（修复前会清空）
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

    logs = []
    page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: logs.append(f"[err] {err}"))

    # 1. 登录
    print("=== 1. 登录 ===")
    page.goto(f"{API}/api/v1/auth/dev-login?username=admin", wait_until="networkidle", timeout=15000)
    cookies = context.cookies()
    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

    # 2. 进入管理页
    print("\n=== 2. 进入架构管理页 ===")
    page.goto(f"{FRONTEND}/system/archdata?tab=business_object", wait_until="networkidle", timeout=15000)
    time.sleep(3)

    # 3. 抓取初始 sessionStorage 状态
    print("\n=== 3. 抓取初始 sessionStorage ===")
    initial_state = page.evaluate("""() => {
        return {
            returningFromDiagram: sessionStorage.getItem('returningFromDiagram'),
            archManagerState: sessionStorage.getItem('archManagerStateBeforeDiagram')
        }
    }""")
    print(f"  initial: {json.dumps(initial_state, ensure_ascii=False)[:200]}")

    # 4. 注入测试选择状态到 scopeIds（绕过 UI 交互）
    print("\n=== 4. 注入选择状态 ===")
    inject_result = page.evaluate("""() => {
        const win = window
        if (!win.__archPage) return { ok: false, reason: 'no __archPage' }
        const ap = win.__archPage
        // 模拟用户选择
        ap.scopeIds.business_object.selected = [100, 200, 300]
        ap.scopeIds.business_object.effective = [100, 200, 300]
        ap.scopeIds.relationExtra.relationCodes = ['R1', 'R2']
        ap.scopeIds.relationExtra.relationIds = ['id-1', 'id-2', 'id-3']
        return { ok: true, scopeIds: JSON.parse(JSON.stringify(ap.scopeIds)) }
    }""")
    print(f"  注入: {json.dumps(inject_result, ensure_ascii=False)[:300]}")

    # 5. 模拟跳转图表 (调用 saveStateForDiagram)
    print("\n=== 5. 模拟跳转图表 ===")
    save_result = page.evaluate("""() => {
        const win = window
        if (!win.__archPage) return { ok: false }
        // 调用 handleShowChart 触发 saveStateForDiagram
        const chartData = win.__archPage.handleShowChart ? win.__archPage.handleShowChart() : null
        const stored = sessionStorage.getItem('archManagerStateBeforeDiagram')
        return {
            ok: true,
            hasChartData: !!chartData,
            hasStored: !!stored,
            storedLength: stored ? stored.length : 0
        }
    }""")
    print(f"  save: {json.dumps(save_result, ensure_ascii=False)}")

    # 6. 模拟第一次切回管理页 (router 设置 flag, onMounted restore)
    print("\n=== 6. 模拟第一次切回管理页 ===")
    page.evaluate("sessionStorage.setItem('returningFromDiagram', 'true')")
    # 卸载 + 重新加载管理页 (模拟 SPA 重建)
    page.evaluate("window.location.reload()")
    time.sleep(3)

    # 抓取 reload 后状态
    state_after_first = page.evaluate("""() => {
        return {
            returningFromDiagram: sessionStorage.getItem('returningFromDiagram'),
            archManagerState: sessionStorage.getItem('archManagerStateBeforeDiagram')?.substring(0, 100),
            hasArchPage: !!window.__archPage
        }
    }""")
    print(f"  after first reload: {json.dumps(state_after_first, ensure_ascii=False)}")

    # 抓取当前 scopeIds (应是注入的值)
    current_state = page.evaluate("""() => {
        if (!window.__archPage) return { error: 'no __archPage' }
        return {
            boIds: window.__archPage.scopeIds?.business_object?.selected,
            relationCodes: window.__archPage.scopeIds?.relationExtra?.relationCodes
        }
    }""")
    print(f"  current scopeIds: {json.dumps(current_state, ensure_ascii=False)}")

    # 7. 再次注入 (模拟用户可能改了)
    print("\n=== 7. 再次注入 (可能用户改了) ===")
    page.evaluate("""() => {
        if (window.__archPage) {
            window.__archPage.scopeIds.business_object.selected = [100, 200, 300, 400, 500]
            window.__archPage.scopeIds.relationExtra.relationCodes = ['R1', 'R2', 'R3']
        }
    }""")

    # 8. 模拟第二次跳转 + 切回
    print("\n=== 8. 模拟第二次切回 ===")
    # 调用 onBeforeRouteLeave 触发 saveStateForDiagram (如果挂载了)
    # 然后 router 设置 flag
    page.evaluate("""() => {
        if (window.__archPage && window.__archPage.handleShowChart) {
            window.__archPage.handleShowChart()
        }
        sessionStorage.setItem('returningFromDiagram', 'true')
    }""")
    # 再次 reload
    page.evaluate("window.location.reload()")
    time.sleep(3)

    # 9. 验证第二次恢复
    print("\n=== 9. 验证第二次恢复 ===")
    second_state = page.evaluate("""() => {
        return {
            returningFromDiagram: sessionStorage.getItem('returningFromDiagram'),
            archManagerState: sessionStorage.getItem('archManagerStateBeforeDiagram')?.substring(0, 100),
            scopeIds: window.__archPage ? {
                boIds: window.__archPage.scopeIds?.business_object?.selected,
                relationCodes: window.__archPage.scopeIds?.relationExtra?.relationCodes
            } : null
        }
    }""")
    print(f"  second restore: {json.dumps(second_state, ensure_ascii=False)}")

    # 10. 验证结果
    print("\n=== 10. 验证 ===")
    if second_state.get('scopeIds'):
        bo = second_state['scopeIds'].get('boIds', [])
        codes = second_state['scopeIds'].get('relationCodes', [])
        # 期望：第二次恢复应包含第二次注入的数据 (5 BO, 3 关系码)
        if len(bo) == 5 and len(codes) == 3:
            print(f"  ✓✓✓ 第二次恢复成功！BO={bo}, 关系码={codes}")
        elif len(bo) > 0:
            print(f"  ⚠ 恢复了一些数据: BO={len(bo)}, 关系码={len(codes)} (期望 5/3)")
        else:
            print(f"  ✗ 第二次恢复失败：数据为空（修复前会这样）")
    else:
        print(f"  ✗ __archPage 不存在")

    # 检查 console
    print("\n=== Console 日志（最后 10 条）===")
    for log in logs[-10:]:
        if 'error' in log.lower() or 'warn' in log.lower() or 'v39' in log:
            print(f"  {log[:200]}")

    browser.close()
    print("\n=== Done ===")
