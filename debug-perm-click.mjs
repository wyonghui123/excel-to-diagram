import { chromium } from 'playwright';

const BASE_URL = 'http://localhost:3010';
const APP_URL = 'http://localhost:3004';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  // Capture console logs
  page.on('console', msg => {
    console.log(`[Console ${msg.type()}] ${msg.text().substring(0, 300)}`);
  });
  
  try {
    await page.request.get(`${BASE_URL}/api/v1/auth/dev-login?username=admin`);
    await page.goto(`${APP_URL}/detail/role/1`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(5000);
    
    console.log('Page loaded');
    
    // Click the permission tab
    console.log('\nClicking permission tab...');
    const permTab = page.locator('button:has-text("权限配置")');
    await permTab.click();
    await page.waitForTimeout(3000);
    
    // Check what's visible now
    console.log('\nChecking content after clicking permission tab:');
    
    // Check for permission config panel
    const permPanel = page.locator('.permission-config-panel, .perm-section, .dimension-scope-panel');
    const panelCount = await permPanel.count();
    console.log(`  Permission panels: ${panelCount}`);
    
    // Check for empty state
    const emptyState = page.locator('.el-empty');
    const emptyCount = await emptyState.count();
    console.log(`  Empty states: ${emptyCount}`);
    
    // Check for loading
    const loading = page.locator('.el-loading-mask');
    const loadingCount = await loading.count();
    console.log(`  Loading states: ${loadingCount}`);
    
    // Get visible text
    const bodyText = await page.locator('body').textContent();
    console.log('\n  Visible text (first 1500 chars):');
    console.log(bodyText.substring(0, 1500));
    
    await page.screenshot({ path: 'after-perm-click.png', fullPage: true });
    console.log('\nScreenshot saved');
    
    console.log('\n✅ Done');
    
  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await browser.close();
  }
}

main();
