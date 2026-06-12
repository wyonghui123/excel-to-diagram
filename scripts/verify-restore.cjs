// Frontend verification: arch manager -> chart app -> back, state restoration
// 详细诊断: 验证"对象范围"和"关系范围"是否在返回后恢复
const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  const log = (k, v) => console.log(`[${k}] ${typeof v === 'string' ? v : JSON.stringify(v).substring(0, 1500)}`);

  page.on('pageerror', e => log('PAGEERR', e.message));
  page.on('console', msg => {
    const t = msg.text();
    if (msg.type() === 'error') log('CONSOLE.error', t.substring(0, 300));
    if (t.includes('RelationScopeSection')) log('CONSOLE.RSS', t.substring(0, 500));
    if (t.includes('ObjectScopeSection')) log('CONSOLE.OSS', t.substring(0, 400));
    if (t.includes('[MOP]')) log('CONSOLE.MOP', t.substring(0, 800));
    if (t.includes('useMultiObjectPage')) log('CONSOLE.MOP', t.substring(0, 800));
    if (t.includes('[RST]')) log('CONSOLE.RST', t.substring(0, 800));
    if (t.includes('useDiagramData')) log('CONSOLE.DD', t.substring(0, 500));
    if (t.includes('normalizedFilter')) log('CONSOLE.DD', t.substring(0, 500));
    if (t.includes('[DIAG]')) log('CONSOLE.DD', t.substring(0, 500));
  });

  // 注入诊断脚本
  const diagnosticScript = () => {
    window.__diag = function() {
      const out = {};

      // 1. MOM page state
      const momEl = document.querySelector('.multi-object-management');
      if (momEl) {
        const inst = momEl.__vueParentComponent;
        if (inst && inst.setupState) {
          const page = inst.setupState.page;
          if (page) {
            out.page = {
              activeTab: page.activeTab,
              hasScopeSelection: page.hasScopeSelection,
              scopeIds: JSON.parse(JSON.stringify(page.scopeIds || {})),
              combinedFilters: JSON.parse(JSON.stringify(page.combinedFilters || {}))
            };
          }
        }
      }

      // 2. Find all el-tree (OSS + RSS)
      const treeEls = document.querySelectorAll('.momp-sidebar .el-tree');
      out.trees = [];
      treeEls.forEach((treeEl, idx) => {
        const inst = treeEl.__vueParentComponent;
        const tree = { idx };
        if (inst) {
          try {
            const treeRef = inst.setupState?.relationTreeRef
              || inst.setupState?.objectTreeRef
              || inst.refs?.relationTreeRef
              || inst.refs?.objectTreeRef;
            // 尝试通过 el-tree 的 ref 方法获取 checked keys
            if (typeof inst.setupState?.getCheckedKeys === 'function') {
              tree.checkedKeys = inst.setupState.getCheckedKeys();
            } else if (inst.proxy?.getCheckedKeys) {
              tree.checkedKeys = inst.proxy.getCheckedKeys();
            } else if (treeRef?.getCheckedKeys) {
              tree.checkedKeys = treeRef.getCheckedKeys();
            } else {
              // fallback: 从 DOM 读取
              const checkedEls = treeEl.querySelectorAll('.el-tree-node.is-checked');
              tree.checkedCount = checkedEls.length;
            }
          } catch (e) {
            tree.err = e.message;
          }
        }
        out.trees.push(tree);
      });

      // 3. RSS 子组件状态
      const rssEl = document.querySelector('.rss-root');
      if (rssEl) {
        const rssInst = rssEl.__vueParentComponent;
        if (rssInst) {
          try {
            // 通过 _test 钩子
            const testHook = rssInst.setupState?._test;
            if (testHook) {
              out.rssTest = {
                hasData: testHook.hasData,
                treeNodeCount: testHook.treeData?.length || 0,
                relationCount: testHook.relationCount,
                loading: testHook.loading,
                error: testHook.error,
                filterParams: testHook.filterParams,
                selectedCodes: testHook.selectedCodes
              };
            }
          } catch (e) {
            out.rssErr = e.message;
          }
        }
      }

      // 4. sessionStorage
      out.ss = {};
      for (let i = 0; i < sessionStorage.length; i++) {
        const k = sessionStorage.key(i);
        const v = sessionStorage.getItem(k);
        out.ss[k] = v.length > 200 ? v.substring(0, 200) + '...' : v;
      }

      return out;
    };

    // [TEST] 等 RSS 树加载完后, 通过 RSS 内部的 setCheckedKeys 设置 relation codes
    window.__setRelationCodes = async function(codes, opts = {}) {
      const momEl = document.querySelector('.multi-object-management');
      if (!momEl) return { error: 'no momEl' };
      const momInst = momEl.__vueParentComponent;
      if (!momInst) return { error: 'no momInst' };
      const page = momInst.setupState?.page;
      if (!page) return { error: 'no page' };

      // 1. 找到 RSS 组件
      const rssEl = document.querySelector('.rss-root');
      if (!rssEl) return { error: 'no rss (面板未展开)' };
      const rssInst = rssEl.__vueParentComponent;
      if (!rssInst) return { error: 'no rssInst' };

      // 2. 等待树加载 (轮询 - 找树节点出现)
      const maxWait = opts.maxWait || 20000;
      const start = Date.now();
      let lastDiag = null;
      let hasTreeNode = false;
      while (Date.now() - start < maxWait) {
        // 通过 DOM 找 RSS 树是否有可见节点
        const rssTreeNodes = document.querySelectorAll('.rss-root .el-tree-node');
        if (rssTreeNodes.length > 0) {
          hasTreeNode = true;
          lastDiag = { domNodeCount: rssTreeNodes.length, ts: Date.now() - start };
          break;
        }
        lastDiag = { domNodeCount: rssTreeNodes.length, ts: Date.now() - start };
        await new Promise(r => setTimeout(r, 200));
      }

      if (!hasTreeNode) {
        return { error: 'tree not loaded', lastDiag };
      }

      // 3. 通过 UI 点击第一个可见的叶子节点 checkbox
      const checkboxes = document.querySelectorAll('.rss-root .el-tree-node__content .el-checkbox');
      let clicked = 0;
      for (const cb of checkboxes) {
        // 只点未勾选的
        if (cb.classList.contains('is-checked')) continue;
        try {
          cb.click();
          clicked++;
          if (clicked >= 1) break;  // 只点 1 个模拟用户
        } catch (e) {
          // ignore
        }
      }

      // 4. 等待一帧让 watcher 触发
      await new Promise(r => setTimeout(r, 800));

      // 5. 验证 RSS 内部 preservedCheckedKeys 状态
      const rssTree = document.querySelector('.rss-root .el-tree');
      const treeInst = rssTree?.__vueParentComponent;
      const checkedEls = rssTree?.querySelectorAll('.el-tree-node.is-checked') || [];
      const page_ = momInst.setupState?.page;
      const rsc = page_?.scopeIds?.relationExtra?.relationCodes || [];

      return {
        ok: true,
        domNodeCount: document.querySelectorAll('.rss-root .el-tree-node').length,
        clickedCheckboxes: clicked,
        rssCheckedNodeCount: checkedEls.length,
        scopeRelationCodes: rsc,
        lastDiag
      };
    };
  };
  await page.addInitScript(diagnosticScript);

  try {
    await page.request.get('http://localhost:3010/api/v1/auth/dev-login?username=admin');
    await page.goto('http://localhost:3004/system/archdata', { waitUntil: 'load' });
    await page.waitForTimeout(2000);

    // 选择产品 (优先供应链管理系统: v=1 有 28 个关系, TEST60: 业务对象多)
    log('S1.click.product', '');
    await page.locator('.el-select').nth(0).click();
    await page.waitForTimeout(1500);
    const productItems = await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').allTextContents();
    log('S1.product.items', productItems.slice(0, 10).join(' | '));
    // 优先供应链管理系统 (有 v=1 关系数据)
    let prodIdx = productItems.findIndex(t => /供应链/.test(t));
    if (prodIdx < 0) prodIdx = productItems.findIndex(t => /^TEST15$/.test(t.trim()));
    if (prodIdx < 0) prodIdx = productItems.findIndex(t => /^TEST60$/.test(t.trim()));
    if (prodIdx < 0) prodIdx = productItems.findIndex(t => /^TEST14$/.test(t.trim()));
    if (prodIdx < 0) prodIdx = productItems.findIndex(t => t.trim() && !t.includes('createdby'));
    if (prodIdx < 0) prodIdx = 0;
    log('S1.productIdx', prodIdx);
    if (productItems.length > 0) {
      await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').nth(prodIdx).click();
      await page.waitForTimeout(2000);
    }

    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    log('S2.click.version', '');
    await page.locator('.el-select').nth(1).click({ force: true });
    await page.waitForTimeout(1500);
    const versionItems = await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').allTextContents();
    log('S2.version.items', versionItems.slice(0, 5).join(' | '));
    if (versionItems.length > 0) {
      // 优先选名字含"新测试2"的版本 (v=1 关系数据丰富)
      let vIdx = versionItems.findIndex(t => /新测试2/.test(t));
      if (vIdx < 0) vIdx = 0;
      log('S2.versionIdx', vIdx);
      await page.locator('.el-select-dropdown:visible .el-select-dropdown__item').nth(vIdx).click({ force: true });
      await page.waitForTimeout(3000);
    }

    await page.waitForTimeout(3000);

    // 勾选 OSS 树第一个节点
    log('S3.clickCb', '');
    const firstCb = page.locator('.momp-sidebar .el-tree .el-tree-node').first().locator('.el-checkbox').first();
    await firstCb.click({ force: true });
    await page.waitForTimeout(2000);

    // 展开"关系范围"面板
    log('S3b.expandRelation', '');
    const relationPanelToggle = page.locator('.rst-panel-relation .collapsible-panel__header, .rst-panel-relation .panel-header').first();
    if (await relationPanelToggle.count() > 0) {
      await relationPanelToggle.click({ force: true });
      await page.waitForTimeout(2000);
    }

    // 通过 __setRelationCodes 设置关系 codes (等待树加载)
    log('S3b.setRel', '');
    const setRes = await page.evaluate(async () => {
      return await window.__setRelationCodes(['BELONGS_TO']);
    });
    log('S3b.setRes', JSON.stringify(setRes));

    // 跳转到图表前快照
    const diag1 = await page.evaluate(() => window.__diag());
    log('DIAG.before_chart', JSON.stringify(diag1).substring(0, 3000));

    // 点击"展示图表"按钮
    const chartBtn = page.locator('.gt-actions button').nth(2);
    const isDisabled = await chartBtn.evaluate(el => el.disabled || el.classList.contains('is-disabled'));
    log('S5.chartBtnDisabled', isDisabled);

    if (!isDisabled) {
      log('S5.clickChart', '');
      await chartBtn.click({ force: true });
      await page.waitForTimeout(5000);  // 多等一下确保 chart app 初始化完成
      log('S5.url', page.url());

      // [KEY] 验证 chart app 收到的 archData 过滤参数
      const chartArchData = await page.evaluate(() => {
        try {
          const raw = sessionStorage.getItem('archDataForDiagram') || sessionStorage.getItem('lastArchDataForDiagram');
          if (!raw) return { error: 'no archData in sessionStorage' };
          const data = JSON.parse(raw);
          return {
            versionId: data.versionId,
            hierarchyFilterKeys: Object.keys(data.hierarchyFilter || {}),
            hierarchyFilter: JSON.stringify(data.hierarchyFilter || {}).substring(0, 500),
            selectedDomainIds: data.selectedDomainIds,
            hasSelectedDomainIds: Array.isArray(data.selectedDomainIds) && data.selectedDomainIds.length > 0
          };
        } catch(e) { return { error: e.message }; }
      });
      log('S5.chartArchData', JSON.stringify(chartArchData));

      await page.screenshot({ path: 'scripts/_screenshots/05_chart_app_step3.png', fullPage: true });
      
      // 检查图表应用是否显示过滤后的数据 (不是所有领域)
      const chartPageDiag = await page.evaluate(() => {
        const h3s = document.querySelectorAll('h3');
        const h3Texts = [];
        h3s.forEach(h => h3Texts.push(h.textContent?.substring(0, 100)));
        return { url: location.href, h3s: h3Texts };
      });
      log('S5.chartPage', JSON.stringify(chartPageDiag));

      // 前进到配置步骤 (step 4)
      const nextBtn1 = page.locator('button:has-text("下一步")').first();
      if (await nextBtn1.count() > 0) {
        log('S5b.clickNext_toStep4', '');
        await nextBtn1.click({ force: true });
        await page.waitForTimeout(3000);
        
        // [KEY] 验证配置步骤的领域过滤效果：图表应用应只显示所选领域，而非所有领域
        const configDiag = await page.evaluate(() => {
          // 尝试查找配置步骤中显示的领域信息
          const selects = document.querySelectorAll('.el-select');
          const cascaders = document.querySelectorAll('.el-cascader');
          const labels = document.querySelectorAll('label, .form-label, .el-form-item__label');
          const labelTexts = [];
          labels.forEach(l => {
            const t = l.textContent?.trim();
            if (t && t.length < 50) labelTexts.push(t);
          });
          // 查找中心的业务对象选择器内容
          const centerScopeEl = document.querySelector('[class*="centerScope"]');
          const centerScopeText = centerScopeEl ? centerScopeEl.textContent?.trim() : null;
          return {
            labelCount: labels.length,
            labelTexts: labelTexts.slice(0, 20),
            centerScopeText,
            url: location.href
          };
        });
        log('S5b.configDiag', JSON.stringify(configDiag).substring(0, 1000));

        await page.screenshot({ path: 'scripts/_screenshots/06_chart_app_step4.png', fullPage: true });
        log('S5b.url', page.url());
      }

      // 前进到展示步骤 (step 5)
      const nextBtn2 = page.locator('button:has-text("下一步")').first();
      if (await nextBtn2.count() > 0) {
        log('S5c.clickNext_toStep5', '');
        await nextBtn2.click({ force: true });
        await page.waitForTimeout(2000);
        await page.screenshot({ path: 'scripts/_screenshots/07_chart_app_step5.png', fullPage: true });
        log('S5c.url', page.url());
      }

      // [KEY] 从步骤5展示页点"上一步"返回架构管理（验证任何步骤都可返回）
      const backBtn = page.locator('button:has-text("上一步")').first();
      const backCount = await backBtn.count();
      log('S6.backCount', backCount);
      if (backCount > 0) {
        log('S6.clickBack', '');
        await backBtn.click({ force: true });
        await page.waitForTimeout(1500);
        log('S6.url', page.url());

        // 立即诊断
        const diagImmediate = await page.evaluate(() => window.__diag());
        log('DIAG.immediate', JSON.stringify(diagImmediate).substring(0, 3000));

        // 等待 5s 后再诊断
        await page.waitForTimeout(4000);
        const diag2 = await page.evaluate(() => window.__diag());
        log('DIAG.after_back', JSON.stringify(diag2).substring(0, 3000));
        await page.screenshot({ path: 'scripts/_screenshots/02_after_back.png', fullPage: true });

        // [KEY] 等 RSS 树加载完后, 截图验证关系范围是否自动展开 + 复选框恢复
        log('S7.waitForRelTree', '');
        await page.waitForTimeout(5000);
        const diag3 = await page.evaluate(() => window.__diag());
        log('DIAG.after_rel_tree_loaded', JSON.stringify(diag3).substring(0, 1500));

        // [DBG] 检查关系范围面板的 DOM 状态
        const relPanelState = await page.evaluate(() => {
          const panel = document.querySelector('.rst-panel-relation');
          if (!panel) return { error: 'no .rst-panel-relation' };
          const cp = panel.querySelector('.collapsible-panel');
          const content = panel.querySelector('.collapsible-panel__content');
          const rssRoot = panel.querySelector('.rss-root');
          const tree = panel.querySelector('.el-tree');
          return {
            panelExists: !!panel,
            cpClass: cp ? cp.className : null,
            cpIsCollapsed: cp ? cp.classList.contains('is-collapsed') : null,
            contentDisplay: content ? window.getComputedStyle(content).display : null,
            contentHeight: content ? content.offsetHeight : null,
            rssRootExists: !!rssRoot,
            rssRootDisplay: rssRoot ? window.getComputedStyle(rssRoot).display : null,
            rssRootHeight: rssRoot ? rssRoot.offsetHeight : null,
            treeExists: !!tree,
            treeHeight: tree ? tree.offsetHeight : null
          };
        });
        log('S7.relPanelDOM', JSON.stringify(relPanelState));

        await page.screenshot({ path: 'scripts/_screenshots/03_rel_auto_expanded.png', fullPage: true });

        // 展开后, 找可见的 .rss-tree .is-checked 节点
        const rssTreeChecked = await page.locator('.rss-root .el-tree-node.is-checked').count();
        log('S7.rssTreeCheckedCount', rssTreeChecked);
        // 列出 rss 树所有可见的勾选节点
        const checkedNodes = await page.locator('.rss-root .el-tree-node.is-checked .rss-node-label').allTextContents();
        log('S7.rssCheckedNodeLabels', checkedNodes.slice(0, 10).join(' | '));
        await page.screenshot({ path: 'scripts/_screenshots/04_rel_visible_checked.png', fullPage: true });
      }
    }

  } catch (e) {
    log('ERROR', e.message);
    log('STACK', e.stack?.substring(0, 500));
  } finally {
    await browser.close();
  }
})();
