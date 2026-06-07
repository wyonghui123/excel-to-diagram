import { chromium } from 'playwright';

const BASE_URL = 'http://localhost:3010';
const APP_URL = 'http://localhost:3004';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  // Capture all API requests
  const apiRequests = [];
  page.on('response', async response => {
    const url = response.url();
    if (url.includes('/api/')) {
      try {
        const body = await response.text();
        const data = JSON.parse(body);
        apiRequests.push({
          url: url.replace('http://localhost:3010', ''),
          status: response.status(),
          success: data.success,
          data: data.data
        });
      } catch (e) {
        apiRequests.push({
          url: url.replace('http://localhost:3010', ''),
          status: response.status(),
          error: 'Failed to parse'
        });
      }
    }
  });
  
  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.log(`[Console Error] ${msg.text().substring(0, 200)}`);
    }
  });
  
  try {
    // 1. Dev login
    console.log('1. Dev login...');
    await page.request.get(`${BASE_URL}/api/v1/auth/dev-login?username=admin`);
    console.log('   ✓ Done');
    
    // 2. Navigate to role detail page
    console.log('2. Navigate to /detail/role/1...');
    await page.goto(`${APP_URL}/detail/role/1`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000);
    console.log(`   URL: ${page.url()}`);
    
    // 3. Check page content
    console.log('\n3. Page content analysis:');
    const bodyText = await page.locator('body').textContent();
    
    // Check for tabs
    const tabs = page.locator('.el-tabs__item');
    const tabCount = await tabs.count();
    console.log(`   Tabs found: ${tabCount}`);
    for (let i = 0; i < tabCount; i++) {
      const text = await tabs.nth(i).textContent();
      console.log(`     - "${text?.trim()}"`);
    }
    
    // 4. Check for permission-related content
    console.log('\n4. Looking for permission content:');
    
    const hasPermTab = tabs.filter({ hasText: '权限' }).count();
    console.log(`   Permission tab count: ${hasPermTab}`);
    
    // 5. Click permission tab if exists
    if (hasPermTab > 0) {
      console.log('\n5. Clicking permission tab...');
      const permTab = page.locator('.el-tabs__item:has-text("权限")');
      await permTab.click();
      await page.waitForTimeout(3000);
      
      // Check for loading
      const loading = page.locator('.el-loading-mask');
      if (await loading.isVisible()) {
        console.log('   Loading...');
        await page.waitForTimeout(3000);
      }
      
      // Check for empty state
      console.log('\n6. Checking empty state:');
      const emptyState = page.locator('.el-empty');
      if (await emptyState.isVisible()) {
        const emptyDesc = await emptyState.locator('.el-empty__description').textContent().catch(() => 'N/A');
        console.log(`   Empty state: "${emptyDesc}"`);
      }
      
      // Check for dimension panel
      console.log('\n7. Checking dimension panel:');
      const dimPanel = page.locator('text=/管理维度|维度范围/');
      const dimCount = await dimPanel.count();
      console.log(`   Dimension elements: ${dimCount}`);
      
      // Check for menu permission matrix
      console.log('\n8. Checking menu permission:');
      const menuSection = page.locator('text=/菜单与功能/');
      const menuCount = await menuSection.count();
      console.log(`   Menu section elements: ${menuCount}`);
      
      // Check for any section with content
      const permSections = page.locator('.perm-section, .dimension-scope-panel, .menu-permission-matrix');
      const sectionCount = await permSections.count();
      console.log(`   Permission sections found: ${sectionCount}`);
    }
    
    // Take screenshot
    await page.screenshot({ path: 'perm-detail-debug.png', fullPage: true });
    console.log('\n   Screenshot saved: perm-detail-debug.png');
    
    // Print ALL API requests related to permissions/dimensions
    console.log('\n📋 API requests related to permissions:');
    const permRequests = apiRequests.filter(r => 
      r.url.includes('permission') || 
      r.url.includes('dimension') ||
      r.url.includes('unified') ||
      r.url.includes('menu')
    );
    if (permRequests.length > 0) {
      permRequests.forEach(req => {
        console.log(`\n  ${req.status} ${req.url}`);
        if (req.success === false) {
          console.log(`    Error: ${JSON.stringify(req.data)}`);
        } else if (req.data) {
          if (req.data.dimensions) {
            console.log(`    Dimensions: ${req.data.dimensions.length}`);
          }
          if (req.data.menus) {
            console.log(`    Menus: ${req.data.menus.length}`);
          }
          if (req.data.items) {
            console.log(`    Items: ${req.data.items.length}`);
          }
        }
      });
    } else {
      console.log('   No permission-related API requests found!');
    }
    
    // Print failed requests
    const failedRequests = apiRequests.filter(r => r.status >= 400 || r.success === false);
    if (failedRequests.length > 0) {
      console.log('\n⚠️ Failed requests:');
      failedRequests.forEach(req => {
        console.log(`  ${req.status} ${req.url}`);
        if (req.data?.message) {
          console.log(`    Message: ${req.data.message}`);
        }
      });
    }
    
    console.log('\n✅ Done');
    
  } catch (error) {
    console.error('\n❌ Error:', error.message);
    await page.screenshot({ path: 'error.png', fullPage: true });
  } finally {
    await browser.close();
  }
}

main();
