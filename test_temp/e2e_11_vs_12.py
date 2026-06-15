"""
端到端测试：复现 图表页 11 vs 管理页 12 的关系数差异

步骤：
1. 登录
2. 进入架构数据管理页
3. 选择对象范围（按用户场景：1领域 1子域 5服务 9对象）
4. 选择关系范围（2个范围内关系）
5. 抓取管理页的关系数
6. 跳转到图表页
7. 抓取图表页导航的关系数
8. 对比

同时注入 console 日志抓取和 __diagramApp 状态，定位根因。
"""
import json
import time
from playwright.sync_api import sync_playwright

FRONTEND = "http://localhost:3004"
API = "http://localhost:3010"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()

    logs = []
    page.on("console", lambda msg: logs.append(f"[{msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: logs.append(f"[pageerror] {err}"))

    # 1. 登录
    print("=== Step 1: 登录 ===")
    page.goto(f"{FRONTEND}/", wait_until="networkidle", timeout=30000)
    # dev-login
    page.goto(f"{API}/api/v1/auth/dev-login?username=admin", wait_until="networkidle", timeout=30000)
    print("已登录")

    # 2. 进入架构管理页
    print("\n=== Step 2: 进入架构管理页 ===")
    # 找入口链接
    page.goto(f"{FRONTEND}/arch-data-manager", wait_until="networkidle", timeout=30000)
    time.sleep(2)

    # 3. 等待树加载并选择对象范围
    print("\n=== Step 3: 选择对象范围 ===")
    # 找版本选择器
    try:
        # 尝试找到产品/版本下拉
        page.wait_for_selector('.el-select', timeout=10000)
        selects = page.locator('.el-select').all()
        print(f"  找到 {len(selects)} 个 el-select")

        # 点击第一个（产品）
        if len(selects) >= 1:
            selects[0].click()
            time.sleep(1)
            # 选择第一个 option
            opts = page.locator('.el-select-dropdown__item').all()
            if opts:
                opts[0].click()
                time.sleep(1)

        # 点击第二个（版本）
        selects = page.locator('.el-select').all()
        if len(selects) >= 2:
            selects[1].click()
            time.sleep(1)
            opts = page.locator('.el-select-dropdown__item').all()
            if opts:
                opts[0].click()
                time.sleep(2)
    except Exception as e:
        print(f"  选择版本失败: {e}")

    # 抓取当前页面状态
    print("\n=== 当前页面 URL ===")
    print(page.url)

    # 抓取管理页的关系数（badge）
    print("\n=== Step 4: 抓取管理页关系数 ===")
    try:
        # 找"关系范围"面板的 badge
        relation_badges = page.locator('.collapsible-panel__badge').all()
        for i, badge in enumerate(relation_badges):
            text = badge.inner_text()
            print(f"  Badge[{i}]: {text}")
    except Exception as e:
        print(f"  抓取 badge 失败: {e}")

    # 5. 抓取 __diagramApp 全局状态（如果存在）
    print("\n=== Step 5: 抓取 window 全局状态 ===")
    diag_data = page.evaluate("""() => {
        const result = {};
        if (window.__diagramApp) {
            result.has_diagram_app = true;
        }
        if (window.__pinia__ || window.__VUE_DEVTOOLS_GLOBAL_HOOK__) {
            result.has_devtools = true;
        }
        // 抓取所有 .stat 元素
        const stats = document.querySelectorAll('.stat-value, .step-stats-inline');
        result.stat_texts = Array.from(stats).map(el => el.textContent?.trim());
        return result;
    }""")
    print(f"  {json.dumps(diag_data, ensure_ascii=False, indent=2)}")

    # 6. 跳转到图表页
    print("\n=== Step 6: 跳转到图表页 ===")
    # 找"展示图表"或"生成图表"按钮
    try:
        # 尝试找按钮
        chart_btn = page.locator('button:has-text("展示"), button:has-text("图表"), a:has-text("图表")').first
        if chart_btn.is_visible():
            chart_btn.click()
            time.sleep(3)
        else:
            # 直接跳路由
            page.goto(f"{FRONTEND}/diagram", wait_until="networkidle", timeout=30000)
            time.sleep(3)
    except Exception as e:
        print(f"  跳转失败: {e}")
        page.goto(f"{FRONTEND}/diagram", wait_until="networkidle", timeout=30000)
        time.sleep(3)

    print(f"  当前 URL: {page.url}")

    # 7. 抓取图表页导航的关系数
    print("\n=== Step 7: 抓取图表页导航关系数 ===")
    nav_stats = page.evaluate("""() => {
        const items = document.querySelectorAll('.step-stats-inline, .step-stats, .navigate-stats');
        return Array.from(items).map(el => el.textContent?.trim());
    }""")
    print(f"  导航统计: {nav_stats}")

    # 8. 抓取预览数据
    print("\n=== Step 8: 抓取预览数据 ===")
    preview_info = page.evaluate("""() => {
        // 尝试从 Vue 实例获取
        const root = document.querySelector('#app, [data-v-app]');
        if (!root) return { error: 'no root' };

        // 抓取所有统计数字
        const allText = document.body.innerText;
        const relationMatches = allText.match(/\\d+\\s*关系/g);
        return {
            body_relation_matches: relationMatches,
            body_length: allText.length
        };
    }""")
    print(f"  {json.dumps(preview_info, ensure_ascii=False, indent=2)}")

    # 9. 抓取 console 日志
    print("\n=== Step 9: Console 日志（最近 30 条）===")
    for log in logs[-30:]:
        print(f"  {log[:200]}")

    browser.close()
    print("\n=== 测试完成 ===")
