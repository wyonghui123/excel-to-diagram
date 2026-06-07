import { chromium } from 'playwright';

const BASE_URL = 'http://localhost:3010';
const APP_URL = 'http://localhost:3004';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  page.on('console', msg => {
    const text = msg.text();
    if (text.includes('objectType') || text.includes('role') || text.includes('section')) {
      console.log(`[${msg.type()}] ${text.substring(0, 200)}`);
    }
  });
  
  try {
    await page.request.get(`${BASE_URL}/api/v1/auth/dev-login?username=admin`);
    await page.goto(`${APP_URL}/detail/role/1`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(5000);
    
    console.log('Page loaded');
    
    // Click permission tab
    const permTab = page.locator('button:has-text("权限配置")');
    await permTab.click();
    await page.waitForTimeout(3000);
    
    // Evaluate Vue state
    const result = await page.evaluate(() => {
      // Try to get Vue component instance
      const app = document.querySelector('#app');
      const vueApp = app?.__vue_app__;
      
      // Try to get component data
      const detailPage = document.querySelector('.object-detail-page');
      const vueInstance = detailPage?.__vue_parentComponent;
      
      return {
        url: window.location.href,
        hasVueApp: !!vueApp,
        routeParams: window.__vueRouter__?.currentRoute?.value?.params
      };
    });
    console.log('\nResult:', JSON.stringify(result, null, 2));
    
    // Get full page HTML for debugging
    const html = await page.content();
    const permPanelIndex = html.indexOf('permission-config-panel');
    const permSectionIndex = html.indexOf('perm-section');
    console.log('\npermission-config-panel found at:', permPanelIndex);
    console.log('perm-section found at:', permSectionIndex);
    
    // Check if slot content is in HTML
    const slotContent = html.match(/<section[^>]*>[\s\S]*?section-permissions[\s\S]*?<\/section>/);
    console.log('Slot content found:', !!slotContent);
    
    await page.screenshot({ path: 'perm-slot-debug2.png', fullPage: true });
    console.log('\nScreenshot saved');
    
    console.log('\n✅ Done');
    
  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await browser.close();
  }
}

main();
