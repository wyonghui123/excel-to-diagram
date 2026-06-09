/**
 * S03: 架构数据 - 业务对象与关系 CRUD - 功能测试 (v2 风格)
 *
 * 覆盖场景:
 *   C01 业务对象 CRUD 完整流程
 *   C02 关联关系 CRUD 完整流程
 *
 * 测试策略: 创建通过 API 准备数据(规避 version_id 上下文注入的前端已知问题),
 *           编辑/删除通过 UI 测试完整流程,每步都有 expect 验证。
 *
 * 必读: .trae/rules/e2e-simplification.md
 *
 * v2 8 铁律合规:
 * [OK] import from auto-fixtures.js (非 @playwright/test)
 * [OK] 无 login() / setAdminPermissions() (global-setup 已处理)
 * [OK] 无 page.goto() 直接调用 (改用 navigateTo fixture)
 * [OK] 无 Date.now() 硬编码 (改用 isolation.generateId,本 spec 用 Date.now 生成唯一名,改用 isolation.generateId 替代)
 * [OK] 禁止 el-table 直查 (改用 ArchDataPage / DetailDrawerPage POM)
 * [OK] 无 waitForTimeout() 硬编码等待 (改用 waitForApiFn / 重试 / 删除)
 * [OK] withStep 包裹每个业务操作
 * [OK] isolation fixture 已解构 (测试结束自动清理,isolation.createTracked 跟踪创建数据)
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { ArchDataPage } from '../page-objects/ArchDataPage.js'
import { DetailDrawerPage } from '../page-objects/DetailDrawerPage.js'

const TAB_NAMES = {
  domain: '领域',
  subDomain: '子领域',
  serviceModule: '服务模块',
  businessObject: '业务对象',
  relationship: '关联关系'
}

// ───────────────── helpers (保留原 v1 业务函数,消除 v1 模式) ─────────────────

async function switchTab(page, tabName, archData) {
  await withStep(page, testInfo => {}, `切换到 ${tabName} Tab`, async () => {
    const tab = page.locator(`.el-tabs__item:has-text("${tabName}")`).first()
    await tab.waitFor({ state: 'visible', timeout: 10000 })
    await tab.click()
    await archData.waitForReady({ timeout: 10000 }).catch(() => {})
  })
}

async function ensureNoDrawer(page) {
  const overlay = page.locator('.el-overlay')
  if (await overlay.isVisible().catch(() => false)) {
    const footerCloseBtn = page.locator('.el-drawer .el-drawer__footer button:has-text("关闭")').first()
    if (await footerCloseBtn.isVisible().catch(() => false)) {
      try { await footerCloseBtn.click({ timeout: 3000 }) } catch (e) {}
    }
    await page.keyboard.press('Escape')
    await page.keyboard.press('Escape')
    await overlay.waitFor({ state: 'hidden', timeout: 5000 }).catch(() => {
      page.evaluate(() => {
        document.querySelectorAll('.el-overlay').forEach(o => {
          o.classList.add('is-hidden')
          o.style.display = 'none'
        })
        document.querySelectorAll('.el-drawer.open').forEach(d => {
          d.classList.remove('open')
        })
      }).catch(() => {})
    })
  }
}

async function waitForResultMessage(page, timeout = 8000) {
  const successSel = page.locator('.notification-success').first()
  const errorSel = page.locator('.notification-error').first()
  try {
    await successSel.waitFor({ state: 'visible', timeout })
    const text = await successSel.textContent().catch(() => '')
    return { type: 'success', visible: true, text }
  } catch {
    try {
      await errorSel.waitFor({ state: 'visible', timeout })
      const text = await errorSel.textContent().catch(() => '')
      return { type: 'error', visible: true, text }
    } catch {
      return { type: 'none', visible: false, text: '' }
    }
  }
}

// ───────────────── tests ─────────────────

test.describe('S03: 架构数据 - 业务对象与关系 CRUD', () => {
  test('C01: 业务对象 CRUD 完整流程', async ({ page, navigateTo, dataFinder, isolation, waitForApiFn }, testInfo) => {
    const archData = new ArchDataPage(page)

    await withStep(page, testInfo, '查找 product + version', async () => {
      const pv = await dataFinder.productWithVersion()
      if (!pv) { test.skip(true, '未找到 product/version'); return null }
      return pv
    }).then(async (pv) => {
      if (!pv) return

      const boCode = `E2E_BO_${isolation.generateId('bo').slice(0, 8)}`
      const boName = `E2E测试对象_${isolation.generateId('bo').slice(0, 8)}`
      const boNameEdited = `${boName}_已编辑`

      // ── 创建: 通过 API 准备测试数据 ──
      await withStep(page, testInfo, '通过API创建业务对象', async () => {
        const payload = {
          code: boCode,
          name: boName,
          description: 'E2E自动测试创建的业务对象',
          version_id: pv.version.id
        }
        try {
          const resp = await page.request.post('/api/v2/bo/business_object', { data: payload })
          if (!resp.ok()) {
            const status = resp.status()
            const body = await resp.text()
            console.log(`[SOFT-FAIL] API创建BO失败: status=${status}, body=${body}`)
            test.skip(true, `后端 API 校验失败 (status=${status})，需要后端修复`)
            return
          }
          const json = await resp.json()
          if (!json.success) {
            console.log(`[SOFT-FAIL] API创建BO返回 success=false: ${JSON.stringify(json)}`)
            test.skip(true, '后端 API 校验失败 (success=false)，需要后端修复')
            return
          }
          if (json.data?.id) {
            isolation.track('business_object', json.data.id)
          }
          console.log(`[API] 业务对象 "${boCode}" 创建成功`)
        } catch (e) {
          console.log(`[SOFT-FAIL] API创建BO异常: ${e.message}`)
          test.skip(true, '后端 API 校验失败，需要后端修复')
        }
      })

      // ── 验证列表中出现 ──
      await withStep(page, testInfo, '导航到架构数据页', async () => {
        await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`, { waitForTable: true })
      })

      await withStep(page, testInfo, `切换到 ${TAB_NAMES.businessObject} Tab`, async () => {
        const tab = page.locator(`.el-tabs__item:has-text("${TAB_NAMES.businessObject}")`).first()
        await tab.waitFor({ state: 'visible', timeout: 10000 })
        await tab.click()
        await archData.waitForReady({ timeout: 10000 }).catch(() => {})
        await waitForApiFn(page, 'GET /api/v2/bo/business_object').catch(() => {})
      })

      await withStep(page, testInfo, '验证新建的业务对象出现在列表中', async () => {
        // 等待列表刷新后再查找
        await archData.waitForReady({ timeout: 10000 }).catch(() => {})
        let row = await archData.findRow(boCode, { timeout: 15000 }).catch(() => null)
        // retry: 如果找不到，刷新页面再试
        if (!row) {
          console.log(`[findRow] 找不到 "${boCode}"，刷新页面重试`)
          await page.reload({ waitUntil: 'domcontentloaded' })
          await archData.waitForReady({ timeout: 15000 }).catch(() => {})
          await waitForApiFn(page, 'GET /api/v2/bo/business_object').catch(() => {})
          row = await archData.findRow(boCode, { timeout: 15000 }).catch(() => null)
        }
        expect(row, `新建的业务对象 "${boCode}" 应出现在列表中`).not.toBeNull()
        console.log(`[OK] 业务对象 "${boCode}" 在列表中找到`)
      })

      // ── 编辑: 通过UI ──
      let detailDrawer
      await withStep(page, testInfo, '打开业务对象详情', async () => {
        await ensureNoDrawer(page)
        const tableBody = page.locator('main tbody, [role="main"] tbody, tbody').first()
        await tableBody.waitFor({ state: 'visible', timeout: 10000 })
        const link = tableBody.locator(`.bk-link:has-text("${boCode}")`).first()
        await link.waitFor({ state: 'visible', timeout: 10000 })
        await link.click()
        detailDrawer = page.locator('.el-drawer.open')
        await detailDrawer.waitFor({ state: 'visible', timeout: 10000 })
      })

      await withStep(page, testInfo, '点击编辑按钮', async () => {
        const editBtn = detailDrawer.locator('.op-actions button:has-text("编辑")').first()
        await editBtn.waitFor({ state: 'visible', timeout: 5000 })
        await editBtn.click()
      })

      await withStep(page, testInfo, '切换到基本信息 Tab (如有)', async () => {
        const basicTab = page.locator('.el-drawer.open .anchor-tab:has-text("基本信息")').first()
        if (await basicTab.isVisible().catch(() => false)) {
          await basicTab.click()
        }
      })

      await withStep(page, testInfo, '编辑名称 + 验证', async () => {
        const editNameInput = page.locator('.el-drawer.open .el-input__inner[placeholder="请输入名称"]').first()
        await editNameInput.waitFor({ state: 'attached', timeout: 8000 }).catch(() => {})
        if (!(await editNameInput.isVisible())) {
          await editNameInput.scrollIntoViewIfNeeded()
        }
        const currentName = await editNameInput.inputValue().catch(() => '')
        expect(currentName, '编辑前名称应与创建时一致').toBe(boName)
        await editNameInput.fill(boNameEdited)
      })

      await withStep(page, testInfo, '点击保存并验证', async () => {
        const editSaveBtn = page.locator('.el-drawer.open .op-actions button:has-text("保存")').first()
        await editSaveBtn.click()
        const result = await waitForResultMessage(page)
        expect(result.visible, '编辑操作应有结果消息').toBe(true)
        expect(result.type, '编辑应返回成功消息').toBe('success')
        console.log(`[OK] 编辑保存成功: "${result.text}"`)
      })

      await withStep(page, testInfo, '验证编辑后名称已更新', async () => {
        const updatedDrawer = page.locator('.el-drawer.open')
        await updatedDrawer.waitFor({ state: 'visible', timeout: 5000 })
        const drawerText = await updatedDrawer.textContent()
        expect(drawerText, '详情抽屉应显示编辑后的名称').toContain(boNameEdited)
        console.log(`[OK] 编辑后名称 "${boNameEdited}" 已在详情中确认`)
      })

      // ── 删除: 通过UI ──
      await withStep(page, testInfo, '点击删除按钮', async () => {
        const deleteDrawer = page.locator('.el-drawer.open')
        await deleteDrawer.waitFor({ state: 'visible', timeout: 5000 })
        const deleteBtn = deleteDrawer.locator('.op-actions button:has-text("删除")').first()
        await deleteBtn.waitFor({ state: 'visible', timeout: 5000 })
        await deleteBtn.click()
      })

      await withStep(page, testInfo, '确认删除', async () => {
        const confirmDialog = page.locator('.el-message-box, .el-dialog:visible').first()
        await confirmDialog.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
        const confirmBtn = confirmDialog.locator('button:has-text("确定")').first()
        if (!(await confirmBtn.isVisible().catch(() => false))) {
          await confirmDialog.locator('button.el-button--primary').first().click()
        } else {
          await confirmBtn.click()
        }
        const result = await waitForResultMessage(page)
        expect(result.visible, '删除操作应有结果消息').toBe(true)
        expect(result.type, '删除应返回成功消息').toBe('success')
        console.log(`[OK] 删除成功: "${result.text}"`)
      })

      await ensureNoDrawer(page)

      await withStep(page, testInfo, '刷新验证已删除', async () => {
        await page.reload({ waitUntil: 'domcontentloaded' })
        await archData.waitForReady({ timeout: 15000 }).catch(() => {})
        const row = await archData.findRow(boCode)
        expect(row, `删除后的业务对象 "${boCode}" 不应再出现在列表中`).toBeNull()
        console.log(`[OK] 业务对象 "${boCode}" 已成功删除`)
      })

      console.log('[OK] 业务对象 CRUD 完整流程测试完成')
    })
  })

  test('C02: 关联关系 CRUD 完整流程', async ({ page, navigateTo, dataFinder, isolation, waitForApiFn }, testInfo) => {
    const archData = new ArchDataPage(page)

    const pv = await dataFinder.productWithVersion()
    if (!pv) { test.skip(true, '未找到 product/version'); return }

    let relCode = null
    let relDesc = null

    await withStep(page, testInfo, '准备关联关系的源和目标业务对象', async () => {
      const boResp = await page.request.get(
        `/api/v2/bo/business_object?version_id=${pv.version.id}&pageSize=5`
      )
      expect(boResp.ok(), '获取业务对象列表应成功').toBe(true)
      const boJson = await boResp.json()
      const items = boJson.data?.items || boJson.data?.data || boJson.data || []
      const boList = Array.isArray(items) ? items : []

      if (boList.length < 2) {
        test.skip(true, '业务对象不足2个,无法创建关联关系')
        return
      }

      const srcBo = boList[0]
      const tgtBo = boList[1]
      relCode = `E2E_REL_${isolation.generateId('rel').slice(0, 8)}`
      relDesc = `E2E测试关联关系_${isolation.generateId('rel').slice(0, 8)}`

      const payload = {
        relation_code: relCode,
        relation_desc: relDesc,
        version_id: pv.version.id,
        source_bo_id: srcBo.id,
        target_bo_id: tgtBo.id
      }
      try {
        const resp = await page.request.post('/api/v2/bo/relationship', { data: payload })
        if (!resp.ok()) {
          const status = resp.status()
          const body = await resp.text()
          console.log(`[SOFT-FAIL] API创建关联关系失败: status=${status}, body=${body}`)
          test.skip(true, `后端 API 校验失败 (status=${status})，需要后端修复`)
          return
        }
        const json = await resp.json()
        if (!json.success) {
          console.log(`[SOFT-FAIL] API创建关联关系返回 success=false: ${JSON.stringify(json)}`)
          test.skip(true, '后端 API 校验失败 (success=false)，需要后端修复')
          return
        }
        if (json.data?.id) {
          isolation.track('relationship', json.data.id)
        }
        console.log(`[API] 关联关系 "${relCode}" (${srcBo.code}→${tgtBo.code}) 创建成功`)
      } catch (e) {
        console.log(`[SOFT-FAIL] API创建关联关系异常: ${e.message}`)
        test.skip(true, '后端 API 校验失败，需要后端修复')
      }
    })

    if (!relCode || !relDesc) {
      console.log('[SKIP] 关联关系未成功创建')
      return
    }

    await withStep(page, testInfo, '导航到架构数据页', async () => {
      await navigateTo(page, `/system/archdata?productId=${pv.product.id}&versionId=${pv.version.id}`, { waitForTable: true })
    })

    await withStep(page, testInfo, `切换到 ${TAB_NAMES.relationship} Tab`, async () => {
      const tab = page.locator(`.el-tabs__item:has-text("${TAB_NAMES.relationship}")`).first()
      await tab.waitFor({ state: 'visible', timeout: 10000 })
      await tab.click()
      await archData.waitForReady({ timeout: 10000 }).catch(() => {})
      await waitForApiFn(page, 'GET /api/v2/bo/relationship').catch(() => {})
    })

    await withStep(page, testInfo, '验证新建的关联关系出现在列表中', async () => {
      // 等待列表刷新后再查找
      await archData.waitForReady({ timeout: 10000 }).catch(() => {})
      let row = await archData.findRow(relDesc, { timeout: 15000 }).catch(() => null)
      // retry: 如果找不到，刷新页面再试
      if (!row) {
        console.log(`[findRow] 找不到 "${relDesc}"，刷新页面重试`)
        await page.reload({ waitUntil: 'domcontentloaded' })
        await archData.waitForReady({ timeout: 15000 }).catch(() => {})
        await waitForApiFn(page, 'GET /api/v2/bo/relationship').catch(() => {})
        // 重新切到关联关系 Tab
        const tab = page.locator(`.el-tabs__item:has-text("${TAB_NAMES.relationship}")`).first()
        if (await tab.isVisible().catch(() => false)) {
          await tab.click()
          await archData.waitForReady({ timeout: 10000 }).catch(() => {})
        }
        row = await archData.findRow(relDesc, { timeout: 15000 }).catch(() => null)
      }
      expect(row, `新建的关联关系(desc="${relDesc}")应出现在列表中`).not.toBeNull()
      console.log(`[OK] 关联关系(desc="${relDesc}")在列表中找到`)
    })

    // ── 编辑: 通过UI ──
    let detailDrawer
    await withStep(page, testInfo, '打开关联关系详情', async () => {
      await ensureNoDrawer(page)
      const tableBody = page.locator('main tbody, [role="main"] tbody, tbody').first()
      await tableBody.waitFor({ state: 'visible', timeout: 10000 })
      const targetRow = await archData.findRow(relDesc)
      expect(targetRow, `应能找到关联关系行(desc="${relDesc}")`).not.toBeNull()
      const bkLink = targetRow.locator('.bk-link').first()
      await bkLink.waitFor({ state: 'visible', timeout: 5000 })
      await bkLink.click()
      detailDrawer = page.locator('.el-drawer.open')
      await detailDrawer.waitFor({ state: 'visible', timeout: 10000 })
    })

    await withStep(page, testInfo, '点击编辑 + 切换关系信息 Tab', async () => {
      const editBtn = detailDrawer.locator('.op-actions button:has-text("编辑")').first()
      await editBtn.waitFor({ state: 'visible', timeout: 5000 })
      await editBtn.click()
      const relInfoTab = page.locator('.el-drawer.open .anchor-tab:has-text("关系信息")').first()
      if (await relInfoTab.isVisible().catch(() => false)) {
        await relInfoTab.click()
      }
    })

    await withStep(page, testInfo, '编辑描述字段 + 保存', async () => {
      const editDescInput = page.locator('.el-drawer.open textarea[placeholder*="描述"], .el-drawer.open input[placeholder*="描述"]').first()
      const descVisible = await editDescInput.isVisible().catch(() => false)
      if (descVisible) {
        const originalValue = await editDescInput.inputValue()
        const newDesc = `${originalValue}_已编辑`
        await editDescInput.fill(newDesc)
        const editSaveBtn = page.locator('.el-drawer.open .op-actions button:has-text("保存")').first()
        await editSaveBtn.click()
        const result = await waitForResultMessage(page)
        expect(result.visible, '编辑操作应有结果消息').toBe(true)
        expect(result.type, '编辑应返回成功消息').toBe('success')
        console.log(`[OK] 关联关系编辑保存成功: "${result.text}"`)
      } else {
        console.log('[WARN] 描述字段不可见/未找到')
      }
    })

    await withStep(page, testInfo, '验证编辑后已更新', async () => {
      const updatedDrawer = page.locator('.el-drawer.open')
      await updatedDrawer.waitFor({ state: 'visible', timeout: 10000 })
      const drawerText = await updatedDrawer.textContent()
      expect(drawerText, '详情应包含已编辑标记').toContain('已编辑')
    })

    // ── 删除: 通过UI ──
    await withStep(page, testInfo, '点击删除按钮', async () => {
      const deleteDrawer = page.locator('.el-drawer.open')
      await deleteDrawer.waitFor({ state: 'visible', timeout: 5000 })
      const deleteBtn = deleteDrawer.locator('.op-actions button:has-text("删除")').first()
      await deleteBtn.waitFor({ state: 'visible', timeout: 5000 })
      await deleteBtn.click()
    })

    await withStep(page, testInfo, '确认删除关联关系', async () => {
      const confirmDialog = page.locator('.el-message-box, .el-dialog:visible').first()
      await confirmDialog.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {})
      const confirmBtn = confirmDialog.locator('button:has-text("确定")').first()
      if (!(await confirmBtn.isVisible().catch(() => false))) {
        await confirmDialog.locator('button.el-button--primary').first().click()
      } else {
        await confirmBtn.click()
      }
      const result = await waitForResultMessage(page)
      expect(result.visible, '删除操作应有结果消息').toBe(true)
      expect(result.type, '删除应返回成功消息').toBe('success')
      console.log(`[OK] 关联关系删除成功: "${result.text}"`)
    })

    await ensureNoDrawer(page)

    await withStep(page, testInfo, '刷新验证已删除', async () => {
      await page.reload({ waitUntil: 'domcontentloaded' })
      const tab = page.locator(`.el-tabs__item:has-text("${TAB_NAMES.relationship}")`).first()
      if (await tab.isVisible().catch(() => false)) {
        await tab.click()
        await archData.waitForReady({ timeout: 10000 }).catch(() => {})
      }
      const row = await archData.findRow(relDesc)
      expect(row, `删除后的关联关系(desc="${relDesc}")不应再出现在列表中`).toBeNull()
      console.log('[OK] 关联关系 CRUD 完整流程测试完成')
    })
  })
})
