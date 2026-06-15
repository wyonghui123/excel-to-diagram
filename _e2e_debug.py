"""
跑 direct 测试 + 抓 console log
"""
import asyncio
import json
from playwright.async_api import async_playwright

FRONTEND_URL = "http://localhost:3004"
LOGIN_URL = f"{FRONTEND_URL}/#/login"
LOG_FILE = "d:/filework/_e2e_debug.log"

ALL_CONSOLE = []


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

        page.on("console", lambda m: ALL_CONSOLE.append(f"[{m.type}] {m.text}"))
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

        # 清空 console
        ALL_CONSOLE.clear()

        # 设置 state
        flog("=" * 80)
        flog("Setting state with relationIds=[1..10], relationCodes=[A,B,C,D]")
        flog("=" * 80)

        await page.evaluate("""
            () => {
                window.__archPage.handleScopeChange({
                    relationCodes: ['A', 'B', 'C', 'D'],
                    relationIds: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
                    categoryTypes: [],
                    filterRelationCodes: [],
                    boIds: []
                });
            }
        """)
        await page.wait_for_timeout(3000)

        # 读取 state
        result = await page.evaluate("""
            () => {
                const p = window.__archPage;
                return {
                    'scopeIds.relationExtra.relationIds.length': p.scopeIds.relationExtra.relationIds.length,
                    'scopeIds.relationExtra.relationCodes': p.scopeIds.relationExtra.relationCodes,
                    'tabFiltersVersion.value': p.tabFiltersVersion?.value,
                    'tabFilters.relationship': p.tabFilters?.value?.relationship || p.tabFilters?.relationship
                };
            }
        """)
        flog(f"State after handleScopeChange: {json.dumps(result, ensure_ascii=False)}")

        # 输出 console
        flog("=" * 80)
        flog("Console output (last 50):")
        flog("=" * 80)
        dbg_logs = [c for c in ALL_CONSOLE if '[DBG-' in c]
        for c in dbg_logs[-50:]:
            flog(c)
        flog(f"Total DBG logs: {len(dbg_logs)}")

        await browser.close()
        flog("DONE")


asyncio.run(main())
