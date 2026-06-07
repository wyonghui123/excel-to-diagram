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
    await page.waitForTimeout(5000);
    
    // Click permission tab
    const permTab = page.locator('button:has-text("权限配置")');
    await permTab.click();
    await page.waitForTimeout(3000);
    
    console.log('Page loaded');
    
    // Find all permission-config-panel elements
    const panels = page.locator('.permission-config-panel');
    const panelCount = await panels.count();
    console.log(`Permission config panels: ${panelCount}`);
    
    // Get first panel text
    if (panelCount > 0) {
      const panelText = await panels.first().textContent();
      console.log(`\nPanel text (first 500 chars):`);
      console.log(panelText?.substring(0, 500));
      
      // Check if visible
      const isVisible = await panels.first().isVisible();
      console.log(`\nPanel visible: ${isVisible}`);
    }
    
    // Check for menu permission
    const menuSection = page.locator('.menu-permission-matrix, .perm-section');
    const menuCount = await menuSection.count();
    console.log(`\nMenu permission sections: ${menuCount}`);
    
    if (menuCount > 0) {
      const menuText = await menuSection.first().textContent();
      console.log(`Menu text (first 300 chars):`);
      console.log(menuText?.substring(0, 300));
    }
    
    // Check for dimension panel
    const dimPanel = page.locator('.dimension-scope-panel, .management-dimension');
    const dimCount = await dimPanel.count();
    console.log(`\nDimension panels: ${dimCount}`);
    
    await page.screenshot({ path: 'perm-final.png', fullPage: false });
    console.log('\nScreenshot saved');
    
    console.log('\n✅ Done');
    
  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await browser.close();
  }
}

main();
