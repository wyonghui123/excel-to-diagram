/**
 * 规则中心 - 配置发布闭环 E2E（R-A10 / spec-rule-model §12.5 M7-4）
 *
 * 覆盖链路：改值 → 保存草稿 → 发布草稿 → 回滚上一版本 → 历史 action tag
 * 断言点：
 *   1. 抽屉 config-section 渲染（可写目标 = control_parameter_value）
 *   2. 保存草稿发出 POST /api/v2/rules 且返回成功
 *   3. 发布草稿按钮出现 → POST /config/publish 成功 → 历史出现「发布」
 *   4. 回滚按钮出现 → POST /config/rollback 成功 → 历史出现「回滚」且取值恢复
 * 清理：发布失败时删除草稿；回滚失败时用 API 兜底回滚（不留下生效值变更）
 *
 * v2 铁律: import 自 auto-fixtures.js / withStep 自 auto-trace.js
 *          / 不用 page.goto + waitForTimeout / 不用 networkidle
 * 注：试算（simulate）由 meta/tests/test_rule_simulate_api.py 覆盖，不在本用例内重复。
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'
import { attachScreenshot, getAuthHeaders } from '../helpers/auth.js'

const RULE_CENTER_PATH = '/system/rule-center'
const TAB_ID = 'control_parameter'
const VALUE_STEP = '_e2e'

/**
 * 生成一个仍可被 _convert 接受的新取值：
 * 数字 +1（保持整数/小数形态）、布尔翻转、其它追加后缀。
 */
function nextValue(current) {
  const value = (current || '').trim()
  if (value === '') return '1'
  if (/^-?\d+$/.test(value)) return String(Number(value) + 1)
  if (/^-?\d+\.\d+$/.test(value)) return String(Math.round((Number(value) + 1) * 100) / 100)
  if (value === 'true') return 'false'
  if (value === 'false') return 'true'
  return `${value}${VALUE_STEP}`
}

test.describe('规则中心 - 配置发布闭环', () => {
  test.setTimeout(120_000)

  test('控制参数取值：改值 → 草稿 → 发布 → 回滚 → 历史', async ({ page, navigateTo }, testInfo) => {
    let ruleKey = null
    let target = null
    let draftPayload = null
    let draftSaved = false
    let published = false
    let rolledBack = false
    let originalValue = ''
    let valueInput = null

    try {
      await withStep(page, testInfo, '打开规则中心并切到控制参数页签', async () => {
        await navigateTo(page, RULE_CENTER_PATH)
        await page.locator(`#tab-${TAB_ID}`).click()

        const pane = page.locator(`#pane-${TAB_ID}`)
        await expect(pane).toBeVisible({ timeout: 15000 })
        const rows = pane.locator('.el-table__body tr')
        await expect(rows.first()).toBeVisible({ timeout: 15000 })
      })

      await withStep(page, testInfo, '打开首条「已有取值行」的配置抽屉', async () => {
        const pane = page.locator(`#pane-${TAB_ID}`)
        const rows = pane.locator('.el-table__body tr')
        const rowCount = Math.min(await rows.count(), 8)

        for (let i = 0; i < rowCount && !ruleKey; i += 1) {
          const row = rows.nth(i)
          const configBtn = row.locator('td button', { hasText: '配置' })
          if ((await configBtn.count()) === 0) continue

          const [historyResp] = await Promise.all([
            page.waitForResponse(
              r => r.url().includes('/api/v2/rules/config/history') && r.request().method() === 'GET',
              { timeout: 15000 }
            ),
            configBtn.first().click()
          ])

          const params = new URL(historyResp.url()).searchParams
          const candidateKey = params.get('rule_key')
          const candidateTarget = params.get('target')

          await expect(page.locator('.config-section')).toBeVisible({ timeout: 10000 })

          // 仅当该参数存在取值行时才能验证「发布后回滚恢复原值」
          const hasValueRows = await page
            .locator('.config-section .el-select')
            .first()
            .waitFor({ state: 'visible', timeout: 5000 })
            .then(() => true)
            .catch(() => false)

          if (hasValueRows) {
            ruleKey = candidateKey
            target = candidateTarget
            break
          }

          // 无取值行：关闭抽屉换下一条
          await page.locator('.el-drawer__close-btn').click().catch(() => {})
          await page.keyboard.press('Escape').catch(() => {})
          await expect(page.locator('.el-drawer').last()).toBeHidden({ timeout: 5000 }).catch(() => {})
        }

        if (!ruleKey) test.skip(true, '当前环境没有「已有取值行」的可配置控制参数，跳过配置闭环验证')
        expect(target).toBe('control_parameter_value')
      })

      await withStep(page, testInfo, '读取原值并改写取值', async () => {
        const valueItem = page
          .locator('.config-section .el-form-item')
          .filter({ has: page.locator('.el-form-item__label', { hasText: /^取值$/ }) })
          .first()
        valueInput = valueItem.locator('.el-input__inner').first()
        await expect(valueInput).toBeVisible({ timeout: 10000 })

        originalValue = (await valueInput.inputValue()).trim()
        await valueInput.fill(nextValue(originalValue))
        await expect(valueInput).not.toHaveValue(originalValue)
      })

      await withStep(page, testInfo, '保存草稿（POST /api/v2/rules）', async () => {
        const saveBtn = page.locator('.config-section button', { hasText: '保存草稿' }).first()
        const [saveReq, saveResp] = await Promise.all([
          page.waitForRequest(
            r => r.method() === 'POST' && new URL(r.url()).pathname === '/api/v2/rules',
            { timeout: 20000 }
          ),
          page.waitForResponse(
            r => r.request().method() === 'POST' && new URL(r.url()).pathname === '/api/v2/rules',
            { timeout: 20000 }
          ),
          saveBtn.click()
        ])

        if (!saveResp.ok()) {
          throw new Error(`保存草稿失败 HTTP ${saveResp.status()}: ${await saveResp.text()}`)
        }
        const body = await saveResp.json()
        expect(body.success).toBeTruthy()
        draftPayload = saveReq.postDataJSON()
        draftSaved = true
      })

      await withStep(page, testInfo, '发布草稿（POST /config/publish）', async () => {
        const publishBtn = page.locator('.audit-toolbar button', { hasText: '发布草稿' }).first()
        await expect(publishBtn).toBeVisible({ timeout: 15000 })

        const [resp] = await Promise.all([
          page.waitForResponse(
            r => r.url().includes('/api/v2/rules/config/publish') && r.request().method() === 'POST',
            { timeout: 20000 }
          ),
          publishBtn.click()
        ])
        if (!resp.ok()) throw new Error(`发布草稿失败 HTTP ${resp.status()}: ${await resp.text()}`)
        expect((await resp.json()).success).toBeTruthy()
        published = true

        await expect(
          page.locator('.audit-log .el-tag').filter({ hasText: '发布' }).first()
        ).toBeVisible({ timeout: 15000 })
      })

      await withStep(page, testInfo, '回滚上一版本（POST /config/rollback）', async () => {
        const rollbackBtn = page.locator('.audit-toolbar button', { hasText: '回滚上一版本' }).first()
        await expect(rollbackBtn).toBeVisible({ timeout: 15000 })

        const [resp] = await Promise.all([
          page.waitForResponse(
            r => r.url().includes('/api/v2/rules/config/rollback') && r.request().method() === 'POST',
            { timeout: 20000 }
          ),
          rollbackBtn.click()
        ])
        if (!resp.ok()) throw new Error(`回滚失败 HTTP ${resp.status()}: ${await resp.text()}`)
        expect((await resp.json()).success).toBeTruthy()
        rolledBack = true

        await expect(
          page.locator('.audit-log .el-tag').filter({ hasText: '回滚' }).first()
        ).toBeVisible({ timeout: 15000 })
        // 回滚后抽屉重载，取值应恢复到变更前
        await expect(valueInput).toHaveValue(originalValue, { timeout: 15000 })
      })

      await attachScreenshot(page, testInfo, 'rule-center-config-flow')
    } finally {
      // 兜底：不留生效值变更 / 不留草稿
      try {
        if (ruleKey) {
          const headers = await getAuthHeaders(page)
          if (published && !rolledBack) {
            await page.request.post('/api/v2/rules/config/rollback', {
              data: { target, payload: { rule_key: ruleKey } },
              headers
            })
          } else if (draftSaved && draftPayload) {
            await page.request.delete(`/api/v2/rules/${encodeURIComponent(ruleKey)}`, {
              data: { payload: draftPayload },
              headers
            })
          }
        }
      } catch (e) {
        console.warn('[rule-center-config-flow] 清理失败:', e.message)
      }
    }
  })
})