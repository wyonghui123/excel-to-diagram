/**
 * EnumTag.spec.js - 枚举标签组件测试（T13-4）
 *
 * 覆盖：label/color 正确 / 未知值显示原值 / 0 与 false 不被当空 /
 *       枚举缓存命中不重复请求 / 未知 color 回退 info。
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('@/services/metaEnumService', () => ({
  getEnum: vi.fn()
}))

import { getEnum } from '@/services/metaEnumService'
import EnumTag from '@/components/meta/EnumTag.vue'
import { _resetEnumMetaCache } from '@/composables/useEnumMeta'

describe('EnumTag', () => {
  beforeEach(() => {
    _resetEnumMetaCache()
    getEnum.mockReset()
  })

  it('按枚举项渲染 label 与 color 对应的 tag type', async () => {
    getEnum.mockResolvedValue([
      { value: 'active', label: '启用', color: 'success' },
      { value: 'blocked', label: '停用', color: 'danger' }
    ])

    const wrapper = mount(EnumTag, {
      props: { enumName: 'task_status', value: 'active' }
    })
    await flushPromises()

    expect(getEnum).toHaveBeenCalledWith('task_status')
    expect(wrapper.text()).toBe('启用')
    expect(wrapper.find('.el-tag').classes()).toContain('el-tag--success')

    await wrapper.setProps({ value: 'blocked' })
    expect(wrapper.text()).toBe('停用')
    expect(wrapper.find('.el-tag').classes()).toContain('el-tag--danger')
  })

  it('未知值渲染原值 + info 色', async () => {
    getEnum.mockResolvedValue([{ value: 'active', label: '启用', color: 'success' }])

    const wrapper = mount(EnumTag, {
      props: { enumName: 'task_status', value: 'ghost' }
    })
    await flushPromises()

    expect(wrapper.find('.el-tag').exists()).toBe(false)
    expect(wrapper.find('.enum-tag--unknown').text()).toBe('ghost')
  })

  it('0 / false 能命中枚举项，不被当空', async () => {
    getEnum.mockResolvedValue([
      { value: 0, label: '零', color: 'info' },
      { value: false, label: '否', color: 'warning' }
    ])

    const zero = mount(EnumTag, { props: { enumName: 'flag_enum', value: 0 } })
    const boolFalse = mount(EnumTag, { props: { enumName: 'flag_enum', value: false } })
    await flushPromises()

    expect(zero.text()).toBe('零')
    expect(boolFalse.text()).toBe('否')
  })

  it('0 / false 未知时显示原值而非 "-"', async () => {
    getEnum.mockResolvedValue([])

    const zero = mount(EnumTag, { props: { enumName: 'empty_enum', value: 0 } })
    const boolFalse = mount(EnumTag, { props: { enumName: 'empty_enum', value: false } })
    await flushPromises()

    expect(zero.find('.enum-tag--unknown').text()).toBe('0')
    expect(boolFalse.find('.enum-tag--unknown').text()).toBe('false')
  })

  it('缺省 color 回退 info', async () => {
    getEnum.mockResolvedValue([{ value: 'draft', label: '草稿' }])

    const wrapper = mount(EnumTag, {
      props: { enumName: 'doc_status', value: 'draft' }
    })
    await flushPromises()

    expect(wrapper.find('.el-tag').classes()).toContain('el-tag--info')
  })

  it('缓存命中不重复请求枚举', async () => {
    getEnum.mockResolvedValue([{ value: 'active', label: '启用', color: 'success' }])

    const first = mount(EnumTag, { props: { enumName: 'task_status', value: 'active' } })
    await flushPromises()
    const second = mount(EnumTag, { props: { enumName: 'task_status', value: 'active' } })
    await flushPromises()

    expect(first.text()).toBe('启用')
    expect(second.text()).toBe('启用')
    expect(getEnum).toHaveBeenCalledTimes(1)
  })
})