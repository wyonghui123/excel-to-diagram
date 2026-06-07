const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();

    console.log('Logging in...');
    await page.goto('http://localhost:3004');
    await page.fill('input[type="text"], input[name="username"]', 'admin');
    await page.fill('input[type="password"]', 'admin123');
    await page.click('button[type="submit"]');

    try {
        await page.waitForSelector('.login-overlay', { state: 'hidden', timeout: 10000 });
        console.log('Login successful');
    } catch(e) {
        console.log('Login overlay wait failed:', e.message);
    }

    console.log('Navigating to role management...');
    await page.goto('http://localhost:3004/system/role-permission');
    await page.waitForLoadState('domcontentloaded');

    try {
        await page.waitForSelector('.el-table', { timeout: 15000 });
        console.log('Table loaded');
    } catch(e) {
        console.log('Table wait failed:', e.message);
    }

    await page.waitForTimeout(2000);

    const badges = await page.$$eval('.el-tag', tags => tags.map(t => t.textContent.trim()));
    console.log('Badge values:', JSON.stringify(badges));

    const screenshot = await page.screenshot({ fullPage: true });
    const fs = require('fs');
    fs.writeFileSync('test_role_screenshot.png', screenshot);
    console.log('Screenshot saved to test_role_screenshot.png');

    await browser.close();
})();
