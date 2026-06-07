"""诊断：查看供应链管理系统的所有版本选项"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth import authenticated_page

async def main():
    os.makedirs('d:/filework/excel-to-diagram/test_output', exist_ok=True)
    async with authenticated_page(username='admin', target_url='/system/archdata', headless=False) as page:
        await page.set_viewport_size({"width": 1680, "height": 1050})
        print("Page ready", flush=True)
        await asyncio.sleep(3)

        # 选择产品线
        selects = page.locator('.el-select')
        if await selects.count() > 0:
            await selects.nth(0).click()
            await asyncio.sleep(1500)

            # 打印所有可见选项
            opts = page.locator('.el-select-dropdown__item:visible')
            for i in range(await opts.count()):
                opt = opts.nth(i)
                if not await opt.is_visible():
                    continue
                txt = (await opt.text_content()) or ''
                print(f"[OPT] {i}: {txt.strip()}", flush=True)

            await asyncio.sleep(1000)
            await page.keyboard.press('Escape')

        # 等待后再次检查
        await asyncio.sleep(2000)

        # 选择产品线后检查版本下拉
        selects2 = page.locator('.el-select')
        count2 = await selects2.count()
        print(f"\n[INFO] 现在有 {count2} 个 selects", flush=True)

        for i in range(count2):
            txt = await selects2.nth(i).text_content()
            print(f"[INFO] Select #{i}: {(txt or '').strip()[:80]}", flush=True)

        if count2 > 1:
            await selects2.nth(1).click()
            await asyncio.sleep(1500)

            opts3 = page.locator('.el-select-dropdown__item:visible')
            for i in range(await opts3.count()):
                opt = opts3.nth(i)
                if not await opt.is_visible():
                    continue
                txt = (await opt.text_content()) or ''
                print(f"[VERSION OPT] {i}: {txt.strip()}", flush=True)

            await page.keyboard.press('Escape')

        await page.screenshot(path='d:/filework/excel-to-diagram/test_output/m5_diag_final.png', full_page=True)
        print("\nDone", flush=True)

asyncio.run(main())
