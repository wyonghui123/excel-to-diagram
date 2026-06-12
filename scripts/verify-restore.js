// Frontend verification: arch manager -> chart app -> back, state restoration
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  const trace = [];
  const log = (k, v) => { trace.push(`${k}=${v}`); console.log(`[${k}] ${v}`); };

  page.on('pageerror', e => log('PAGEERR', e.message));
  page.on('console', msg => {
    if (msg.type() === 'error' || msg.type() === 'warning') {
      log(`CONSOLE.${msg.type()}`, msg.text().substring(0, 200));
    }
  });

  try {
    // 1. dev-login (sets auth cookie)
    log('1.dev-login.start', '');
    const loginResp = await page.request.get('http://localhost:3010/api/v1/auth/dev-login?username=admin');
    log('1.dev-login.status', loginResp.status());
    const cookies = await ctx.cookies('http://localhost:3004');
    log('1.cookies', cookies.map(c => c.name).join(','));

    // 2. Navigate to arch manager
    log('2.nav.archdata', '');
    await page.goto('http://localhost:3004/system/archdata', { waitUntil: 'load' });
    log('2.url', page.url());
    log('2.title', await page.title());

    // Wait for the momp container to be visible (the inner content)
    log('2.wait.momp', '');
    try {
      await page.waitForSelector('.momp-container, [class*="momp"], .el-table, .el-tabs', { timeout: 15000 });
      log('2.momp.found', 'yes');
    } catch (e) {
      log('2.momp.found', 'no - ' + e.message.substring(0, 100));
    }

    // Dump the visible text
    const archText = await page.locator('body').innerText().catch(() => '');
    log('2.arch.text.length', archText.length);
    log('2.arch.text.snippet', archText.substring(0, 500).replace(/\n/g, ' | '));

    // Dump sessionStorage state
    const ssBefore = await page.evaluate(() => {
      const out = {};
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        out[k] = sessionStorage.getItem(k);
      }
      return out;
    });
    log('2.sessionStorage', JSON.stringify(ssBefore).substring(0, 300));

    // 3. Find the "show chart" button in the GlobalToolbar
    log('3.find.chart.button', '');
    const chartButton = page.locator('button:has-text("展示图表"), button:has-text("图表"), [title*="图表"]').first();
    const chartButtonCount = await chartButton.count();
    log('3.chart.button.count', chartButtonCount);
    if (chartButtonCount === 0) {
      // Try to dump all buttons
      const allButtons = await page.locator('button').allTextContents();
      log('3.all.buttons', allButtons.join(' | '));
    }

    // 4. Click "show chart"
    if (chartButtonCount > 0) {
      log('4.click.chart', '');
      await chartButton.click();
      await page.waitForTimeout(2000);
      log('4.url', page.url());
      log('4.title', await page.title());
      log('4.text.snippet', (await page.locator('body').innerText()).substring(0, 500).replace(/\n/g, ' | '));

      // Check sessionStorage for the save
      const ssAfter = await page.evaluate(() => {
        const out = {};
        for (let i = 0; i < sessionStorage.length; i++) {
          const k = sessionStorage.key(i);
          out[k] = sessionStorage.getItem(k);
        }
        return out;
      });
      log('4.sessionStorage', JSON.stringify(ssAfter).substring(0, 500));
    }

    // 5. Now click the back button in chart app
    log('5.find.back.button', '');
    const backButton = page.locator('button:has-text("上一步"), button:has-text("返回"), button:has-text("上一步")').first();
    const backCount = await backButton.count();
    log('5.back.count', backCount);
    const allChartButtons = await page.locator('button').allTextContents();
    log('5.all.buttons', allChartButtons.join(' | ').substring(0, 500));

    if (backCount > 0) {
      log('5.click.back', '');
      // Find the back button in the stepper footer (usually the first/leftmost)
      // The chart app's step footer has "上一步" and "下一步" buttons
      await backButton.click();
      await page.waitForTimeout(3000);
      log('5.url', page.url());
      log('5.title', await page.title());
      log('5.text.snippet', (await page.locator('body').innerText()).substring(0, 500).replace(/\n/g, ' | '));

      // Check sessionStorage
      const ssBack = await page.evaluate(() => {
        const out = {};
        for (let i = 0; i < sessionStorage.length; i++) {
          const k = sessionStorage.key(i);
          out[k] = sessionStorage.getItem(k);
        }
        return out;
      });
      log('5.sessionStorage', JSON.stringify(ssBack).substring(0, 500));
    }

  } catch (e) {
    log('ERROR', e.message.substring(0, 500));
    log('STACK', e.stack ? e.stack.substring(0, 500) : 'none');
  } finally {
    log('TRACE', trace.join('\n'));
    await browser.close();
  }
})();
