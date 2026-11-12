/**
 * ReportBarChart.spec.js - 报表柱状图组件测试
 *
 * 覆盖：
 * 1. 挂载时初始化 ECharts 并写入 option（标题 / 分类 / 数值）
 * 2. items 变化时重绘
 * 3. 缺省字段与无标题场景
 * 4. 卸载时释放实例
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  init: vi.fn(),
  setOption: vi.fn(),
  resize: vi.fn(),
  dispose: vi.fn(),
  use: vi.fn(),
}))

vi.mock('echarts/core', () => ({
  init: mocks.init,
  use: mocks.use,
}))

vi.mock('echarts/charts', () => ({ BarChart: {} }))
vi.mock('echarts/components', () => ({
  GridComponent: {},
  TitleComponent: {},
  TooltipComponent: {},
}))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))

import ReportBarChart from '../ReportBarChart.vue'

let wrapper = null

function mountChart(props = {}) {
  wrapper = mount(ReportBarChart, {
    props: {
      items: [
        { bucket: '0-30', qty: 100 },
        { bucket: '31-60', qty: 50 },
      ],
      title: '库龄分布',
      ...props,
    },
    attachTo: document.body,
  })
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.init.mockReturnValue({
    setOption: mocks.setOption,
    resize: mocks.resize,
    dispose: mocks.dispose,
  })
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

describe('ReportBarChart', () => {
  it('挂载时初始化 ECharts 并写入标题、分类与数值', () => {
    mountChart()

    expect(mocks.init).toHaveBeenCalledTimes(1)
    expect(mocks.init.mock.calls[0][0]).toBe(wrapper.element)

    expect(mocks.setOption).toHaveBeenCalledTimes(1)
    const option = mocks.setOption.mock.calls[0][0]
    expect(option.title.text).toBe('库龄分布')
    expect(option.xAxis.data).toEqual(['0-30', '31-60'])
    expect(option.series[0].type).toBe('bar')
    expect(option.series[0].data).toEqual([100, 50])
  })

  it('items 变化时重绘', async () => {
    mountChart()
    mocks.setOption.mockClear()

    await wrapper.setProps({
      items: [{ bucket: '61-90', qty: 7 }],
    })

    expect(mocks.setOption).toHaveBeenCalledTimes(1)
    const option = mocks.setOption.mock.calls[0][0]
    expect(option.xAxis.data).toEqual(['61-90'])
    expect(option.series[0].data).toEqual([7])
  })

  it('无标题时不设置 title 并收紧顶部留白', () => {
    mountChart({ title: '' })

    const option = mocks.setOption.mock.calls[0][0]
    expect(option.title).toBeUndefined()
    expect(option.grid.top).toBe(24)
  })

  it('缺省值按空分类与 0 处理', () => {
    mountChart({
      items: [{}, { bucket: '0-30', qty: null }, { bucket: '31-60', qty: '12' }],
    })

    const option = mocks.setOption.mock.calls[0][0]
    expect(option.xAxis.data).toEqual(['', '0-30', '31-60'])
    expect(option.series[0].data).toEqual([0, 0, 12])
  })

  it('卸载时释放实例', () => {
    mountChart()
    wrapper.unmount()
    wrapper = null

    expect(mocks.dispose).toHaveBeenCalledTimes(1)
  })
})
