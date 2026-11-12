/**
 * MetaReportPage.spec.js - 元数据报表页容器测试
 *
 * 覆盖 P9 核心链路：
 * 1. 配置缺失 / 未声明 report 时的错误提示
 * 2. 配置加载：标题、KPI、筛选字段（value_help 映射）
 * 3. 首屏请求：endpoint 去 /api/v1 前缀、默认筛选值透传
 * 4. 表格分页 + number/date 格式化
 * 5. 筛选值原地合并（reactive 不能用 v-model 赋值）、空值跳过、日期格式化
 * 6. 重置恢复默认值
 * 7. 接口失败错误展示
 * 8. 钻取：group_by 条件、param_map 映射
 * 9. pageConfig.report 覆盖后端配置
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  getViewConfig: vi.fn(),
  apiGet: vi.fn(),
}))

vi.mock('@/services/metaService', () => ({
  default: { getViewConfig: mocks.getViewConfig },
}))

vi.mock('@/utils/httpClient', () => ({
  apiV1: {
    get: mocks.apiGet,
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/components/common/FilterBar/FilterBar.vue', () => ({
  default: {
    name: 'FilterBar',
    props: ['modelValue', 'fields'],
    emits: ['update:model-value', 'search', 'reset'],
    template: `
      <div class="filter-bar-stub">
        <span v-for="field in fields" :key="field.key" class="filter-field">{{ field.key }}</span>
      </div>
    `,
  },
}))

vi.mock('@/components/common/MetaReportPage/ReportBarChart.vue', () => ({
  default: {
    name: 'ReportBarChart',
    props: ['items', 'title', 'categoryField', 'valueField'],
    template: '<div class="chart-stub">{{ title }}|{{ items.length }}</div>',
  },
}))

import MetaReportPage from '../MetaReportPage.vue'

const REPORT_CONFIG = {
  title: '库存库龄',
  description: '按余额行最早入库日分桶',
  endpoint: '/api/v1/inventory-aging/report',
  filters: [
    { key: 'org_id', label: '库存组织', type: 'value_help', target_type: 'org', required: true },
    { key: 'stock_status', label: '库存状态', type: 'select' },
    { key: 'as_of', label: '截止日期', type: 'date' },
    { key: 'group_by', label: '汇总维度', type: 'select', default: 'balance' },
  ],
  kpis: [
    { label: '在手数量', field: 'total_qty', format: 'number' },
    { label: '未分桶数量', field: 'unassigned_qty', format: 'number' },
  ],
  chart: {
    type: 'bar',
    title: '库龄分布',
    data_field: 'summary',
    category_field: 'bucket',
    value_field: 'qty',
  },
  table: {
    data_field: 'rows',
    page_size: 2,
    row_key: ['org_id', 'location_id', 'item_id'],
    columns: [
      { field: 'location_id', label: '库位' },
      { field: 'qty_on_hand', label: '在手数量', format: 'number' },
      { field: 'first_received_date', label: '最早入库日期', format: 'date' },
    ],
  },
  drilldown: {
    endpoint: '/api/v1/inventory-aging/detail',
    title: '库龄明细',
    only_when_group_by: 'balance',
    param_map: { org_id: 'org_id', location_id: 'location_id', as_of: 'as_of' },
  },
}

const REPORT_DATA = {
  total_qty: 1234.5,
  unassigned_qty: 0,
  summary: [
    { bucket: '0-30', qty: 100 },
    { bucket: '31-60', qty: 50 },
  ],
  rows: [
    {
      org_id: 1,
      location_id: 11,
      item_id: 101,
      qty_on_hand: 100,
      first_received_date: '2026-09-01T00:00:00',
      age_bucket: '0-30',
    },
    {
      org_id: 1,
      location_id: 12,
      item_id: 102,
      qty_on_hand: 200,
      first_received_date: '2026-08-15T00:00:00',
      age_bucket: '31-60',
    },
    {
      org_id: 1,
      location_id: 13,
      item_id: 103,
      qty_on_hand: 300,
      first_received_date: '2026-07-01T00:00:00',
      age_bucket: '61-90',
    },
  ],
}

let wrapper = null

async function mountPage(props = {}) {
  wrapper = mount(MetaReportPage, {
    props: { objectType: 'inventory_balance', ...props },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

function filterBar() {
  return wrapper.findComponent({ name: 'FilterBar' })
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.getViewConfig.mockResolvedValue({ success: true, data: { report: REPORT_CONFIG } })
  mocks.apiGet.mockResolvedValue({ success: true, data: REPORT_DATA })
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

describe('MetaReportPage', () => {
  describe('配置加载', () => {
    it('缺少 objectType 时提示错误且不发请求', async () => {
      await mountPage({ objectType: '' })

      expect(wrapper.text()).toContain('报表页缺少 primary_object_type')
      expect(mocks.getViewConfig).not.toHaveBeenCalled()
      expect(mocks.apiGet).not.toHaveBeenCalled()
    })

    it('对象未声明 ui_view_config.report 时提示错误', async () => {
      mocks.getViewConfig.mockResolvedValue({ success: true, data: {} })

      await mountPage()

      expect(wrapper.text()).toContain('对象 inventory_balance 未声明 ui_view_config.report')
      expect(mocks.apiGet).not.toHaveBeenCalled()
    })

    it('渲染标题、描述与 KPI 卡（number 格式化）', async () => {
      await mountPage()

      expect(wrapper.find('.report-title').text()).toBe('库存库龄')
      expect(wrapper.find('.report-description').text()).toBe('按余额行最早入库日分桶')

      const labels = wrapper.findAll('.report-kpi-label').map((item) => item.text())
      expect(labels).toEqual(['在手数量', '未分桶数量'])

      const values = wrapper.findAll('.report-kpi-value').map((item) => item.text())
      expect(values).toEqual(['1,234.5', '0'])
    })

    it('把报表筛选声明映射为 FilterBar 字段（value_help 带 target_bo）', async () => {
      await mountPage()

      const fields = filterBar().props('fields')
      expect(fields.map((field) => field.key)).toEqual(['org_id', 'stock_status', 'as_of', 'group_by'])
      expect(fields[0].valueHelpConfig).toEqual({
        source: { type: 'bo', target_bo: 'org' },
        behavior: {},
        presentation: {},
      })
      expect(fields[1].valueHelpConfig).toBeNull()
    })

    it('pageConfig.report 覆盖后端配置', async () => {
      await mountPage({ pageConfig: { report: { title: '自定义报表' } } })

      expect(wrapper.find('.report-title').text()).toBe('自定义报表')
    })
  })

  describe('首屏请求', () => {
    it('endpoint 去 /api/v1 前缀，默认筛选值参与请求', async () => {
      await mountPage()

      expect(mocks.apiGet).toHaveBeenCalledTimes(1)
      expect(mocks.apiGet).toHaveBeenCalledWith('/inventory-aging/report', {
        params: { group_by: 'balance' },
      })
    })
  })

  describe('表格渲染', () => {
    it('按 page_size 分页并格式化 number / date', async () => {
      await mountPage()

      const rows = wrapper.findAll('.report-table-card .el-table__body-wrapper .el-table__row')
      expect(rows.length).toBe(2)
      expect(rows[0].text()).toContain('100')
      expect(rows[0].text()).toContain('2026-09-01')
      expect(rows[1].text()).toContain('200')
      expect(rows[1].text()).toContain('2026-08-15')
    })

    it('图表使用 summary 作为数据源', async () => {
      await mountPage()

      const chart = wrapper.findComponent({ name: 'ReportBarChart' })
      expect(chart.props('items')).toEqual(REPORT_DATA.summary)
      expect(chart.props('title')).toBe('库龄分布')
    })
  })

  describe('筛选交互', () => {
    it('update:model-value 原地合并，搜索跳过空值并格式化日期', async () => {
      await mountPage()
      mocks.apiGet.mockClear()

      filterBar().vm.$emit('update:model-value', {
        org_id: 1,
        stock_status: '',
        as_of: new Date(2026, 9, 5),
        group_by: 'item',
      })
      await flushPromises()
      filterBar().vm.$emit('search')
      await flushPromises()

      expect(mocks.apiGet).toHaveBeenCalledWith('/inventory-aging/report', {
        params: { org_id: 1, as_of: '2026-10-05', group_by: 'item' },
      })
    })

    it('再次筛选时移除已不存在的键', async () => {
      await mountPage()
      mocks.apiGet.mockClear()

      filterBar().vm.$emit('update:model-value', { org_id: 1 })
      await flushPromises()
      filterBar().vm.$emit('update:model-value', { stock_status: 'available' })
      await flushPromises()
      filterBar().vm.$emit('search')
      await flushPromises()

      const params = mocks.apiGet.mock.calls[0][1].params
      expect(params).toEqual({ stock_status: 'available' })
    })

    it('重置恢复默认值并重新请求', async () => {
      await mountPage()
      filterBar().vm.$emit('update:model-value', { org_id: 9 })
      await flushPromises()
      mocks.apiGet.mockClear()

      filterBar().vm.$emit('reset')
      await flushPromises()

      expect(filterBar().props('modelValue')).toEqual({
        org_id: '',
        stock_status: '',
        as_of: '',
        group_by: 'balance',
      })
      expect(mocks.apiGet).toHaveBeenCalledWith('/inventory-aging/report', {
        params: { group_by: 'balance' },
      })
    })
  })

  describe('错误处理', () => {
    it('接口失败时展示 code + message', async () => {
      mocks.apiGet.mockResolvedValue({
        success: false,
        code: 'INV_AGING_ORG_REQUIRED',
        message: '库存组织必填',
      })

      await mountPage()

      expect(wrapper.find('.report-error').text()).toContain('INV_AGING_ORG_REQUIRED: 库存组织必填')
    })
  })

  describe('钻取', () => {
    it('group_by=balance 时按 param_map 请求明细', async () => {
      await mountPage()

      mocks.apiGet.mockResolvedValue({
        success: true,
        data: {
          as_of: '2026-11-06',
          qty_on_hand: 100,
          reconciled: true,
          layers: [
            { receipt_date: '2026-09-01', layer_qty: 100, remaining_qty: 80, days_in_stock: 66 },
          ],
        },
      })

      const firstRow = wrapper.findAll('.report-table-card .el-table__body-wrapper .el-table__row')[0]
      await firstRow.trigger('click')
      await flushPromises()

      expect(mocks.apiGet).toHaveBeenCalledWith('/inventory-aging/detail', {
        params: { org_id: 1, location_id: 11 },
      })
      expect(document.body.textContent).toContain('已对平')
      expect(document.body.textContent).toContain('2026-09-01')
    })

    it('汇总维度非余额行时不触发明细请求', async () => {
      await mountPage()
      filterBar().vm.$emit('update:model-value', { group_by: 'item' })
      await flushPromises()
      mocks.apiGet.mockClear()

      const firstRow = wrapper.findAll('.report-table-card .el-table__body-wrapper .el-table__row')[0]
      await firstRow.trigger('click')
      await flushPromises()

      expect(mocks.apiGet).not.toHaveBeenCalled()
    })
  })
})
