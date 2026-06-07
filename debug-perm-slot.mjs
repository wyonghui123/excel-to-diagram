import { chromium } from 'playwright';

const BASE_URL = 'http://localhost:3010';
const APP_URL = 'http://localhost:3004';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  // Capture console logs
  page.on('console', msg => {
    const text = msg.text();
    if (text.includes('objectType') || text.includes('Permission') || text.includes('slot') || text.includes('permission')) {
      console.log(`[Console ${msg.type()}] ${text.substring(0, 200)}`);
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
    
    // Evaluate Vue app state
    const vueState = await page.evaluate(() => {
      // Try to access Vue app state
      const app = document.querySelector('#app');
      const vueApp = app?.__vue_app__;
      
      return {
        hasVueApp: !!vueApp,
        url: window.location.href,
        routeParams: window.__VUE_ROUTER__?.resolve?.()?.params
      };
    });
    console.log('\nVue state:', JSON.stringify(vueState));
    
    // Check for permission panel in DOM
    const permPanelHtml = await page.evaluate(() => {
      const panels = document.querySelectorAll('.permission-config-panel, .perm-section, .dimension-scope-panel');
      return Array.from(panels).map(p => ({
        class: p.className,
        visible: p.offsetParent !== null,
        html: p.outerHTML.substring(0, 200)
      }));
    });
    console.log('\nPermission panels in DOM:', JSON.stringify(permPanelHtml, null, 2));
    
    // Check for any custom section content
    const customSections = await page.evaluate(() => {
      const sections = document.querySelectorAll('.op-content > section, .op-section');
      return Array.from(sections).map(s => ({
        class: s.className,
        id: s.id,
        visible: s.offsetParent !== null
      }));
    });
    console.log('\nSections in DOM:', JSON.stringify(customSections, null, 2));
    
    await page.screenshot({ path: 'perm-slot-debug.png', fullPage: true });
    console.log('\nScreenshot saved');
    
    console.log('\n✅ Done');
    
  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await browser.close();
  }
}

main();
