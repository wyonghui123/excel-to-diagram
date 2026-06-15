"""
Playwright e2e: trigger the user's flow and capture all console logs.
Updated: Vite dev server at 3004, use version 1 (29 records), product=供应链管理系统.
"""
import asyncio
from playwright.async_api import async_playwright

LOG_FILE = "d:/filework/excel-to-diagram/debug_console.log"

async def main():
    captured = []
    network_failures = []
    api_calls = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1600, "height": 1000})

        def handle_console(msg):
            text = msg.text
            # only keep relevant lines
            if 'DEBUG-' in text or '[RelationScopeSection]' in text or 'pageerror' in text.lower():
                captured.append(f"[console.{msg.type}] {text}")

        def handle_response(resp):
            url = resp.url
            if '/api/' in url and ('relationship' in url.lower() or 'business_object' in url.lower()):
                api_calls.append(f"[api.{resp.status}] {resp.request.method} {url}")

        page = await context.new_page()
        page.on('console', handle_console)
        page.on('pageerror', lambda err: captured.append(f"[pageerror] {err}"))
        page.on('response', handle_response)

        # Login first via API
        await page.goto('http://localhost:3010/api/v1/auth/dev-login?username=admin')
        await page.wait_for_timeout(2000)
        captured.append("--- LOGGED IN ---")

        # Navigate to the SPA on Vite (3004), then to archdata page
        await page.goto('http://localhost:3004/?_t=' + str(__import__('time').time()))
        await page.wait_for_timeout(3000)
        captured.append("--- SPA LOADED ---")

        # Use SPA internal navigation
        await page.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__;
                if (app) {
                    const router = app.config.globalProperties.$router;
                    router.push('/system/archdata');
                }
            }
        """)
        await page.wait_for_timeout(10000)
        captured.append("--- NAVIGATED TO ARCHDATA ---")

        # Wait for page
        await page.wait_for_timeout(3000)
        captured.append("--- WAITED 3s ---")

        # Click product dropdown - first el-select
        try:
            product_combobox = page.locator('.el-select').first
            await product_combobox.wait_for(timeout=10000)
            await product_combobox.click()
            await page.wait_for_timeout(2000)
            captured.append("[action] Clicked product dropdown")

            # Find and click "供应链管理系统"
            options = page.locator('.el-select-dropdown__item:visible')
            count = await options.count()
            captured.append(f"[info] Found {count} product options visible")
            target_product = "供应链管理系统"
            found = False
            for i in range(count):
                text = (await options.nth(i).text_content() or "").strip()
                if target_product in text:
                    await options.nth(i).click()
                    captured.append(f"[action] Selected product: {text}")
                    found = True
                    break
            if not found:
                captured.append(f"[action.error] Could not find product '{target_product}'")
                # List all options
                for i in range(count):
                    text = (await options.nth(i).text_content() or "").strip()
                    captured.append(f"  product[{i}]: {text}")
                # Close dropdown
                await page.keyboard.press("Escape")
            await page.wait_for_timeout(3000)
        except Exception as e:
            captured.append(f"[action.error] Product selection failed: {e}")

        # Click version dropdown - second el-select
        try:
            version_combobox = page.locator('.el-select').nth(1)
            await version_combobox.wait_for(timeout=10000)
            await version_combobox.click()
            await page.wait_for_timeout(2000)
            captured.append("[action] Clicked version dropdown")

            # Find and click "新测试2_1780899784189"
            options = page.locator('.el-select-dropdown__item:visible')
            count = await options.count()
            captured.append(f"[info] Found {count} version options visible")
            target_version = "新测试2_1780899784189"
            found = False
            for i in range(count):
                text = (await options.nth(i).text_content() or "").strip()
                captured.append(f"  version[{i}]: {text}")
                if target_version in text:
                    await options.nth(i).click()
                    captured.append(f"[action] Selected version: {text}")
                    found = True
                    break
            if not found:
                captured.append(f"[action.error] Could not find version '{target_version}'")
                await page.keyboard.press("Escape")
            await page.wait_for_timeout(8000)
        except Exception as e:
            captured.append(f"[action.error] Version selection failed: {e}")

        # Take a screenshot
        await page.screenshot(path='d:/filework/excel-to-diagram/debug_page_v2.png', full_page=True)
        captured.append("--- SCREENSHOT v2 saved ---")

        # Try to find 采购管理 in object scope
        try:
            procurement = page.get_by_text('采购管理').first
            await procurement.wait_for(timeout=15000)
            captured.append("[wait] 采购管理 visible")
            await procurement.scroll_into_view_if_needed(timeout=10000)
            # Get the row's checkbox
            row = procurement.locator('xpath=ancestor::*[contains(@class, "el-tree-node__content")][1]')
            checkbox = row.locator('.el-checkbox').first
            await checkbox.click()
            await page.wait_for_timeout(3000)
            captured.append("[action] Clicked 采购管理 checkbox")
        except Exception as e:
            captured.append(f"[action.error] Click 采购管理 failed: {e}")

        # Look for 关系范围 panel header
        try:
            rel_label = page.get_by_text('关系范围', exact=False).first
            await rel_label.wait_for(timeout=10000)
            await rel_label.scroll_into_view_if_needed(timeout=10000)
            await rel_label.click()
            await page.wait_for_timeout(3000)
            captured.append("[action] Clicked 关系范围 panel")
        except Exception as e:
            captured.append(f"[action.error] Open 关系范围 panel failed: {e}")

        await page.wait_for_timeout(5000)

        # Click 范围内 parent checkbox
        try:
            internal_label = page.get_by_text('范围内', exact=True).first
            await internal_label.wait_for(timeout=15000)
            await internal_label.scroll_into_view_if_needed(timeout=15000)
            row = internal_label.locator('xpath=ancestor::*[contains(@class, "el-tree-node__content")][1]')
            checkbox = row.locator('.el-checkbox').first
            await checkbox.click()
            await page.wait_for_timeout(3000)
            captured.append("[action] Clicked 范围内 parent checkbox")
        except Exception as e:
            captured.append(f"[action.error] Click 范围内 parent failed: {e}")

        await page.wait_for_timeout(3000)

        # Click 范围内与外部 parent checkbox
        try:
            cross_label = page.get_by_text('范围内与外部', exact=True).first
            await cross_label.wait_for(timeout=15000)
            await cross_label.scroll_into_view_if_needed(timeout=15000)
            row = cross_label.locator('xpath=ancestor::*[contains(@class, "el-tree-node__content")][1]')
            checkbox = row.locator('.el-checkbox').first
            await checkbox.click()
            await page.wait_for_timeout(3000)
            captured.append("[action] Clicked 范围内与外部 parent checkbox")
        except Exception as e:
            captured.append(f"[action.error] Click 范围内与外部 parent failed: {e}")

        await page.wait_for_timeout(3000)

        # Take final screenshot
        await page.screenshot(path='d:/filework/excel-to-diagram/debug_page.png', full_page=True)
        captured.append("--- FINAL SCREENSHOT saved ---")

        await browser.close()

    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        f.write('=== CONSOLE LOGS (filtered: DEBUG-RSS / RSS / pageerror) ===\n')
        for line in captured:
            f.write(line + '\n')
        f.write('\n=== API CALLS (relationships/business_object) ===\n')
        for line in api_calls:
            f.write(line + '\n')
        f.write('\n=== NETWORK FAILURES ===\n')
        for line in network_failures:
            f.write(line + '\n')

    print(f"Captured {len(captured)} console lines, {len(api_calls)} API calls, {len(network_failures)} HTTP errors")

asyncio.run(main())
