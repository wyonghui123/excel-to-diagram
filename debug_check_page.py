"""
Quick check: load the page and see what's actually displayed.
"""
import asyncio
from playwright.async_api import async_playwright

JS_NAV = '''() => {
  const app = document.querySelector('#app');
  if (app && app.__vue_app__) {
    const router = app.__vue_app__.config.globalProperties.$router;
    router.push('/system/archdata?productId=1&versionId=1&tab=business_object');
    return 'navigated';
  }
  return 'no app';
}'''

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = await context.new_page()

        # Login first
        await page.goto('http://localhost:3010/api/v1/auth/dev-login?username=admin')
        await page.wait_for_timeout(2000)

        # Navigate to SPA
        await page.goto('http://localhost:3004/')
        await page.wait_for_timeout(3000)

        # Use SPA internal navigation
        result = await page.evaluate(JS_NAV)
        print('JS nav result:', result)
        await page.wait_for_timeout(5000)
        print('URL after archdata:', page.url)

        # Take a screenshot
        await page.screenshot(path='d:/filework/excel-to-diagram/debug_archdata.png', full_page=True)

        # Get body text
        body_text = await page.locator('body').inner_text(timeout=5000)
        print('Body text length:', len(body_text))
        print('Body (first 2000 chars):')
        print(body_text[:2000])

        await browser.close()

asyncio.run(main())
