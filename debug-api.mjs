import { chromium } from 'playwright';

const BASE_URL = 'http://localhost:3010';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();
  
  try {
    // 登录
    await page.request.get(`${BASE_URL}/api/v1/auth/dev-login?username=admin`);
    
    // 测试 product instances API
    console.log('Testing product instances API...');
    const resp = await page.request.get(`${BASE_URL}/api/v1/management-dimensions/product/instances?page=1&page_size=20`);
    const data = await resp.json();
    console.log('API response:', JSON.stringify(data, null, 2));
    
  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await browser.close();
  }
}

main();
