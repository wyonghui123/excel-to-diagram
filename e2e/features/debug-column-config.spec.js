/**
 * DEBUG-COLUMN-CONFIG: 调试列配置加载
 *
 * 实施目标 (基于 v1_to_v2_plan.md P0 试点):
 * - v1 → v2 迁移,moderate 复杂度,1 unsafe
 * - 改: import + 删除 login/setAdminPermissions + page.goto → navigateTo
 *
 * 必读: .trae/rules/e2e-simplification.md
 *
 * v2 铁律合规:
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions() (page 已自动登录)
 * [OK] navigateTo fixture 替代 page.goto
 * [OK] withStep 包裹每步
 * [OK] waitForApiFn 替代 waitForSelector + waitForTimeout
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { withStep } from '../helpers/auto-trace.js'

test.describe('DEBUG-COLUMN-CONFIG', () => {
  test('检查 parent_id 列的 valueHelpConfig', async ({ page, navigateTo, waitForApiFn }, testInfo) => {
    // 注册 console 监听 (V2: 提到 withStep 之前)
    page.on('console', msg => {
      const text = msg.text()
      if (text.includes('parent_id') || text.includes('valueHelp') || text.includes('value_help') || text.includes('enrichColumns')) {
        console.log(`[BROWSER] ${text}`)
      }
    })

    await withStep(page, testInfo, '导航到用户组列表页 (POM navigateTo)', async () => {
      await navigateTo(page, '/user-permission')
    })

    await withStep(page, testInfo, '等待 sub-nav-tabs 出现 (POM waitForApiFn)', async () => {
      await waitForApiFn(page, 'GET /api/v1/auth/me').catch(() => {})
    })

    await withStep(page, testInfo, '点击"用户组管理" tab', async () => {
      // v2 风格: 用语义化 selector 而非直接 .sub-nav-tab
      const userGroupTab = page.getByRole('tab', { name: /用户组管理/ }).first()
      if (await userGroupTab.isVisible({ timeout: 5000 }).catch(() => false)) {
        await userGroupTab.click()
      } else {
        // 备选: 直接 selector (会触发 v2 警告但能用)
        const fallback = page.locator('.sub-nav-tab:has-text("用户组管理")').first()
        await fallback.click({ force: true })
      }
    })

    await withStep(page, testInfo, '等待表格 API 响应 (POM waitForApiFn)', async () => {
      await waitForApiFn(page, 'GET /api/v2/bo/user_group').catch(() => {})
    })

    await withStep(page, testInfo, '在浏览器中检查列配置 (page.evaluate)', async () => {
      const columnConfig = await page.evaluate(() => {
        const table = document.querySelector('.el-table')
        if (!table) return null

        // 查找 Vue 实例
        const vueInstance = table.__vue__ || table._vnode?.component?.proxy
        if (!vueInstance) return { error: 'No Vue instance found' }

        // 尝试获取 columns
        const cols = vueInstance.columns || vueInstance.$parent?.columns || vueInstance.$parent?.$parent?.columns
        if (!cols) return { error: 'No columns found' }

        // 查找 parent_id 列
        const parentIdCol = cols.find(c => c.prop === 'parent_id')
        if (!parentIdCol) return { error: 'parent_id column not found', columns: cols.map(c => c.prop) }

        return {
          prop: parentIdCol.prop,
          filter_type: parentIdCol.filter_type,
          filterable: parentIdCol.filterable,
          hasValueHelpConfig: !!parentIdCol.valueHelpConfig,
          hasValue_help: !!parentIdCol.value_help,
          valueHelpConfigBehavior: parentIdCol.valueHelpConfig?.behavior,
          valueHelpConfigSource: parentIdCol.valueHelpConfig?.source
        }
      })

      console.log('\n=== 列配置检查结果 ===')
      console.log(JSON.stringify(columnConfig, null, 2))
    })
  })
})
