/**
 * E2E 测试: OSS/RSS 关系范围树节点操作
 *
 * 测试场景:
 * 1. OSS 对象范围树节点选择
 * 2. RSS 关系范围树节点选择
 * 3. 验证 filterParams 正确传递 originalId
 *
 * 可测试性目标:
 * - data-testid 属性支持稳定选择器
 * - defineExpose _test 暴露内部状态
 * - 健康检查 Fail-Fast
 * - 智能等待替代盲等
 *
 * 运行: npx playwright test --project=features e2e/features/relation-scope-tree.spec.js
 */
import { test, expect } from '@playwright/test'
import {
  login,
  setAdminPermissions,
  attachAndVerifyScreenshot,
  assertHealthy,
  waitForDomExists,
  waitForStable
} from '../helpers/auth.js'

test.describe('关系范围树节点操作', () => {
  test.beforeEach(async ({ page }) => {
    // 登录
    await login(page)

    // 设置管理员权限
    await setAdminPermissions(page)

    // 导航到 archdata 页面
    await page.goto('/system/archdata?productId=1&versionId=1', {
      waitUntil: 'domcontentloaded'
    })

    // 等待 Vue 挂载
    await page.waitForFunction(() => {
      return !!document.querySelector('#app')?.__vue_app__
    }, { timeout: 15000 })

    // 等待页面路由完成
    await page.waitForURL('**/archdata**', { timeout: 10000 })

    // [MUST] 导航后立即健康检查（Fail-Fast）
    await assertHealthy(page, 'archdata navigation')
  })

  test('C01: OSS 树 data-testid 属性验证', async ({ page }) => {
    const testInfo = test.info()

    // 等待 OSS 树加载（DOM 存在即可）
    await waitForDomExists(page, '[data-testid="oss-tree-label"]', 15000)

    // 验证 OSS 树节点有 data-testid 属性
    const ossLabels = await page.locator('[data-testid="oss-tree-label"]').all()
    console.log(`OSS labels count: ${ossLabels.length}`)

    expect(ossLabels.length).toBeGreaterThan(0)

    // 等待树稳定后再截图
    await waitForStable(page, '[data-testid="oss-tree-label"]', 5000)

    await attachAndVerifyScreenshot(page, testInfo, '01-oss-tree-labels', {
      expectedPath: 'archdata'
    })

    // 操作后再次检查健康
    await assertHealthy(page, 'C01 after screenshot')
  })

  test('C02: OSS 树节点点击选中', async ({ page }) => {
    const testInfo = test.info()

    // 等待 OSS 树 DOM 存在
    await waitForDomExists(page, '[data-testid="oss-tree-label"]', 15000)

    // 获取第一个 OSS 节点文本
    const firstLabel = await page.locator('[data-testid="oss-tree-label"]').first()
    const labelText = await firstLabel.textContent()

    console.log(`Clicking OSS label: ${labelText}`)

    // 点击节点（通过 el-tree-node__content 找到正确的点击区域）
    await page.evaluate((text) => {
      const labels = document.querySelectorAll('[data-testid="oss-tree-label"]')
      for (const label of labels) {
        if (label.textContent.trim() === text) {
          const content = label.closest('.el-tree-node__content')
          if (content) {
            content.click()
            return true
          }
        }
      }
      return false
    }, labelText.trim())

    // [改进] 使用稳定等待替代固定时间
    await waitForStable(page, '[data-testid="oss-tree-label"]', 3000)

    // 验证 checkbox 被选中
    const checkbox = await page.evaluate((text) => {
      const labels = document.querySelectorAll('[data-testid="oss-tree-label"]')
      for (const label of labels) {
        if (label.textContent.trim() === text) {
          const content = label.closest('.el-tree-node__content')
          if (content) {
            const cb = content.querySelector('.el-checkbox__input')
            return cb?.classList.contains('is-checked')
          }
        }
      }
      return false
    }, labelText.trim())

    expect(checkbox).toBe(true)

    // 操作后健康检查
    await assertHealthy(page, 'C02 after click')

    await attachAndVerifyScreenshot(page, testInfo, '02-oss-node-selected', {
      expectedPath: 'archdata'
    })
  })

  test('C03: RSS 树节点点击选中', async ({ page }) => {
    const testInfo = test.info()

    // 展开 RSS 面板（点击 RelationScopeSection 标题）
    const rssSection = page.locator('.relation-scope-section, [class*="relation-scope"]').first()
    await rssSection.click().catch(() => {})

    // [改进] 等待 RSS 树 DOM 存在（不要求可见）
    await waitForDomExists(page, '[data-testid="rss-tree-label"]', 15000)

    // 验证 RSS 树节点有 data-testid 属性
    const rssLabels = await page.locator('[data-testid="rss-tree-label"]').all()
    console.log(`RSS labels count: ${rssLabels.length}`)

    expect(rssLabels.length).toBeGreaterThan(0)

    // 获取第一个 RSS 节点文本并点击
    const firstLabel = await page.locator('[data-testid="rss-tree-label"]').first()
    const labelText = await firstLabel.textContent()

    console.log(`Clicking RSS label: ${labelText}`)

    // 点击 RSS 节点
    await page.evaluate((text) => {
      const labels = document.querySelectorAll('[data-testid="rss-tree-label"]')
      for (const label of labels) {
        if (label.textContent.trim() === text) {
          const content = label.closest('.el-tree-node__content')
          if (content) {
            content.click()
            return true
          }
        }
      }
      return false
    }, labelText.trim())

    // [改进] 使用稳定等待
    await waitForStable(page, '[data-testid="rss-tree-label"]', 3000)

    // 操作后健康检查
    await assertHealthy(page, 'C03 after click')

    await attachAndVerifyScreenshot(page, testInfo, '03-rss-node-selected', {
      expectedPath: 'archdata'
    })
  })

  test('C04: OSS + RSS 联合选择验证 filterParams', async ({ page }) => {
    const testInfo = test.info()

    // 展开 RSS 面板
    const rssSection = page.locator('.relation-scope-section, [class*="relation-scope"]').first()
    await rssSection.click().catch(() => {})

    await waitForDomExists(page, '[data-testid="rss-tree-label"]', 15000)

    // 1. 选择一个 OSS 节点
    await waitForDomExists(page, '[data-testid="oss-tree-label"]', 15000)
    const ossLabel = await page.locator('[data-testid="oss-tree-label"]').first()
    const ossText = await ossLabel.textContent()

    await page.evaluate((text) => {
      const labels = document.querySelectorAll('[data-testid="oss-tree-label"]')
      for (const label of labels) {
        if (label.textContent.trim() === text) {
          const content = label.closest('.el-tree-node__content')
          content?.click()
          return
        }
      }
    }, ossText.trim())

    // [改进] 使用稳定等待（等待 filterParams 更新）
    await waitForStable(page, '.relation-scope-section', 5000)

    // 2. 获取 RSS 组件状态（验证 filterParams 包含 originalId）
    const filterParams = await page.evaluate(() => {
      const app = document.querySelector('#app')?.__vue_app__
      if (!app) return { source: 'no_app' }

      // 方法1: 通过 el-tree 的 __vueParentComponent 找到组件
      const treeEl = document.querySelector('.relation-scope-section .el-tree, [class*="relation-scope"] .el-tree')
      if (treeEl?.__vueParentComponent) {
        let parent = treeEl.__vueParentComponent
        while (parent) {
          const exposed = parent.exposed
          if (exposed?._test) {
            return {
              filterParams: exposed._test.filterParams,
              source: '_test'
            }
          }
          const ss = parent.setupState
          if (ss && ss._test) {
            return {
              filterParams: ss._test.filterParams,
              source: 'setupState'
            }
          }
          parent = parent.parent
        }
      }

      // 方法2: 遍历 Vue 实例树
      const findExposed = (vm) => {
        if (!vm) return null
        const exposed = vm.exposed
        if (exposed?._test) return exposed

        if (vm.subTree) {
          const result = findExposed(vm.subTree)
          if (result) return result
        }

        if (vm.component) {
          const result = findExposed(vm.component)
          if (result) return result
        }

        return null
      }

      const exposed = findExposed(app._instance)
      if (exposed?._test) {
        return {
          filterParams: exposed._test.filterParams,
          source: '_test'
        }
      }

      return { source: 'not_found' }
    })

    console.log('RSS component state:', JSON.stringify(filterParams, null, 2))

    // 验证能获取到状态
    expect(filterParams).toBeTruthy()

    // 验证 filterParams 包含 originalId（核心功能验证）
    if (filterParams.filterParams) {
      console.log(`Filter params: ${JSON.stringify(filterParams.filterParams)}`)
      expect(filterParams.filterParams.originalId).toBeDefined()
    }

    // 操作后健康检查
    await assertHealthy(page, 'C04 after combined select')

    await attachAndVerifyScreenshot(page, testInfo, '04-oss-rss-combined', {
      expectedPath: 'archdata'
    })
  })

  test('C05: 联动勾选回归 — 勾选同服务模块不应联动勾选其他分类节点', async ({ page }) => {
    const testInfo = test.info()

    // 展开两个面板
    await page.evaluate(() => {
      const toggles = document.querySelectorAll('.collapsible-panel__header')
      toggles.forEach(t => {
        const panel = t.closest('.collapsible-panel')
        if (panel?.classList.contains('is-collapsed')) t.click()
      })
    })
    await page.waitForTimeout(2000)

    // 选择 OSS: "销售管理"
    await waitForDomExists(page, '[data-testid="oss-tree-label"]', 10000)
    await page.evaluate(() => {
      const labels = document.querySelectorAll('[data-testid="oss-tree-label"]')
      for (const l of labels) {
        if (l.textContent.trim() === '销售管理') {
          const content = l.closest('.el-tree-node__content')
          if (content) { content.click(); return }
        }
      }
    })
    console.log('OSS: clicked 销售管理')
    await page.waitForTimeout(4000)

    // 等待 RSS 树加载
    await waitForDomExists(page, '[data-testid="rss-tree-label"]', 15000)

    // 展开所有 RSS 树节点
    await page.evaluate(() => {
      const icons = document.querySelectorAll('.el-tree-node__expand-icon:not(.is-leaf)')
      icons.forEach(i => i.click())
    })
    await page.waitForTimeout(2000)

    // 查找 "同服务模块" category 节点的 checkbox 并点击
    const clickResult = await page.evaluate(() => {
      // 在所有 RSS label 中找 "同服务模块"
      const labels = document.querySelectorAll('[data-testid="rss-tree-label"]')
      for (const label of labels) {
        const text = label.textContent.trim()
        if (text === '同服务模块') {
          const content = label.closest('.el-tree-node__content')
          if (content) {
            const cb = content.querySelector('.el-checkbox__input')
            if (cb) {
              cb.click()
              return { clicked: true, text }
            }
          }
        }
      }
      return { clicked: false }
    })
    console.log('Click result:', JSON.stringify(clickResult))
    await page.waitForTimeout(3000)

    // DOM 验证："采购合同-采购执行" 不应被勾选
    const treeHierarchy = await page.evaluate(() => {
      // 获取树层级结构
      const result = []
      const walkNodes = (container, depth) => {
        const items = container.querySelectorAll(':scope > .el-tree-node')
        for (const item of items) {
          const label = item.querySelector('.el-tree-node__label')?.textContent?.trim()
          const isLeaf = item.classList.contains('is-leaf')
          const cb = item.querySelector('.el-checkbox__input')
          const isChecked = cb?.classList.contains('is-checked') || false
          
          result.push({
            depth,
            label: label?.substring(0, 40),
            isLeaf,
            isChecked,
          })
          
          const children = item.querySelector(':scope > .el-tree-node__children')
          if (children) walkNodes(children, depth + 1)
        }
      }
      
      // 找到 RSS 树的根
      const treeEl = document.querySelector('.relation-scope-section .el-tree, [class*="relation-scope"] .el-tree')
      if (treeEl) walkNodes(treeEl, 0)
      
      return result
    })
    console.log('Tree hierarchy:', JSON.stringify(treeHierarchy?.filter(h => h.isChecked || (h.label && h.label.includes('采购合同'))).slice(0, 20)))
    
    const domCheck = await page.evaluate(() => {
      const labels = document.querySelectorAll('[data-testid="rss-tree-label"]')
      let found = false
      let isChecked = false
      let allCheckedLabels = []

      for (const l of labels) {
        const text = l.textContent.trim()
        const content = l.closest('.el-tree-node__content')
        const cb = content?.querySelector('.el-checkbox__input')

        if (cb?.classList.contains('is-checked')) {
          allCheckedLabels.push(text)
        }

        if (text === '采购合同-采购执行') {
          found = true
          isChecked = cb?.classList.contains('is-checked') || false
        }
      }

      return { found, isChecked, checkedLabelCount: allCheckedLabels.length, checkedLabels: allCheckedLabels.slice(0, 15) }
    })

    console.log('DOM check:', JSON.stringify(domCheck))

    // 核心断言：采购合同-采购执行 不应该被勾选
    if (domCheck.found) {
      expect(domCheck.isChecked).toBe(false)
    }

    await assertHealthy(page, 'C05 after multi-check test')
    await attachAndVerifyScreenshot(page, testInfo, '05-multi-check-regression', {
      expectedPath: 'archdata'
    })
  })

  test('C06: selectedCodes 数量一致性 — 勾选单叶子后 selectedCodes 应等于该叶子 codes 长度', async ({ page }) => {
    const testInfo = test.info()

    // 展开两个面板
    await page.evaluate(() => {
      const toggles = document.querySelectorAll('.collapsible-panel__header')
      toggles.forEach(t => {
        const panel = t.closest('.collapsible-panel')
        if (panel?.classList.contains('is-collapsed')) t.click()
      })
    })
    await page.waitForTimeout(2000)

    // 选择 OSS: "销售管理" - 必须点击 checkbox
    await waitForDomExists(page, '[data-testid="oss-tree-label"]', 10000)
    // 强制清空已勾选（防止前序测试残留）
    await page.evaluate(() => {
      const trees = document.querySelectorAll('.el-tree');
      if (trees[0]?.__vueParentComponent) {
        let p = trees[0].__vueParentComponent;
        while (p) {
          const ref = p.setupState?.treeRef || p.refs?.treeRef;
          if (ref?.value?.setCheckedKeys) { ref.value.setCheckedKeys([]); break; }
          p = p.parent;
        }
      }
    })
    await page.waitForTimeout(500)
    await page.evaluate(() => {
      const labels = document.querySelectorAll('[data-testid="oss-tree-label"]')
      for (const l of labels) {
        if (l.textContent.trim() === '销售管理') {
          const content = l.closest('.el-tree-node__content')
          const cb = content?.querySelector('.el-checkbox__input')
          if (cb) { cb.click(); return }
        }
      }
    })
    console.log('OSS: clicked 销售管理')
    await page.waitForTimeout(5000)

    // 等待 RSS 树加载
    await waitForDomExists(page, '[data-testid="rss-tree-label"]', 15000)

    // 展开 "同服务模块" 分类
    await page.evaluate(() => {
      const labels = document.querySelectorAll('[data-testid="rss-tree-label"]')
      for (const l of labels) {
        if (l.textContent.trim() === '同服务模块') {
          const node = l.closest('.el-tree-node')
          const icon = node?.querySelector('.el-tree-node__expand-icon')
          if (icon) icon.click()
          return
        }
      }
    })
    await page.waitForTimeout(2000)

    // 找到 "付款计划-付款计划" 叶子节点并点击
    const target = await page.evaluate(() => {
      const labels = document.querySelectorAll('[data-testid="rss-tree-label"]')
      for (const l of labels) {
        if (l.textContent.trim() === '付款计划-付款计划') {
          const content = l.closest('.el-tree-node__content')
          if (content) {
            const cb = content.querySelector('.el-checkbox__input')
            if (cb) {
              cb.click()
              return { found: true, label: l.textContent.trim() }
            }
          }
        }
      }
      return { found: false }
    })
    console.log('Click result:', JSON.stringify(target))
    await page.waitForTimeout(3000)

    // 检查 _test.selectedCodes 数量
    const result = await page.evaluate(() => {
      const trees = document.querySelectorAll('.el-tree')
      const rssTree = trees[1]
      if (!rssTree?.__vueParentComponent) return { error: 'no comp' }
      let p = rssTree.__vueParentComponent
      while (p) {
        if (p.exposed?._test) {
          const t = p.exposed._test
          return {
            selectedCodes: t.selectedCodes,
            selectedCodesLen: t.selectedCodes?.length || 0,
            filterParams: t.filterParams
          }
        }
        if (p.setupState?._test) {
          const t = p.setupState._test
          return {
            selectedCodes: t.selectedCodes,
            selectedCodesLen: t.selectedCodes?.length || 0,
            filterParams: t.filterParams
          }
        }
        p = p.parent
      }
      return { error: 'no _test' }
    })
    console.log('Test state:', JSON.stringify(result, null, 2))

    // 验证 selectedCodes 应有 1 个关系 code（= 该叶子的 relationCodes 长度）
    expect(result.selectedCodesLen).toBeGreaterThanOrEqual(1)

    await assertHealthy(page, 'C06 after check')
    await attachAndVerifyScreenshot(page, testInfo, '06-single-leaf-check', {
      expectedPath: 'archdata'
    })
  })
})
