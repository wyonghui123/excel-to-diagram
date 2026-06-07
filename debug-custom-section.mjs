import { chromium } from 'playwright';

const BASE_URL = 'http://localhost:3010';
const APP_URL = 'http://localhost:3004';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  try {
    await page.request.get(`${BASE_URL}/api/v1/auth/dev-login?username=admin`);
    await page.goto(`${APP_URL}/detail/role/1`, { waitUntil: 'networkidle' });
    
    // Wait for Vue to render
    await page.waitForTimeout(8000);
    
    // Click permission tab
    const permTab = page.locator('button:has-text("权限配置")');
    await permTab.click();
    await page.waitForTimeout(3000);
    
    // Get page text
    const bodyText = await page.locator('body').textContent();
    console.log('\nPage text:');
    console.log(bodyText?.substring(0, 3000));
    
    // Check for debug info
    const debugInfo = bodyText?.match(/Custom section.*?Has slot/s);
    console.log('\nDebug info found:', !!debugInfo);
    
    // Check for custom-section-debug
    const debugCount = await page.locator('.custom-section-debug').count();
    console.log('Custom section debug elements:', debugCount);
    
    // Check for section key
    const sectionKeys = await page.locator('[data-section-key]').count();
    console.log('Elements with data-section-key:', sectionKeys);
    
    await page.screenshot({ path: 'custom-section-debug.png', fullPage: false });
    console.log('\nScreenshot saved');
    
    console.log('\n✅ Done');
    
  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await browser.close();
  }
}

main();
