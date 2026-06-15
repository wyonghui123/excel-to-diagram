"""
直接测试 isAssociation('relationship') 返回什么
"""
import asyncio
import json
from playwright.async_api import async_playwright

FRONTEND_URL = "http://localhost:3004"
LOGIN_URL = f"{FRONTEND_URL}/#/login"
LOG_FILE = "d:/filework/_e2e_kind.log"


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

        # 直接检查 isAssociation
        result = await page.evaluate("""
            async () => {
                const mod = await import('/src/services/hierarchyService.js');
                // 从 page.__archPage 拿 levels
                const p = window.__archPage;
                // levels 是 ref (因为在 setup 里用 useHierarchyTypes 返回 ref)
                // 我们需要 useHierarchyTypes 重新拿
                const ht = await import('/src/composables/useHierarchyTypes.js');
                const levels = ht.useHierarchyTypes();
                const levelsValue = levels.levels.value;

                const isAssoc = mod.isAssociation(levelsValue, 'relationship');
                const isEntity = mod.isEntity(levelsValue, 'relationship');
                const findResult = mod.findLevel(levelsValue, 'relationship');
                const getKindResult = mod.getKind(levelsValue, 'relationship');

                // 检查 levels 中有哪些 object_type
                const objectTypesInLevels = levelsValue.map(l => ({
                    type: l.object_type || l.object,
                    kind: l.kind
                }));

                return {
                    isAssociation: isAssoc,
                    isEntity: isEntity,
                    findLevel: findResult,
                    getKind: getKindResult,
                    objectTypesInLevels
                };
            }
        """)
        flog(f"isAssociation test:")
        flog(json.dumps(result, ensure_ascii=False, indent=2))

        await browser.close()
        flog("DONE")


asyncio.run(main())
