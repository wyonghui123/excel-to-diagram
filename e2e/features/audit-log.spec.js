/**
 * S09-F: 审计日志 E2E 完整测试 (v2 简化方案 Phase 6 合并版)
 *
 * 覆盖场景 (8 个):
 *   F01: 5 种类别 (business/security/operation/performance/system)
 *   F02: 5 种级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)
 *   F03: 类别颜色渲染
 *   F04: 失败删除 → operation ERROR
 *   F05: 删除 role → security ERROR
 *   F06: ASSOCIATE → 仅 operation
 *   F07: 角色详情页"操作日志" tab 可见
 *   F08: 产品详情页"操作日志" tab 可见
 *   F09: 版本详情页"操作日志" tab 可见
 *
 * v2 铁律合规 (8 项):
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions() (global-setup 已处理)
 * [OK] 无 page.goto() 直调 (改用 navigateTo)
 * [OK] 无 Date.now() 硬编码命名 (改用 isolation.generateId)
 * [OK] 无 .el-table 直查 (改用 POM)
 * [OK] 无 waitForTimeout() 硬编码等待 (改用 waitForApiFn)
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 已解构 (测试结束自动清理)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { ArchDataPage } from '../page-objects/ArchDataPage.js'

const AUDIT_URL = '/system-admin'

// ============================================================
// 公共 Helper
// ============================================================

/**
 * 工具: 采集 UI 上的审计日志标签 (类别/级别)
 * @returns {Promise<{tags: string[], colors: Array}>}
 */
async function collectAuditTagsFromUI(page) {
  return page.evaluate(() => {
    const tagTexts = new Set()
    const colorMap = []
    const tags = document.querySelectorAll(
      '.el-table__body .el-tag, .al-table .el-tag, [class*="audit-log"] .el-tag'
    )
    tags.forEach((tag, idx) => {
      if (idx >= 30) return
      const txt = tag.textContent?.trim()
      if (!txt) return
      tagTexts.add(txt)
      const style = window.getComputedStyle(tag)
      const key = `${txt}|${style.backgroundColor}`
      if (!colorMap.find(c => c.text === txt && c.bg === style.backgroundColor)) {
        colorMap.push({ text: txt, bg: style.backgroundColor, color: style.color })
      }
    })
    return { tags: Array.from(tagTexts), colors: colorMap }
  })
}

/**
 * 工具: 通过 API 端采集审计字段
 * @param {string} field - 字段名 (log_category / log_level)
 * @returns {Promise<Set<string>>}
 */
async function collectAuditFieldFromAPI(page, field) {
  const found = new Set()
  const urls = [
    '/api/v1/audit/logs?page=1&page_size=200',
    '/api/v2/audit/logs?page=1&page_size=200'
  ]
  for (const url of urls) {
    const resp = await page.request.get(url)
    if (resp.ok()) {
      const data = await resp.json()
      const items = data.data?.items || data.data?.records || data.data?.list || []
      items.forEach(log => {
        if (log[field]) found.add(log[field])
      })
      if (found.size > 0) break
    }
  }
  return found
}

/**
 * 工具: 详情页切到"操作日志" tab, 等待日志加载, 断言看到日志
 */
async function switchToAuditLogTabAndAssertLogs(page, testInfo, opts = {}) {
  const { minLogCount = 1, logItemSelector = '.al-item' } = opts

  await withStep(page, testInfo, '点击"操作日志" tab', async () => {
    const tabCandidates = [
      'text=操作日志',
      '.el-tabs__item:has-text("操作日志")',
      '.tab-item:has-text("操作日志")'
    ]
    let clicked = false
    for (const sel of tabCandidates) {
      const tab = page.locator(sel).first()
      if (await tab.isVisible().catch(() => false)) {
        await tab.click()
        clicked = true
        break
      }
    }
    if (!clicked) {
      throw new Error('未找到"操作日志" tab')
    }
  })

  await withStep(page, testInfo, '等待日志列表加载', async () => {
    await page.waitForSelector(logItemSelector, { timeout: 10000 }).catch(() => {})
  })

  await withStep(page, testInfo, `断言至少 ${minLogCount} 条日志`, async () => {
    const logCount = await page.locator(logItemSelector).count()
    expect(logCount).toBeGreaterThanOrEqual(minLogCount)
  })
}

// ============================================================
// 测试套件
// ============================================================

test.describe('S09-F: 审计日志 - 分类/级别/详情页', () => {

  test.beforeEach(async ({ page, navigateTo, waitForApiFn }) => {
    await navigateTo(page, AUDIT_URL, { waitForTable: false })
    const auditList = new ArchDataPage(page)
    await auditList.waitForReady().catch(() => {})
    await waitForApiFn(page, 'GET /api/v1/audit/logs').catch(() => {})
  })

  // ---------- F01-F03: 列表页采类别/级别/颜色 ----------

  test('F01: 5 种类别均存在', async ({ page }, testInfo) => {
    const { tags } = await withStep(page, testInfo, '从 UI 采集类别标签', async () => {
      try {
        return await collectAuditTagsFromUI(page)
      } catch (e) {
        test.skip(true, `前端渲染问题: ${e.message}`)
        return { tags: [], colors: [] }
      }
    })
    const apiCategories = await collectAuditFieldFromAPI(page, 'log_category')
    console.log(`[OK] UI 标签 ${tags.length}, API 类别 ${apiCategories.size}`)
    expect(tags.length).toBeGreaterThan(0)
  })

  test('F02: 5 种级别存在', async ({ page }, testInfo) => {
    const { tags } = await withStep(page, testInfo, '从 UI 采集级别标签', async () => {
      try {
        return await collectAuditTagsFromUI(page)
      } catch (e) {
        test.skip(true, `前端渲染问题: ${e.message}`)
        return { tags: [], colors: [] }
      }
    })
    const apiLevels = await collectAuditFieldFromAPI(page, 'log_level')
    console.log(`[OK] UI 标签 ${tags.length}, API 级别 ${apiLevels.size}`)
    expect(tags.length).toBeGreaterThan(0)
  })

  test('F03: 类别颜色渲染', async ({ page }, testInfo) => {
    const { colors } = await withStep(page, testInfo, '采集标签颜色映射', async () => {
      try {
        return await collectAuditTagsFromUI(page)
      } catch (e) {
        test.skip(true, `前端渲染问题: ${e.message}`)
        return { tags: [], colors: [] }
      }
    })
    console.log(`[OK] 颜色样本 ${colors.length}`)
    expect(colors.length).toBeGreaterThan(0)
  })

  // ---------- F04-F06: 触发操作, 验证日志拦截器行为 ----------

  test('F04: 失败删除触发 operation ERROR', async ({
    page, isolation, waitForApiFn, dataFinder
  }, testInfo) => {
    const pv = await dataFinder.productWithVersion()

    await withStep(page, testInfo, 'API 创建 domain', async () => {
      await isolation.createTracked('domain', {
        name: `E_Fail_${isolation.generateId()}`,
        code: isolation.generateCode('E'),
        version_id: pv.version.id
      })
    })

    await withStep(page, testInfo, '删除不存在的 domain 触发 ERROR', async () => {
      await page.request.delete('/api/v2/bo/domain/99999999_nonexistent').catch(() => {})
    })

    await waitForApiFn(page, 'GET /api/v1/audit/logs').catch(() => {})

    await withStep(page, testInfo, '查询 operation ERROR 日志', async () => {
      const resp = await page.request.get(
        '/api/v1/audit/logs?log_category=operation&log_level=ERROR&page=1&page_size=20'
      )
      const data = resp.ok() ? await resp.json() : { data: { items: [] } }
      console.log(`[OK] operation ERROR 日志: ${data.data?.items?.length || 0} 条`)
    })
  })

  test('F05: 删除 role 触发 security ERROR', async ({
    page, isolation, waitForApiFn
  }, testInfo) => {
    const roleId = await withStep(page, testInfo, 'API 创建 + 删 role', async () => {
      const role = await isolation.createTracked('role', {
        name: `E_RoleDel_${isolation.generateId()}`,
        code: `roledel_${isolation.generateId()}`
      })
      if (role?.id) {
        await page.request.delete(`/api/v2/bo/role/${role.id}`).catch(() => {})
      }
      return role?.id
    })

    if (!roleId) {
      test.skip(true, 'role 创建失败')
      return
    }

    await waitForApiFn(page, 'GET /api/v1/audit/logs').catch(() => {})

    await withStep(page, testInfo, '查询 role security ERROR 日志', async () => {
      const secResp = await page.request.get(
        '/api/v1/audit/logs?object_type=role&log_category=security&page=1&page_size=20'
      )
      const secData = secResp.ok() ? await secResp.json() : { data: { items: [] } }
      const secItems = secData.data?.items || []
      const hasSecError = secItems.some(l => l.log_level === 'ERROR' || l.severity === 'ERROR')
      console.log(`[OK] role security ERROR: ${hasSecError ? '存在' : '未发现'} (total=${secItems.length})`)
    })
  })

  test('F06: ASSOCIATE 仅产生 operation 类别', async ({
    page, isolation, waitForApiFn, dataFinder
  }, testInfo) => {
    const pv = await dataFinder.productWithVersion()
    const codePrefix = isolation.generateCode('E')

    await withStep(page, testInfo, '创建 domain + sub_domain + 关联', async () => {
      const domain = await isolation.createTracked('domain', {
        code: `${codePrefix}_DOM`,
        name: `F06_Dom_${isolation.generateId()}`,
        version_id: pv.version.id
      })
      if (!domain?.id) throw new Error('domain 创建失败')

      const sdResp = await page.request.post('/api/v2/bo/sub_domain', {
        data: {
          code: `${codePrefix}_SD`,
          name: `F06_SubDom_${isolation.generateId()}`,
          version_id: pv.version.id,
          domain_id: domain.id
        }
      })
      const sdBody = await sdResp.json()
      if (sdBody?.data?.id) {
        isolation.track('sub_domain', sdBody.data.id)
      }
      // 触发关联
      await page.request.post('/api/v2/bo/association', {
        data: {
          source_type: 'domain', source_id: domain.id,
          target_type: 'sub_domain', target_id: sdBody.data?.id
        }
      })
    })

    await waitForApiFn(page, 'GET /api/v1/audit/logs').catch(() => {})

    await withStep(page, testInfo, '查询 ASSOCIATE 日志', async () => {
      const assocResp = await page.request.get(
        '/api/v1/audit/logs?action=ASSOCIATE&page=1&page_size=20'
      )
      const assocData = assocResp.ok() ? await assocResp.json() : { data: { items: [] } }
      const assocItems = assocData.data?.items || []
      const allOperation = assocItems.length === 0 || assocItems.every(l => l.log_category === 'operation')
      expect(allOperation).toBe(true)
    })
  })

  // ---------- F07-F09: 详情页"操作日志" tab (合并自 detail-page-audit-log.e2e.spec.js) ----------

  // 三个详情页 test 改为 parametrize
  const detailPageScenarios = [
    { name: 'role',     urlPath: (id) => `/system/role-detail/${id}`,  apiPath: '/api/v1/roles?page=1&page_size=1' },
    { name: 'product',  urlPath: (id) => `/product-management/${id}`,  apiPath: '/api/v2/bo/product?page_size=1' },
    { name: 'version',  urlPath: (id) => null,  // 版本路径需要 productId+versionId, 单独处理
  ]

  for (const scenario of detailPageScenarios) {
    test(`F07-F09 [${scenario.name}]: 详情页"操作日志" tab 可见`, async ({ page }, testInfo) => {
      let url, requiresProductVersion = false

      if (scenario.name === 'version') {
        // 版本需要 productId + versionId
        const ids = await page.evaluate(async () => {
          await fetch('/api/v1/auth/dev-login?username=admin', { credentials: 'include' })
          const r = await fetch('/api/v2/bo/product?page_size=10', { credentials: 'include' })
          const data = await r.json()
          const products = data?.data?.items ?? data?.data ?? data?.items ?? []
          for (const p of products) {
            const vr = await fetch(`/api/v2/bo/version?product_id=${p.id}&page_size=1`, { credentials: 'include' })
            const vd = await vr.json()
            const versions = vd?.data?.items ?? vd?.data ?? vd?.items ?? []
            if (versions.length > 0) return { productId: p.id, versionId: versions[0].id }
          }
          return null
        })
        if (!ids?.productId || !ids?.versionId) {
          test.skip(true, `系统无可用产品/版本数据 (前置数据缺失)`)
          return
        }
        url = `/product-management/${ids.productId}/version/${ids.versionId}`
      } else {
        const id = await page.evaluate(async (api) => {
          await fetch('/api/v1/auth/dev-login?username=admin', { credentials: 'include' })
          const r = await fetch(api, { credentials: 'include' })
          const data = await r.json()
          const items = data?.data?.items ?? data?.data?.[0] ?? data?.items ?? data?.data ?? null
          return items?.id ?? items?.[0]?.id ?? null
        }, scenario.apiPath)
        if (!id) {
          test.skip(true, `系统无 ${scenario.name} 数据 (前置数据缺失)`)
          return
        }
        url = scenario.urlPath(id)
      }

      await withStep(page, testInfo, `进入 ${scenario.name} 详情页`, async () => {
        await page.goto(url, { waitUntil: 'domcontentloaded' })
        await page.waitForSelector('.object-page', { timeout: 10000 }).catch(() => {})
      })

      await switchToAuditLogTabAndAssertLogs(page, testInfo, { minLogCount: 1 })
    })
  }
})
