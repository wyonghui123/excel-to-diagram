"""
直接测试 buildAssociationFilterParams + tabFilters 行为
"""
import asyncio
import json
from playwright.async_api import async_playwright

FRONTEND_URL = "http://localhost:3004"
LOGIN_URL = f"{FRONTEND_URL}/#/login"
LOG_FILE = "d:/filework/_e2e_direct.log"


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
        page.on("pageerror", lambda e: flog(f"[PAGEERROR] {e}"))

        # 登录 + 进数据管理
        flog("Step 1-3: 登录 + 进架构数据管理 + 选 product/version")
        await page.goto(LOGIN_URL, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        inputs = await page.locator("input").all()
        await inputs[0].fill("admin")
        await inputs[1].fill("admin123")
        await page.locator("button.login-btn").first.click()
        await page.wait_for_timeout(3000)

        await page.goto(f"{FRONTEND_URL}/#/data-manager?menu=architecture&_t=1", wait_until="networkidle")
        await page.wait_for_timeout(3000)
        for el in await page.locator("text=架构数据管理").all():
            if await el.is_visible():
                await el.click(force=True)
                break
        await page.wait_for_timeout(5000)

        async def pick_option(idx, match_text):
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

        await pick_option(0, "供应链")
        await pick_option(1, "新测试")
        await page.wait_for_timeout(5000)

        # Step 4: 直接调用 _buildAssociationFilters 并 trace
        flog("=" * 80)
        flog("Step 4: 直接测试 _buildAssociationFilters 行为")
        flog("=" * 80)

        # 先直接读取 state
        result = await page.evaluate("""
            () => {
                const p = window.__archPage;
                const re = p.scopeIds.relationExtra;
                return {
                    'relationExtra.relationIds.length': re.relationIds.length,
                    'relationExtra.relationCodes.length': re.relationCodes.length,
                    'relationExtra.relationIds': re.relationIds,
                    'relationExtra.relationCodes': re.relationCodes,
                    'tabFiltersVersion': p.tabFiltersVersion?.value
                };
            }
        """)
        flog(f"Initial state: {json.dumps(result, ensure_ascii=False)[:500]}")

        # 先调一次 buildAssociationFilterParams (直接通过 import 路径)
        result = await page.evaluate("""
            async () => {
                // 直接用 import 动态加载 hierarchyService
                const mod = await import('/src/services/hierarchyService.js');
                const p = window.__archPage;
                const levels = await (await import('/src/composables/useHierarchyTypes.js')).useHierarchyTypes();

                // 先 set state
                p.handleScopeChange({
                    relationCodes: ['PROVIDES', 'ORDERS', 'CONTAINS', 'RESERVES'],
                    relationIds: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                    categoryTypes: [],
                    filterRelationCodes: [],
                    boIds: []
                });

                // 立刻读 state
                const re = p.scopeIds.relationExtra;
                const state1 = {
                    'relationExtra.relationIds.length': re.relationIds.length,
                    'relationExtra.relationCodes.length': re.relationCodes.length
                };

                // 直接调用 buildAssociationFilterParams
                const result1 = mod.buildAssociationFilterParams({
                    levels: levels.levels.value,
                    scopeIds: p.scopeIds,
                    relationExtra: re
                });
                const result2 = mod.buildAssociationFilterParams({
                    levels: levels.levels.value,
                    scopeIds: p.scopeIds,
                    relationExtra: p.scopeIds.relationExtra
                });

                return {
                    state_after_set: state1,
                    'result with explicit re': result1,
                    'result with p.scopeIds.relationExtra': result2,
                    'tabFilters.relationship (after handleScopeChange)': p.tabFilters?.value?.relationship || p.tabFilters?.relationship
                };
            }
        """)
        flog(f"Direct test result:")
        flog(json.dumps(result, ensure_ascii=False, indent=2))

        await browser.close()
        flog("DONE")


asyncio.run(main())
