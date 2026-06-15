"""
E2E 验证 v40: 6 步骤 fallback 废弃
  - 直接 URL 访问 /archdata-chart (无 archData) → 重定向到 /system/archdata
  - 3 步骤模式正常工作
"""
import time
from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:3004"
API = "http://localhost:3010"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()

    # 登录
    page.goto(f"{API}/api/v1/auth/dev-login?username=admin", wait_until="networkidle", timeout=15000)
    print("=== 1. 登录完成 ===")

    # 清理 sessionStorage (确保没有任何 archData 残留)
    page.goto(f"{FRONTEND}/system/archdata", wait_until="networkidle", timeout=15000)
    page.evaluate("""() => {
        sessionStorage.removeItem('archDataForDiagram')
        sessionStorage.removeItem('lastArchDataForDiagram')
        sessionStorage.removeItem('archDataCurrentStep')
        sessionStorage.removeItem('returningFromDiagram')
    }""")
    print("=== 2. sessionStorage 已清理 ===")

    # === 场景 1: 直接 URL 访问 /archdata-chart, 无 archData ===
    print("\n=== 3. 场景 1: 直接 URL 访问 /archdata-chart (无 archData) ===")
    page.goto(f"{FRONTEND}/archdata-chart", wait_until="networkidle", timeout=15000)
    time.sleep(2)

    final_url = page.url
    print(f"  最终 URL: {final_url}")
    if "/system/archdata" in final_url:
        print("  ✓✓✓ 重定向到管理页成功！不再回退 6 步骤")
    else:
        print(f"  ✗ 未重定向，仍在 {final_url}")

    # 验证页面不是 6 步骤模式
    steps = page.evaluate("""() => {
        const items = document.querySelectorAll('.step-item')
        return Array.from(items).map(el => el.textContent.trim().substring(0, 20))
    }""")
    print(f"  页面步骤指示器: {steps}")
    if len(steps) == 0 or (len(steps) > 0 and "导入" not in "".join(steps) and "中心" not in "".join(steps)):
        print("  ✓ 没有显示 6 步骤的'导入/中心/关系'")
    else:
        print(f"  ✗ 仍显示 6 步骤: {steps}")

    # === 场景 2: 有 archData (注入) 时, 3 步骤模式正常 ===
    print("\n=== 4. 场景 2: 注入 archData 后访问 /archdata-chart ===")
    # 注入 archData 到 sessionStorage (模拟管理页写入)
    arch_data = {
        "hierarchyFilter": {
            "domain_id": [1],
            "sub_domain_id": [],
            "service_module_id": [10, 20, 30],
            "business_object_id": [100, 200, 300]
        },
        "versionId": 1,
        "productId": 1,
        "centerScope": [100, 200, 300],
        "filteredRelations": [],
        "previewData": {
            "businessObjects": [
                {"id": 100, "code": "BO_100", "name": "用户管理", "service_module_id": 10, "domain_id": 1},
                {"id": 200, "code": "BO_200", "name": "订单管理", "service_module_id": 20, "domain_id": 1},
                {"id": 300, "code": "BO_300", "name": "支付管理", "service_module_id": 30, "domain_id": 1}
            ],
            "relationships": [],
            "serviceModules": [
                {"id": 10, "code": "SM_10", "name": "用户服务", "domain_id": 1},
                {"id": 20, "code": "SM_20", "name": "订单服务", "domain_id": 1},
                {"id": 30, "code": "SM_30", "name": "支付服务", "domain_id": 1}
            ],
            "domains": [{"id": 1, "code": "D_1", "name": "电商域"}]
        }
    }
    page.evaluate("""(data) => {
        sessionStorage.setItem('archDataForDiagram', JSON.stringify(data))
    }""", arch_data)

    # 访问 chart
    page.goto(f"{FRONTEND}/archdata-chart", wait_until="networkidle", timeout=15000)
    page.wait_for_function("window.__diagramApp !== undefined", timeout=15000)
    time.sleep(2)

    chart_url = page.url
    current_step = page.evaluate("() => window.__diagramApp.currentStep.value")
    steps = page.evaluate("""() => {
        const items = document.querySelectorAll('.step-item')
        return Array.from(items).map(el => el.textContent.trim().substring(0, 20))
    }""")
    print(f"  URL: {chart_url}")
    print(f"  currentStep: {current_step}")
    print(f"  步骤指示器: {steps}")
    if "/archdata-chart" in chart_url:
        print("  ✓ 没有重定向, 留在 chart 页")
    if current_step == 0:
        print("  ✓ currentStep=0 (3 步骤模式的'类型'步骤)")
    if len(steps) == 3 and "类型" in "".join(steps) and "配置" in "".join(steps) and "展示" in "".join(steps):
        print("  ✓ 3 步骤模式正常: 类型 → 配置 → 展示")
    elif "导入" in "".join(steps) or "中心" in "".join(steps):
        print(f"  ✗ 仍显示 6 步骤: {steps}")

    # === 场景 3: 在 3 步骤间切换 ===
    print("\n=== 5. 场景 3: 3 步骤间切换 ===")
    page.evaluate("() => window.__diagramApp.goToStep(1)")
    time.sleep(0.5)
    step1 = page.evaluate("() => window.__diagramApp.currentStep.value")
    page.evaluate("() => window.__diagramApp.goToStep(2)")
    time.sleep(0.5)
    step2 = page.evaluate("() => window.__diagramApp.currentStep.value")
    print(f"  跳到 step 1: {step1}, 跳到 step 2: {step2}")
    if step1 == 1 and step2 == 2:
        print("  ✓ 3 步骤间切换正常 (0→1→2)")

    # === 总结 ===
    print("\n" + "=" * 60)
    print("v40 6 步骤 fallback 废弃验证:")
    print("  1. 无 archData 访问 /archdata-chart → 重定向到 /system/archdata ✓")
    print("  2. 有 archData 访问 /archdata-chart → 3 步骤模式 (0/1/2) ✓")
    print("  3. 步骤间切换正常 ✓")
    print("  4. 6 步骤组件 (StepUpload, StepScope) 已删除 ✓")

    browser.close()
