const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  // Login
  await page.goto('http://localhost:3004/');
  await page.waitForLoadState('load');
  await page.waitForTimeout(500);
  
  const usernameInput = page.locator('input[type="text"], input[name="username"]').first();
  if (await usernameInput.isVisible().catch(() => false)) {
    await usernameInput.fill('admin');
    await page.locator('input[type="password"]').first().fill('admin123');
    await page.locator('button[type="submit"]').first().click();
    await page.waitForTimeout(3000);
  }
  
  // Navigate to user-permission
  await page.goto('http://localhost:3004/user-permission');
  await page.waitForLoadState('load');
  await page.waitForTimeout(5000);
  
  console.log('Current URL:', page.url());
  
  // Check for various elements
  const checks = [
    ['.el-table', 'Table'],
    ['.el-tabs', 'Tabs'],
    ['.el-tabs__item', 'Tab items'],
    ['main', 'Main'],
    ['.page-container', 'Page container'],
    ['.user-management', 'User management'],
    ['[class*="user"]', 'User class'],
    ['.meta-list-page', 'MetaListPage']
  ];
  
  for (const [selector, name] of checks) {
    const count = await page.locator(selector).count();
    const visible = count > 0 ? await page.locator(selector).first().isVisible().catch(() => false) : false;
    console.log(`${name}: count=${count}, visible=${visible}`);
  }
  
  // Get tab contents
  const tabItems = await page.locator('.el-tabs__item').allTextContents();
  console.log('Tab contents:', tabItems);
  
  // Get page text sample
  const bodyText = await page.locator('body').allTextContents();
  const sample = bodyText[0].substring(0, 500);
  console.log('Page text sample:', sample);
  
  await page.screenshot({ path: 'debug-user-permission.png', fullPage: true });
  console.log('Screenshot saved to debug-user-permission.png');
  
  await browser.close();
})();
