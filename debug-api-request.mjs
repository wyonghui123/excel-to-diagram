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
        apiRequests.push({
          url: url.replace('http://localhost:3010', ''),
          status: response.status(),
          body: body.substring(0, 300)
        });
      } catch {}
    }
  });
  
  try {
    await page.request.get(`${BASE_URL}/api/v1/auth/dev-login?username=admin`);
    await page.goto(`${APP_URL}/detail/role/1`, { waitUntil: 'networkidle' });
    
    // Wait for page to load
    await page.waitForTimeout(5000);
    
    console.log('Page loaded');
    console.log(`API requests so far: ${apiRequests.length}`);
    
    // Click permission tab
    const permTab = page.locator('button:has-text("权限配置")');
    await permTab.click();
    
    // Wait for API requests
    await page.waitForTimeout(5000);
    
    console.log(`API requests after click: ${apiRequests.length}`);
    
    // Print all permission-related requests
    const permRequests = apiRequests.filter(r => 
      r.url.includes('permission') || 
      r.url.includes('dimension') ||
      r.url.includes('unified') ||
      r.url.includes('menu')
    );
    
    console.log('\nPermission-related API requests:');
    permRequests.forEach(r => {
      console.log(`  ${r.status} ${r.url}`);
    });
    
    // Print all requests
    console.log('\nAll API requests:');
    apiRequests.forEach(r => {
      console.log(`  ${r.status} ${r.url}`);
    });
    
    console.log('\n✅ Done');
    
  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await browser.close();
  }
}

main();
