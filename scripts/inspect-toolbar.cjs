// Inspect toolbar to find product/version selectors
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  const log = (k, v) => console.log(`[${k}] ${typeof v === 'string' ? v : JSON.stringify(v).substring(0, 1000)}`);

  try {
    await page.request.get('http://localhost:3010/api/v1/auth/dev-login?username=admin');
    await page.goto('http://localhost:3004/system/archdata', { waitUntil: 'load' });
    await page.waitForTimeout(3000);

    // Dump the full body HTML (first 5000 chars)
    const html = await page.content();
    log('html.length', html.length);

    // Look for the toolbar area - search for elements with "产品" or "版本"
    const toolbarInfo = await page.evaluate(() => {
      const result = { selects: [], inputs: [], allText: '', bodyHTML: '' };
      // Find all el-select
      document.querySelectorAll('.el-select').forEach((el, i) => {
        const rect = el.getBoundingClientRect();
        result.selects.push({
          idx: i,
          text: el.innerText.substring(0, 50),
          placeholder: el.querySelector('input')?.placeholder || '',
          id: el.id || '',
          className: el.className.substring(0, 80),
          visible: rect.width > 0 && rect.height > 0
        });
      });
      // Find all inputs
      document.querySelectorAll('input').forEach((el, i) => {
        result.inputs.push({
          idx: i,
          placeholder: el.placeholder || '',
          name: el.name || '',
          id: el.id || '',
          value: el.value || '',
          type: el.type || ''
        });
      });
      // Get all text content
      result.allText = document.body.innerText.substring(0, 1000);
      return result;
    });
    log('selects', JSON.stringify(toolbarInfo.selects, null, 2));
    log('inputs', JSON.stringify(toolbarInfo.inputs, null, 2));
    log('allText', toolbarInfo.allText);

  } catch (e) {
    log('ERROR', e.message);
  } finally {
    await browser.close();
  }
})();
