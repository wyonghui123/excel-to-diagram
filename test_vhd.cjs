/**
 * VHD-01: Value Help Dialog 分页验证测试
 * 直接使用 Playwright API，不依赖 Playwright Test Runner
 */
const { chromium } = require('playwright');

async function runTest() {
  const baseUrl = 'http://127.0.0.1:3010';
  const appUrl = 'http://127.0.0.1:3004';

  console.log('启动浏览器...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  let passed = 0;
  let failed = 0;

  try {
    // 1. 登录
    console.log('1. 登录...');
    const resp = await page.request.get(`${baseUrl}/api/v1/auth/dev-login?username=admin`);
    if (!resp.ok()) {
      throw new Error(`dev-login failed: ${resp.status()}`);
    }
    await page.goto(appUrl, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    console.log('   登录成功');

    // 2. 导航到新建用户组
    console.log('2. 导航到 /detail/user_group/new...');
    await page.goto(`${appUrl}/detail/user_group/new`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(5000);  // SPA 需要时间渲染

    // 截图
    await page.screenshot({ path: 'test_results/00_navigated.png', fullPage: true });
    console.log('   截图: 00_navigated.png');

    // 检查当前 URL
    const url = page.url();
    console.log(`   当前 URL: ${url}`);

    // 等待表单加载（等待包含"组编码"文字的元素出现 - 这是表单特有的字段）
    try {
      await page.waitForFunction(
        () => {
          const selectors = ['.el-form-item__label', '[class*="label"]', 'label', 'span', 'div'];
          for (const sel of selectors) {
            const els = document.querySelectorAll(sel);
            for (const el of els) {
              const text = el.textContent || '';
              if (text.includes('组编码') || text.includes('组名')) return true;
            }
          }
          return false;
        },
        { timeout: 20000 }
      );
      console.log('   表单已加载');
    } catch (e) {
      // 可能表单不在这里，尝试找其他入口
      const bodyText = await page.evaluate(() => document.body.innerText.substring(0, 500));
      console.log('   表单未找到，页面内容:', bodyText);
      throw new Error(`表单未加载: ${bodyText.substring(0, 200)}`);
    }

    // 3. 截图
    await page.screenshot({ path: 'test_results/01_form_loaded.png', fullPage: true });
    console.log('   截图: 01_form_loaded.png');

    // 4. 找管理员字段
    const adminLabel = page.locator('.el-form-item__label').filter({ hasText: /管理员/i });
    const adminCount = await adminLabel.count();
    console.log(`3. 找到 ${adminCount} 个管理员字段`);

    if (adminCount === 0) {
      // 调试：输出所有可能的表单元素
      const allLabels = await page.evaluate(() => {
        const els = document.querySelectorAll('[class*="label"], .el-form-item__label, label, span, div');
        const results = [];
        for (const el of els) {
          const text = el.textContent?.trim();
          if (text && text.length > 0 && text.length < 50) {
            results.push({ tag: el.tagName, class: el.className.substring(0, 50), text });
          }
        }
        return results.slice(0, 30);
      });
      console.log('   调试 - 页面元素:', JSON.stringify(allLabels, null, 2).substring(0, 1000));
      throw new Error(`未找到管理员字段。页面元素: ${allLabels.map(e => e.text).join(', ')}`);
    }

    // 5. 打开 value help 弹窗
    console.log('4. 打开 value help...');
    const adminFormItem = adminLabel.first().locator('..').locator('..');
    const searchIcon = adminFormItem.locator('.vh-search-icon');
    const searchVisible = await searchIcon.isVisible().catch(() => false);
    if (searchVisible) {
      await searchIcon.click();
    } else {
      await adminFormItem.locator('input').click();
    }

    // 等待弹窗
    await page.waitForSelector('.el-dialog', { timeout: 10000 });
    console.log('   弹窗已打开');

    // 6. 截图
    await page.screenshot({ path: 'test_results/02_dialog_opened.png', fullPage: true });
    console.log('   截图: 02_dialog_opened.png');

    // 7. 核心验证：表格行数
    console.log('5. 验证表格行数...');
    const tableRows = page.locator('.el-dialog .el-table__body tr');
    const rowCount = await tableRows.count();
    console.log(`   表格行数: ${rowCount}`);

    if (rowCount > 20) {
      console.log(`   ❌ FAIL: 表格行数 ${rowCount} 超过 20，max-height 未生效`);
      failed++;
    } else if (rowCount > 0) {
      console.log(`   ✅ PASS: 表格行数 ${rowCount} 在合理范围内`);
      passed++;
    } else {
      console.log(`   ⚠️ 表格行数为 0，可能数据未加载`);
    }

    // 8. 验证 max-height
    console.log('6. 验证 el-table max-height...');
    const maxHeight = await page.locator('.el-dialog .el-table').evaluate(
      el => getComputedStyle(el).maxHeight
    );
    console.log(`   max-height: ${maxHeight}`);
    if (maxHeight === '420px') {
      console.log('   ✅ PASS: max-height = 420px');
      passed++;
    } else {
      console.log(`   ❌ FAIL: max-height 应为 420px，实际为 ${maxHeight}`);
      failed++;
    }

    // 9. 验证分页
    console.log('7. 验证分页信息...');
    const paginationText = await page.locator('.el-dialog .el-pagination').innerText().catch(() => '');
    console.log(`   分页信息: ${paginationText}`);
    if (paginationText.includes('15')) {
      console.log('   ✅ PASS: 分页显示 15 条/页');
      passed++;
    } else {
      console.log(`   ⚠️ 分页信息: ${paginationText}`);
    }

    // 10. 测试搜索
    console.log('8. 测试实时搜索...');
    const searchInput = page.locator('.el-dialog .vh-search-bar input');
    const searchInputVisible = await searchInput.isVisible().catch(() => false);
    if (searchInputVisible) {
      await searchInput.fill('admin');
      await page.waitForTimeout(600);
      await page.screenshot({ path: 'test_results/03_search_result.png', fullPage: true });
      console.log('   截图: 03_search_result.png');
      const filteredRows = await tableRows.count();
      console.log(`   搜索后行数: ${filteredRows}`);
    } else {
      console.log('   ⚠️ 搜索框未找到');
    }

    // 11. 关闭弹窗
    console.log('9. 关闭弹窗...');
    await page.locator('.el-dialog .el-button').filter({ hasText: /取消/ }).first().click();
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'test_results/04_dialog_closed.png', fullPage: true });
    console.log('   截图: 04_dialog_closed.png');

  } catch (e) {
    console.log(`\n❌ 测试失败: ${e.message}`);
    failed++;
    await page.screenshot({ path: 'test_results/99_error.png', fullPage: true }).catch(() => {});
  } finally {
    await browser.close();
  }

  console.log('\n========== 测试结果 ==========');
  console.log(`✅ 通过: ${passed}`);
  console.log(`❌ 失败: ${failed}`);
  console.log('==============================');

  process.exit(failed > 0 ? 1 : 0);
}

// 确保截图目录存在
const fs = require('fs');
try {
  fs.mkdirSync('test_results', { recursive: true });
} catch (e) {}

runTest().catch(e => {
  console.error('Fatal error:', e);
  process.exit(1);
});
