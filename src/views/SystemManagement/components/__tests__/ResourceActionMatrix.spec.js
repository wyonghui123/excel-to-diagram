/**
 * ResourceActionMatrix.spec.js - P2-Matrix-01 资源×动作矩阵组件测试
 *
 * 覆盖（Spec 5.4.1 P2-Matrix-01 验收）：
 *   1. 渲染：行 = resources，列 = 动态动作列
 *   2. 灰化禁选：audit_log 行 create/update/delete 列不可勾（A5）
 *   3. 来源标签 4 色 class（auto/include/derived）
 *   4. 勾选 cell → emit change 且 source=include
 *   5. 全选当前筛选 / 清空当前筛选
 *   6. 行全选 / 清空行
 *   7. 列全选（列头 checkbox）
 *   8. 筛选：仅显示已分配 + 资源类型筛选
 *
 * 注意：el-table 在 happy-dom 中列注册是异步的（el-table-column onMounted
 * 后 insertColumn + 重渲染），mount 后需多次 nextTick 才能看到完整 DOM。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import ResourceActionMatrix from '../ResourceActionMatrix.vue'

// 验收样例数据：audit_log 不支持 create/update/delete（A5）
const MOCK_MATRIX = {
  role_id: 1803,
  columns: ['read', 'list', 'create', 'update', 'delete', 'export'],
  resources: [
    {
      resource_type: 'audit_log',
      label: '审计日志',
      cells: {
        read: { granted: true, source: 'auto' },
        list: { granted: true, source: 'include' },
        create: { granted: false, source: '' },
        update: { granted: false, source: '' },
        delete: { granted: false, source: '' },
        export: { granted: true, source: 'auto' },
      },
    },
    {
      resource_type: 'business_object',
      label: '业务对象',
      cells: {
        read: { granted: true, source: 'include' },
        list: { granted: false, source: '' },
        create: { granted: false, source: '' },
        update: { granted: false, source: '' },
        delete: { granted: false, source: '' },
        export: { granted: false, source: '' },
      },
    },
    {
      resource_type: 'domain',
      label: '领域',
      cells: {
        read: { granted: true, source: 'derived' },
        list: { granted: false, source: '' },
        create: { granted: false, source: '' },
        update: { granted: false, source: '' },
        delete: { granted: false, source: '' },
        export: { granted: false, source: '' },
      },
    },
  ],
  sources_detail: [],
}

const MOCK_SUPPORTED = {
  audit_log: ['read', 'list', 'export'],
  business_object: ['read', 'list', 'create', 'update', 'delete', 'export'],
  domain: ['read', 'list', 'create', 'update', 'delete', 'export'],
}

/** 挂载并等待 el-table 列注册完成（多 tick） */
async function mountReady(props = {}) {
  const wrapper = mount(ResourceActionMatrix, {
    props: {
      matrix: MOCK_MATRIX,
      supportedActions: MOCK_SUPPORTED,
      ...props,
    },
    attachTo: document.body,
  })
  for (let i = 0; i < 4; i++) await wrapper.vm.$nextTick()
  return wrapper
}

async function clickButtonByText(wrapper, text) {
  const btn = wrapper.findAll('button').find((b) => b.text().includes(text))
  expect(btn, `未找到按钮: ${text}`).toBeTruthy()
  await btn.trigger('click')
}

describe('ResourceActionMatrix（P2-Matrix-01）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
  })

  it('渲染：行数 = resources，列头 = 动态动作标签', async () => {
    const wrapper = await mountReady()

    // 行：3 个资源（audit_log / business_object / domain）
    expect(wrapper.findAll('.el-table__body-wrapper .el-table__row').length).toBe(3)

    // 列头：read→查看 / create→创建 / export→导出 等
    const headerText = wrapper.find('.el-table__header-wrapper').text()
    expect(headerText).toContain('查看')
    expect(headerText).toContain('创建')
    expect(headerText).toContain('导出')
    expect(headerText).toContain('资源')
    wrapper.unmount()
  })

  it('灰化禁选：audit_log 行 create/update/delete 列显示不支持图标', async () => {
    const wrapper = await mountReady()

    const firstRow = wrapper.findAll('.el-table__body-wrapper .el-table__row')[0]
    expect(firstRow.text()).toContain('审计日志')
    // audit_log 只支持 read/list/export → create/update/delete 3 个灰化单元格
    expect(firstRow.findAll('.ram-cell--unsupported').length).toBe(3)
    // 灰化单元格含 ban 图标（不支持提示）
    expect(firstRow.findAll('.ram-cell--unsupported .app-icon--ban').length).toBe(3)
    wrapper.unmount()
  })

  it('来源标签 4 色：auto / include / derived 渲染对应 class', async () => {
    const wrapper = await mountReady()

    const rows = wrapper.findAll('.el-table__body-wrapper .el-table__row')
    // audit_log 行：read=auto、list=include、export=auto
    expect(rows[0].find('.source-tag--auto').exists()).toBe(true)
    expect(rows[0].find('.source-tag--include').exists()).toBe(true)
    // business_object 行：read=include
    expect(rows[1].find('.source-tag--include').exists()).toBe(true)
    // domain 行：read=derived
    expect(rows[2].find('.source-tag--derived').exists()).toBe(true)
    wrapper.unmount()
  })

  it('勾选 cell → emit change 且 source=include', async () => {
    const wrapper = await mountReady()

    // business_object 行的 list 列（未勾选）点击 checkbox 勾选
    const boRow = wrapper.findAll('.el-table__body-wrapper .el-table__row')[1]
    const checkboxes = boRow.findAll('.ram-cell--clickable .el-checkbox')
    // 列顺序：read, list, create, update, delete, export → list 为第 2 个
    expect(checkboxes.length).toBe(6)
    await checkboxes[1].trigger('click')
    await wrapper.vm.$nextTick()

    const changes = wrapper.emitted('change').at(-1)[0]
    const change = changes.find(
      (c) => c.resource_type === 'business_object' && c.action === 'list',
    )
    expect(change).toEqual({
      resource_type: 'business_object',
      action: 'list',
      granted: true,
      source: 'include',
    })
    wrapper.unmount()
  })

  it('全选当前筛选：所有支持且非 exclude 的 cell 置 include', async () => {
    const wrapper = await mountReady()

    await clickButtonByText(wrapper, '全选当前筛选')
    await wrapper.vm.$nextTick()

    const lastChanges = wrapper.emitted('change').at(-1)[0]
    // business_object（全支持）所有列都应为 include
    const boChanges = lastChanges.filter((c) => c.resource_type === 'business_object')
    expect(boChanges.length).toBe(6)
    expect(boChanges.every((c) => c.granted && c.source === 'include')).toBe(true)
    // audit_log 只支持 3 列：仅 3 条 granted，其余（不支持列）保持 false
    const alChanges = lastChanges.filter((c) => c.resource_type === 'audit_log')
    expect(alChanges.filter((c) => c.granted).length).toBe(3)
    expect(alChanges.every((c) => !c.granted || c.source === 'include')).toBe(true)
    wrapper.unmount()
  })

  it('清空当前筛选：所有可见 cell 置 granted=false', async () => {
    const wrapper = await mountReady()

    await clickButtonByText(wrapper, '清空当前筛选')
    await wrapper.vm.$nextTick()

    const lastChanges = wrapper.emitted('change').at(-1)[0]
    const granted = lastChanges.filter((c) => c.granted)
    expect(granted.length).toBe(0)
    wrapper.unmount()
  })

  it('行全选 / 清空行', async () => {
    const wrapper = await mountReady()

    // business_object 行全选（该行按钮文案为「全选行」）
    const boRow = wrapper.findAll('.el-table__body-wrapper .el-table__row')[1]
    const rowBtn = boRow.findAll('button').find((b) => b.text().includes('全选行'))
    expect(rowBtn, '未找到行全选按钮').toBeTruthy()
    await rowBtn.trigger('click')
    await wrapper.vm.$nextTick()

    let lastChanges = wrapper.emitted('change').at(-1)[0]
    const boGranted = lastChanges.filter(
      (c) => c.resource_type === 'business_object' && c.granted,
    )
    expect(boGranted.length).toBe(6)

    // 再次点击 → 清空行
    const boRow2 = wrapper.findAll('.el-table__body-wrapper .el-table__row')[1]
    const clearBtn = boRow2.findAll('button').find((b) => b.text().includes('清空行'))
    expect(clearBtn, '未找到清空行按钮').toBeTruthy()
    await clearBtn.trigger('click')
    await wrapper.vm.$nextTick()

    lastChanges = wrapper.emitted('change').at(-1)[0]
    const boCleared = lastChanges.filter(
      (c) => c.resource_type === 'business_object' && c.granted,
    )
    expect(boCleared.length).toBe(0)
    wrapper.unmount()
  })

  it('列全选（列头 checkbox）：该列所有支持行置 include', async () => {
    const wrapper = await mountReady()

    // 列头：read / list / create / update / delete / export → create 为第 3 列
    const headerCheckboxes = wrapper.findAll('.el-table__header-wrapper .ram-col-header .el-checkbox')
    expect(headerCheckboxes.length).toBe(6)
    await headerCheckboxes[2].trigger('click') // create 列
    await wrapper.vm.$nextTick()

    const lastChanges = wrapper.emitted('change').at(-1)[0]
    const createChanges = lastChanges.filter((c) => c.action === 'create')
    // 支持 create 的行：business_object / domain（audit_log 不支持）
    const supportedRows = ['business_object', 'domain']
    const unsupportedRow = ['audit_log']
    expect(
      createChanges
        .filter((c) => supportedRows.includes(c.resource_type))
        .every((c) => c.granted && c.source === 'include'),
    ).toBe(true)
    expect(
      createChanges
        .filter((c) => unsupportedRow.includes(c.resource_type))
        .every((c) => !c.granted),
    ).toBe(true)
    wrapper.unmount()
  })

  it('筛选：仅显示已分配 → 只保留有 granted 的行', async () => {
    const wrapper = await mountReady()

    // 勾选「仅显示已分配」checkbox（筛选栏中）
    await wrapper.find('.ram-only-assigned').trigger('click')
    await wrapper.vm.$nextTick()

    // 3 行都有 granted → 全部保留
    expect(wrapper.findAll('.el-table__body-wrapper .el-table__row').length).toBe(3)

    // 清空当前筛选后再过滤 → 无 granted 行 → 0 行
    await clickButtonByText(wrapper, '清空当前筛选')
    await wrapper.vm.$nextTick()
    expect(wrapper.findAll('.el-table__body-wrapper .el-table__row').length).toBe(0)
    wrapper.unmount()
  })

  it('筛选：按资源类型筛选 → 只显示该行', async () => {
    const wrapper = await mountReady()

    // AppSelect（el-select）第一个为资源类型筛选，直接触发 update:modelValue
    const selectWrapper = wrapper.findComponent({ name: 'ElSelect' })
    expect(selectWrapper.exists(), '未找到资源类型筛选 ElSelect').toBe(true)
    selectWrapper.vm.$emit('update:modelValue', 'domain')
    await wrapper.vm.$nextTick()

    const rows = wrapper.findAll('.el-table__body-wrapper .el-table__row')
    expect(rows.length).toBe(1)
    expect(rows[0].text()).toContain('领域')
    wrapper.unmount()
  })
})
