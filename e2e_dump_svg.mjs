// e2e_dump_svg.mjs - 用 playwright 渲染页面, dump svg 结构
import { chromium } from 'playwright';
import fs from 'fs';

const browser = await chromium.launch({ headless: true });
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
const page = await ctx.newPage();

const consoleLogs = [];
page.on('console', msg => consoleLogs.push(`[${msg.type()}] ${msg.text()}`));
page.on('pageerror', err => consoleLogs.push(`[pageerror] ${err.message}`));

// 登录
await page.goto('http://localhost:3004/');
await page.waitForTimeout(500);
await page.goto('http://localhost:3004/');
// 触发 dev-login
const loginResp = await page.evaluate(async () => {
  const r = await fetch('/api/v1/auth/dev-login', { method: 'GET', credentials: 'include' });
  return r.status;
});
console.log('login status:', loginResp);

// 等待页面
await page.waitForTimeout(1000);

// 模拟 initFromArchDataManager
const initResult = await page.evaluate(async () => {
  try {
    // 查找页面里 vue 组件实例
    const r = await fetch('/api/v2/bo/architecture/preview?version_id=1', { credentials: 'include' });
    return { status: r.status, ok: r.ok };
  } catch (e) {
    return { error: e.message };
  }
});
console.log('preview fetch:', initResult);

await browser.close();

fs.writeFileSync('console_logs.txt', consoleLogs.join('\n'));
console.log('--- console logs ---');
console.log(consoleLogs.slice(-30).join('\n'));
