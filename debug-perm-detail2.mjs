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
    
    console.log('Page title:', await page.title());
    
    // Get all visible text
    const bodyText = await page.locator('body').textContent();
    console.log('\nVisible text (first 3000 chars):');
    console.log(bodyText.substring(0, 3000));
    
    // Check for any tab-like elements
    console.log('\n\nLooking for tabs:');
    const tabSelectors = [
      '.el-tabs__item',
      '[role="tab"]',
      '.sub-nav-tab',
      '.op-tab',
      'button[class*="tab"]',
      '.tabs button'
    ];
    
    for (const selector of tabSelectors) {
      const elements = page.locator(selector);
      const count = await elements.count();
      if (count > 0) {
        console.log(`  ${selector}: ${count} found`);
        for (let i = 0; i < Math.min(count, 5); i++) {
          const text = await elements.nth(i).textContent();
          console.log(`    - "${text?.trim()}"`);
        }
      }
    }
    
    // Check for any section with text "权限"
    console.log('\n\nLooking for "权限" text:');
    const permElements = page.locator('text=权限');
    const permCount = await permElements.count();
    console.log(`  Found ${permCount} elements with "权限"`);
    for (let i = 0; i < Math.min(permCount, 10); i++) {
      const el = permElements.nth(i);
      const visible = await el.isVisible();
      const text = await el.textContent();
      console.log(`    [${i}] visible=${visible}: "${text?.trim()}"`);
    }
    
    // Check for permission config panel
    console.log('\n\nLooking for permission config elements:');
    const permPanel = page.locator('.permission-config-panel, .perm-section, .dimension-scope-panel, .menu-permission-matrix');
    const panelCount = await permPanel.count();
    console.log(`  Found ${panelCount} permission panel elements`);
    
    await page.screenshot({ path: 'perm-detail-debug2.png', fullPage: true });
    console.log('\nScreenshot saved');
    
    console.log('\n✅ Done');
    
  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await browser.close();
  }
}

main();
