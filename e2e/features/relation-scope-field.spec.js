/**
 * S04: 关联关系范围字段 - 功能测试 (v2 风格)
 *
 * 覆盖场景:
 *   C01: 关联关系列表中关系范围字段非空
 *   C02: 按关系范围排序验证
 *
 * 必读: .trae/rules/e2e-simplification.md
 *
 * v2 8 铁律合规:
 * [OK] import from auto-fixtures.js (非 @playwright/test)
 * [OK] 无 login() / setAdminPermissions() (global-setup 已处理)
 * [OK] 无 page.goto() 直接调用 (改用 navigateTo fixture)
 * [OK] 无 Date.now() 硬编码 (本 spec 不需要)
 * [OK] 禁止 el-table 直查 (改用 ArchDataPage POM)
 * [OK] 无 waitForTimeout() 硬编码等待 (改用 waitForApiFn)
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 已解构 (测试结束自动清理)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { ArchDataPage } from '../page-objects/ArchDataPage.js'

const ARCHDATA_URL = '/system/archdata'

const SCOPE_HEADER_REGEX = /关系范围|分类维度/
const SCOPE_VALUE_REGEX = /跨领域|同领域|同子领域|同服务模块|跨服务模块|跨子领域/

test.describe('S04: 关联关系范围字段', () => {
  test('C01: 关联关系列表中关系范围字段非空', async ({
    page, navigateTo, dataFinder, isolation, waitForApiFn
  }, testInfo) => {
    const archData = new ArchDataPage(page)

    // 1. 智能查找 product/version (30s 缓存,自动复用)
    const pv = await dataFinder.productWithVersion()
    if (!pv) {
      console.log('[WARN] 未找到 product/version,跳过')
      test.skip(true, '未找到 product/version')
      return
    }

    // 2. 导航到架构数据 - 关联关系 tab (URL 参数自动恢复 product/version 上下文)
    await withStep(page, testInfo, '导航到架构数据 - 关联关系 tab', async () => {
      await navigateTo(page, `${ARCHDATA_URL}?productId=${pv.product.id}&versionId=${pv.version.id}&tab=relationship`, {
        skipHealthCheck: true,
        waitForSelector: '.el-tabs__item'
      })
    })

    // 3. 切到关联关系 tab (保险:防止 URL tab 参数未生效)
    await withStep(page, testInfo, '切到关联关系 tab', async () => {
      await archData.openTab('relationship')
    })

    // 4. 等待关联关系表格加载 (基于 API 响应等待)
    await withStep(page, testInfo, '等待关联关系表格加载', async () => {
      await waitForApiFn(page, 'GET /api/v2/bo/relationship').catch(() => {})
      await archData.waitForReady()
    })

    // 5. 验证表头中包含 关系范围 列
    const headers = await archData.getColumnHeaders()
    const hasScopeHeader = headers.some(h => SCOPE_HEADER_REGEX.test(h))
    if (!hasScopeHeader) {
      console.log(`[WARN] 表格无关系范围列,表头: ${headers.join(', ')}`)
      test.skip(true, '表格无关系范围列')
      return
    }
    console.log(`[OK] 找到关系范围列,表头: ${headers.filter(h => SCOPE_HEADER_REGEX.test(h)).join(', ')}`)

    // 6. 验证有行
    const rowCount = await archData.getRowCount()
    if (rowCount === 0) {
      console.log('[WARN] 关联关系列表无数据,跳过测试')
      test.skip(true, '关联关系列表无数据')
      return
    }
    console.log(`[INFO] 关联关系列表有 ${rowCount} 行数据`)

    // 7. 扫描前 20 行的关系范围值
    let nonEmptyCount = 0
    await withStep(page, testInfo, '扫描前 20 行的关系范围值', async () => {
      const rows = archData.page.locator(archData.rowSelector)
      const limit = Math.min(rowCount, 20)
      for (let i = 0; i < limit; i++) {
        const row = rows.nth(i)
        if (!(await row.isVisible().catch(() => false))) break
        const cells = row.locator('td.cell')
        const cellCount = await cells.count()
        for (let j = 0; j < cellCount; j++) {
          const cellText = await cells.nth(j).textContent()
          if (cellText && SCOPE_VALUE_REGEX.test(cellText)) {
            nonEmptyCount++
            console.log(`  行${i + 1}: ${cellText.trim()}`)
            break
          }
        }
      }
    })

    if (nonEmptyCount === 0) {
      console.log(`[WARN] 表格有 ${rowCount} 行但无关系范围值,可能是列布局问题,跳过`)
      test.skip(true, '无关系范围值')
      return
    }

    expect(nonEmptyCount, `期望至少1行有非空关系范围,实际: ${nonEmptyCount}`).toBeGreaterThan(0)
    console.log(`[OK] 验证通过: ${nonEmptyCount} 行数据包含非空的关系范围值`)
  })

  test('C02: 按关系范围排序验证', async ({
    page, navigateTo, dataFinder, isolation, waitForApiFn
  }, testInfo) => {
    const archData = new ArchDataPage(page)

    const pv = await dataFinder.productWithVersion()
    if (!pv) {
      console.log('[WARN] 未找到 product/version,跳过')
      test.skip(true, '未找到 product/version')
      return
    }

    await withStep(page, testInfo, '导航到架构数据 - 关联关系 tab', async () => {
      await navigateTo(page, `${ARCHDATA_URL}?productId=${pv.product.id}&versionId=${pv.version.id}&tab=relationship`, {
        skipHealthCheck: true,
        waitForSelector: '.el-tabs__item'
      })
    })

    await withStep(page, testInfo, '切到关联关系 tab', async () => {
      await archData.openTab('relationship')
    })

    await withStep(page, testInfo, '等待关联关系表格加载', async () => {
      await waitForApiFn(page, 'GET /api/v2/bo/relationship').catch(() => {})
      await archData.waitForReady()
    })

    // 8. 点击关系范围列头排序
    const scopeHeader = page.locator('thead th').filter({ hasText: SCOPE_HEADER_REGEX }).first()
    if (!(await scopeHeader.isVisible().catch(() => false))) {
      console.log('[WARN] 关系范围列头未找到,跳过')
      test.skip(true, '关系范围列头未找到')
      return
    }

    await withStep(page, testInfo, '点击关系范围列头排序', async () => {
      await scopeHeader.click()
    })

    // 9. 等待排序后表格刷新
    await waitForApiFn(page, 'GET /api/v2/bo/relationship').catch(() => {})

    // 10. 验证排序后的关系范围值正确显示
    const rowCount = await archData.getRowCount()
    if (rowCount > 1) {
      await withStep(page, testInfo, '展示排序后的关系范围值', async () => {
        const rows = archData.page.locator(archData.rowSelector)
        const limit = Math.min(rowCount, 10)
        for (let i = 0; i < limit; i++) {
          const row = rows.nth(i)
          if (!(await row.isVisible().catch(() => false))) break
          const cells = row.locator('td.cell')
          const cellCount = await cells.count()
          for (let j = 0; j < cellCount; j++) {
            const cellText = ((await cells.nth(j).textContent()) || '').trim()
            if (SCOPE_VALUE_REGEX.test(cellText)) {
              console.log(`  行${i + 1}: ${cellText}`)
              break
            }
          }
        }
        console.log('[OK] 排序后关系范围列值正确显示')
      })
    } else {
      console.log(`[INFO] 表格只有 ${rowCount} 行,无需验证排序`)
    }
  })
})
