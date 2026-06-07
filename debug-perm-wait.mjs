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
    
    // Wait for Vue to fully render
    await page.waitForTimeout(8000);
    
    // Click permission tab
    const permTab = page.locator('button:has-text("权限配置")');
    await permTab.click();
    
    // Wait for permission content to load
    await page.waitForTimeout(5000);
    
    console.log('Page loaded and tab clicked');
    
    // Get page text
    const bodyText = await page.locator('body').textContent();
    console.log('\nPage text (first 2000 chars):');
    console.log(bodyText?.substring(0, 2000));
    
    // Try to find elements
    const panelCount = await page.locator('.permission-config-panel').count();
    console.log(`\nPermission config panels: ${panelCount}`);
    
    const menuCount = await page.locator('.menu-permission-matrix').count();
    console.log(`Menu permission matrix: ${menuCount}`);
    
    const dimCount = await page.locator('.dimension-scope-panel').count();
    console.log(`Dimension panels: ${dimCount}`);
    
    // Try to find by text content
    const manageDimText = await page.locator('text=管理维度').count();
    console.log(`Text "管理维度": ${manageDimText}`);
    
    const menuTextText = await page.locator('text=菜单与功能').count();
    console.log(`Text "菜单与功能": ${menuTextText}`);
    
    await page.screenshot({ path: 'perm-wait.png', fullPage: false });
    console.log('\nScreenshot saved');
    
    console.log('\n✅ Done');
    
  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await browser.close();
  }
}

main();
