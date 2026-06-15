/**
 * product-list-ui.spec.js - Product 列表 UI 组件测试
 *
 * 目标: 验证前端列表 UI 行为 (行可见/列排序/筛选)
 * 维度: UI 列表展示 + 业务数据可见性
 * 业务价值: 发现"数据已创建但 UI 不显示" / "列定义错" / "筛选缺失"等 bug
 *
 * 范围:
 *   - 创建后 → 列表应可见该行
 *   - 列定义 (编码/名称/版本/可见性) 存在
 *   - 搜索 + 筛选可用
 */
import { test, expect } from '../helpers/auto-fixtures.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'

test.describe('Product 列表 UI 组件测试 (GenericListPage 扩展)', () => {
  test('UI-L01: 创建产品后 → 列表应可见该行', async ({
    page, navigateTo, dataFinder, isolation
  }) => {
    // 1. 创建测试数据 (用 dataFinder 默认)
    const pv = await dataFinder.productWithVersion()
    isolation.createTracked('product', pv.product.id, pv.product.code)

    // 2. 导航到列表
    await navigateTo(page, '/product-management')

    // 3. 验证行可见 (软断言)
    const listPage = new GenericListPage(page, {
      tableSelector: '.el-table, table',
      rowSelector: '.el-table__row, tbody tr',
      linkSelector: 'a, button:has-text("查看")'
    })

    // 一站式: 行可见 + 列存在
    const r = await listPage.verifyListUI(pv.product.code, {
      columns: ['编码', '名称', '版本', '可见性']
    })
    console.log(`  [UI 列表] 行: ${JSON.stringify(r.row)}, 列: ${JSON.stringify(r.columns)}`)
  })

  test('UI-L02: 搜索 → 表格应过滤到该行', async ({
    page, navigateTo, dataFinder, isolation
  }) => {
    const pv = await dataFinder.productWithVersion()
    isolation.createTracked('product', pv.product.id, pv.product.code)

    await navigateTo(page, '/product-management')

    const listPage = new GenericListPage(page)
    // 搜索 + 验证
    await listPage.search(pv.product.code)
    await listPage.expectRowExists(pv.product.code, { timeout: 10000 })
    console.log(`  [UI 搜索] 找到 ${pv.product.code}`)
  })

  test('UI-L03: 列可排序断言 (软)', async ({ page, navigateTo }) => {
    await navigateTo(page, '/product-management')
    const listPage = new GenericListPage(page)
    const r = await listPage.expectColumnSortable('编码')
    console.log(`  [UI 列] 编码 可排序: ${r.sortable}`)
    const r2 = await listPage.expectColumnSortable('名称')
    console.log(`  [UI 列] 名称 可排序: ${r2.sortable}`)
  })

  test('UI-L04: 筛选器存在 (软)', async ({ page, navigateTo }) => {
    await navigateTo(page, '/product-management')
    const listPage = new GenericListPage(page)
    const r1 = await listPage.expectFilterExists('可见性')
    const r2 = await listPage.expectFilterExists('状态')
    console.log(`  [UI 筛选] 可见性: ${r1.exists}, 状态: ${r2.exists}`)
  })
})
