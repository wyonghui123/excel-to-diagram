import { chromium } from 'playwright';

const BASE_URL = 'http://localhost:3010';
const APP_URL = 'http://localhost:3004';

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();
  
  // 捕获控制台日志
  page.on('console', msg => {
    const text = msg.text();
    if (text.includes('dimension') || text.includes('selected') || text.includes('fetch')) {
      console.log(`[${msg.type()}] ${text.substring(0, 200)}`);
    }
  });
  
  try {
    await page.request.get(`${BASE_URL}/api/v1/auth/dev-login?username=admin`);
    await page.goto(`${APP_URL}/detail/role/1`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(5000);
    
    // 检查 dimension scopes
    const scopesResp = await page.request.get(`${BASE_URL}/api/v1/roles/1/dimension-scopes`);
    const scopes = await scopesResp.json();
    console.log('\n当前 dimension scopes:', JSON.stringify(scopes, null, 2));
    
    // 点击权限配置 tab
    await page.locator('button:has-text("权限配置")').click();
    await page.waitForTimeout(3000);
    console.log('\n已打开权限配置 tab');
    
    // 检查 selectedValues
    const selectedValues = await page.evaluate(() => {
      // 尝试获取 Vue 组件状态
      const app = document.querySelector('#app');
      return {
        hasApp: !!app,
        appChildren: app?.childElementCount
      };
    });
    console.log('App state:', selectedValues);
    
    // 打开对话框
    await page.locator('button:has-text("添加产品")').first().click();
    await page.waitForTimeout(2000);
    console.log('\n已打开对话框');
    
    // 统计产品数量
    const count = await page.locator('.el-dialog .el-table__body tr').count();
    console.log(`产品数量: ${count}`);
    
    // 截图
    await page.screenshot({ path: 'debug-delta.png', fullPage: false });
    console.log('截图已保存');
    
  } catch (error) {
    console.error('错误:', error.message);
  } finally {
    await browser.close();
  }
}

main();
