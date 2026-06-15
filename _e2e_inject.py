"""
直接注入到 Vue 组件，验证 fix 行为
不走 UI 点击，直接调用 Vue 内部状态
"""
import asyncio
import json
from playwright.async_api import async_playwright

FRONTEND_URL = "http://localhost:3004"
LOGIN_URL = f"{FRONTEND_URL}/#/login"
LOG_FILE = "d:/filework/_e2e_inject.log"

API_CALLS = []


def flog(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


async def main():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        async def on_request(req):
            url = req.url
            if "/api/v2/bo/relationship" in url or "/bo/relationship" in url:
                API_CALLS.append({"method": req.method, "url": url})
                flog(f"[API] {req.method} {url}")

        page.on("request", on_request)
        page.on("pageerror", lambda e: flog(f"[PAGEERROR] {e}"))

        # 1. 登录
        flog("=" * 80)
        flog("Step 1: 登录")
        flog("=" * 80)
        await page.goto(LOGIN_URL, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        inputs = await page.locator("input").all()
        await inputs[0].fill("admin")
        await inputs[1].fill("admin123")
        await page.locator("button.login-btn").first.click()
        await page.wait_for_timeout(3000)
        flog(f"After login URL: {page.url}")

        # 2. 进数据管理页
        flog("=" * 80)
        flog("Step 2: 进架构数据管理")
        flog("=" * 80)
        await page.goto(f"{FRONTEND_URL}/#/data-manager?menu=architecture&_t=1", wait_until="networkidle")
        await page.wait_for_timeout(3000)

        all_cards = await page.locator("text=架构数据管理").all()
        for el in all_cards:
            if await el.is_visible():
                await el.click(force=True)
                break
        flog("Card clicked")
        await page.wait_for_timeout(5000)
        flog(f"URL: {page.url}")

        # 3. 选 供应链管理系统 + 新测试2
        flog("=" * 80)
        flog("Step 3: 选 供应链管理系统 + 新测试2")
        flog("=" * 80)

        async def pick_option(idx, label, match_text):
            selects = await page.locator(".el-select").all()
            await selects[idx].click(force=True)
            await page.wait_for_timeout(2000)
            for _ in range(8):
                options = await page.locator(".el-select-dropdown__item:visible").all()
                if options:
                    found = None
                    for o in options:
                        t = (await o.text_content() or "").strip()
                        if match_text in t:
                            found = o
                            break
                    if found:
                        await found.click(force=True)
                    else:
                        await options[0].click(force=True)
                    await page.wait_for_timeout(3000)
                    return True
                await page.wait_for_timeout(1000)
            return False

        await pick_option(0, "Product", "供应链")
        await pick_option(1, "Version", "新测试")
        await page.wait_for_timeout(5000)

        # 4. 检查 window.__archPage
        flog("=" * 80)
        flog("Step 4: 检查 window.__archPage")
        flog("=" * 80)

        # Wait for the dev exposure
        await page.wait_for_timeout(3000)
        has_arch_page = await page.evaluate("() => typeof window.__archPage !== 'undefined'")
        flog(f"window.__archPage exists: {has_arch_page}")

        if not has_arch_page:
            # 看看 main bundle 是否重新加载 (因为我们刚改了 useMultiObjectPage.js)
            flog("window.__archPage 不存在, 尝试查找")
            # 列出 window 上所有 __ 开头的属性
            win_keys = await page.evaluate("() => Object.keys(window).filter(k => k.startsWith('__'))")
            flog(f"window.__ keys: {win_keys}")
            # 找全部含 scopeIds 的对象
            scopeIds_locations = await page.evaluate("""
                () => {
                    // 找 Vue app
                    const app = document.querySelector('#app');
                    if (!app || !app.__vue_app__) return { error: 'no app or __vue_app__' };
                    return {
                        app_keys: Object.keys(app.__vue_app__),
                        // 找 context 中的 _context.config.globalProperties
                        globalProps_keys: Object.keys(app.__vue_app__._context?.config?.globalProperties || {})
                    };
                }
            """)
            flog(f"Vue app info: {json.dumps(scopeIds_locations, ensure_ascii=False)[:500]}")
            flog("FATAL: window.__archPage 不可用, abort")
            await browser.close()
            return

        # 验证 __archPage 暴露
        arch_info = await page.evaluate("""
            () => {
                const p = window.__archPage;
                return {
                    has_scopeIds: !!p.scopeIds,
                    has_tabFilters: !!p.tabFilters,
                    has_combinedFilters: !!p.combinedFilters,
                    has_handleScopeChange: typeof p.handleScopeChange === 'function',
                    objectTypes: p.objectTypes,
                    activeTab: typeof p.activeTab === 'object' ? p.activeTab.value : p.activeTab
                };
            }
        """)
        flog(f"__archPage info: {json.dumps(arch_info, ensure_ascii=False)}")

        # 5. 直接设置 scopeIds.relationExtra.relationIds (28 INTERNAL IDs) - 模拟选 范围内
        flog("=" * 80)
        flog("Step 5: 模拟 选 范围内 (relationIds=28)")
        flog("=" * 80)
        API_CALLS.clear()

        # 28 个 IDs 模拟 (用 1-28)
        await page.evaluate("""
            () => {
                const page = window.__archPage;
                const re = page.scopeIds.relationExtra;
                // 模拟范围内: 28 IDs
                page.handleScopeChange({
                    relationCodes: ['PROVIDES', 'ORDERS', 'CONTAINS', 'RESERVES'],  // 用户勾选的一些 relation_codes
                    relationIds: Array.from({length: 28}, (_, i) => i + 1),  // 28 IDs
                    categoryTypes: [],
                    filterRelationCodes: [],
                    boIds: []
                });
            }
        """)
        await page.wait_for_timeout(3000)

        flog(f"API calls after 范围内 (28 IDs): {len(API_CALLS)}")
        for c in API_CALLS:
            flog(f"  {c['method']} {c['url']}")

        # 读 tabFilters / combinedFilters 状态
        state_after_within = await page.evaluate("""
            () => {
                const page = window.__archPage;
                const tf = page.tabFilters?.value || page.tabFilters;
                const cf = page.combinedFilters?.value || page.combinedFilters;
                return {
                    scopeIds_relationExtra: JSON.parse(JSON.stringify(page.scopeIds.relationExtra || {})),
                    tabFilters_relationship: JSON.parse(JSON.stringify(tf?.relationship || {})),
                    combinedFilters: JSON.parse(JSON.stringify(cf || {}))
                };
            }
        """)
        flog(f"State after 范围内:")
        flog(json.dumps(state_after_within, ensure_ascii=False, indent=2))

        # 6. 模拟 选 范围内 + 范围内与外部 (29 IDs, 包含 cross-boundary)
        flog("=" * 80)
        flog("Step 6: 模拟 选 范围内 + 范围内与外部 (relationIds=29)")
        flog("=" * 80)
        API_CALLS.clear()

        await page.evaluate("""
            () => {
                const page = window.__archPage;
                // 模拟 范围内 + 范围内与外部: 29 IDs (含 cross-boundary id=29)
                page.handleScopeChange({
                    relationCodes: ['PROVIDES', 'ORDERS', 'CONTAINS', 'RESERVES', ''],  // 多了空字符串
                    relationIds: Array.from({length: 29}, (_, i) => i + 1),  // 29 IDs
                    categoryTypes: [],
                    filterRelationCodes: [],
                    boIds: []
                });
            }
        """)
        await page.wait_for_timeout(3000)

        flog(f"API calls after 范围内+范围内与外部 (29 IDs): {len(API_CALLS)}")
        for c in API_CALLS:
            flog(f"  {c['method']} {c['url']}")

        state_after_ext = await page.evaluate("""
            () => {
                const page = window.__archPage;
                const tf = page.tabFilters?.value || page.tabFilters;
                const cf = page.combinedFilters?.value || page.combinedFilters;
                return {
                    scopeIds_relationExtra: JSON.parse(JSON.stringify(page.scopeIds.relationExtra || {})),
                    tabFilters_relationship: JSON.parse(JSON.stringify(tf?.relationship || {})),
                    combinedFilters: JSON.parse(JSON.stringify(cf || {}))
                };
            }
        """)
        flog(f"State after 范围内+范围内与外部:")
        flog(json.dumps(state_after_ext, ensure_ascii=False, indent=2))

        # 保存
        with open("d:/filework/_e2e_state.json", "w", encoding="utf-8") as f:
            json.dump({
                "api_calls_within": [c for c in API_CALLS if "id__in" in c.get("url","")],
                "state_after_within": state_after_within,
                "state_after_ext": state_after_ext
            }, f, ensure_ascii=False, indent=2)
        flog("Saved state to d:/filework/_e2e_state.json")

        await browser.close()
        flog("DONE")


asyncio.run(main())
