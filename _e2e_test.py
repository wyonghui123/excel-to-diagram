"""Focused E2E: verify the bug fix in real browser.

Flow:
1. Login
2. Navigate to /system/archdata (fresh page, bypass HMR cache)
3. Select product=供应链管理系统 + version=新测试2_1780899784189
4. Click 采购管理 in object scope
5. Click 关系范围 panel
6. Click 范围内 parent (should select 28 internal)
7. Click 范围内与外部 parent (should add 1 cross-boundary = 29 total)
8. Verify the API call to /api/v2/bo/relationship contains id__in=29 IDs and NO relation_code__in
9. Verify the relationship list shows 29 records (total=29)
"""
import asyncio
from playwright.async_api import async_playwright

API_LOG = []
CONSOLE_LOG = []

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, args=['--disable-cache'])
        context = await browser.new_context(
            viewport={"width": 1600, "height": 1000},
            ignore_https_errors=True,
        )
        # Force no cache
        await context.route("**/*", lambda route: route.continue_())

        page = await context.new_page()
        page.on('console', lambda m: CONSOLE_LOG.append(f"[{m.type}] {m.text}"))
        page.on('response', lambda r: API_LOG.append({
            'url': r.url,
            'status': r.status,
            'method': r.request.method,
        }) if '/api/' in r.url and 'relationship' in r.url.lower() else None)

        # 1. Login
        await page.goto('http://localhost:3010/api/v1/auth/dev-login?username=admin')
        await page.wait_for_timeout(2000)
        print("[1] Logged in")

        # 2. Navigate to SPA with cache buster
        cache_ts = __import__('time').time()
        await page.goto(f'http://localhost:3004/?nocache={cache_ts}')
        await page.wait_for_timeout(3000)
        print("[2] SPA loaded")

        # 3. SPA internal navigation
        await page.evaluate("""() => {
            const app = document.querySelector('#app').__vue_app__;
            if (app && app.config.globalProperties.$router) {
                app.config.globalProperties.$router.push('/system/archdata');
            }
        }""")
        await page.wait_for_timeout(8000)
        print("[3] Navigated to archdata")

        # 4. Click product dropdown
        try:
            await page.locator('.el-select').first.click(timeout=15000)
            await page.wait_for_timeout(1500)
            # Find and click 供应链管理系统
            await page.locator('.el-select-dropdown__item:has-text("供应链管理系统")').first.click(timeout=5000)
            print("[4] Selected product")
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[4] ERROR: {e}")
            await page.screenshot(path='d:/filework/excel-to-diagram/_e2e_step4.png')
            return

        # 5. Click version dropdown
        try:
            await page.locator('.el-select').nth(1).click(timeout=15000)
            await page.wait_for_timeout(1500)
            # Find and click 新测试2_1780899784189
            await page.locator('.el-select-dropdown__item:has-text("新测试2_1780899784189")').first.click(timeout=5000)
            print("[5] Selected version")
            await page.wait_for_timeout(8000)
        except Exception as e:
            print(f"[5] ERROR: {e}")
            await page.screenshot(path='d:/filework/excel-to-diagram/_e2e_step5.png')
            return

        # 6. Click 采购管理 in object scope
        try:
            await page.get_by_text('采购管理', exact=False).first.scroll_into_view_if_needed(timeout=10000)
            row = page.get_by_text('采购管理', exact=False).first.locator('xpath=ancestor::*[contains(@class, "el-tree-node__content")][1]')
            await row.locator('.el-checkbox').first.click(timeout=5000)
            print("[6] Clicked 采购管理")
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[6] ERROR: {e}")
            await page.screenshot(path='d:/filework/excel-to-diagram/_e2e_step6.png')
            return

        # 7. Click 关系范围 panel
        try:
            await page.get_by_text('关系范围', exact=False).first.scroll_into_view_if_needed(timeout=10000)
            await page.get_by_text('关系范围', exact=False).first.click(timeout=5000)
            print("[7] Opened 关系范围 panel")
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[7] ERROR: {e}")
            await page.screenshot(path='d:/filework/excel-to-diagram/_e2e_step7.png')
            return

        # 8. Click 范围内 parent
        try:
            await page.get_by_text('范围内', exact=True).first.scroll_into_view_if_needed(timeout=10000)
            row = page.get_by_text('范围内', exact=True).first.locator('xpath=ancestor::*[contains(@class, "el-tree-node__content")][1]')
            await row.locator('.el-checkbox').first.click(timeout=5000)
            print("[8] Clicked 范围内")
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[8] ERROR: {e}")
            await page.screenshot(path='d:/filework/excel-to-diagram/_e2e_step8.png')
            return

        # 9. Click 范围内与外部 parent
        try:
            await page.get_by_text('范围内与外部', exact=True).first.scroll_into_view_if_needed(timeout=10000)
            row = page.get_by_text('范围内与外部', exact=True).first.locator('xpath=ancestor::*[contains(@class, "el-tree-node__content")][1]')
            await row.locator('.el-checkbox').first.click(timeout=5000)
            print("[9] Clicked 范围内与外部")
            await page.wait_for_timeout(5000)
        except Exception as e:
            print(f"[9] ERROR: {e}")
            await page.screenshot(path='d:/filework/excel-to-diagram/_e2e_step9.png')
            return

        # 10. Check relationship count in list
        await page.screenshot(path='d:/filework/excel-to-diagram/_e2e_final.png', full_page=True)
        print("[10] Final screenshot saved")

        await browser.close()

    # Save logs
    with open('d:/filework/excel-to-diagram/_e2e_api.log', 'w', encoding='utf-8') as f:
        f.write('=== API CALLS (relationship) ===\n')
        for entry in API_LOG:
            if entry:
                f.write(f"[{entry['status']}] {entry['method']} {entry['url']}\n")

    with open('d:/filework/excel-to-diagram/_e2e_console.log', 'w', encoding='utf-8') as f:
        f.write('=== CONSOLE LOGS (DBG only) ===\n')
        # Filter for DBG and important entries
        for line in CONSOLE_LOG:
            if 'DBG' in line:
                f.write(line + '\n')

    # Print summary
    print(f"\n=== SUMMARY ===")
    print(f"Total API calls: {len([x for x in API_LOG if x])}")
    rel_calls = [x for x in API_LOG if x and 'bo/relationship' in x['url']]
    print(f"bo/relationship calls: {len(rel_calls)}")
    for c in rel_calls:
        # extract id__in and relation_code__in
        url = c['url']
        id_in = ''
        rel_in = ''
        if 'id__in=' in url:
            import re
            m = re.search(r'id__in=([^&]+)', url)
            if m:
                ids = m.group(1).split('%2C')
                id_in = f"id__in=[{len(ids)} IDs: {','.join(ids[:5])}...]"
        if 'relation_code__in=' in url:
            m = re.search(r'relation_code__in=([^&]+)', url)
            if m:
                codes = m.group(1).split('%2C')
                rel_in = f"relation_code__in=[{len(codes)} codes: {','.join(codes[:5])}...]"
        print(f"  {id_in}")
        print(f"  {rel_in}")

asyncio.run(main())
