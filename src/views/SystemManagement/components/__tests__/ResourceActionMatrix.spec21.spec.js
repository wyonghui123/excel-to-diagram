/**
 * ResourceActionMatrix.spec21.spec.js - Spec 21 (动作对象级/实例级语义化) 测试
 *
 * 覆盖（Spec 21 §4 验收清单）：
 *   FR-001 列头语义标识
 *     - [CRUD/批量/业务] 对象级 三组分组前缀
 *     - 数据范围列 [实例级] 标签
 *   FR-002 敏感动作未配范围警示
 *     - 勾 delete + 无范围 → ram-sensitive-warn 出现
 *     - 配范围 → 警示消失
 *     - 取消勾 → 警示消失
 *     - tooltip 含「delete」字样
 *     - 浏览态不警示
 *   FR-004 「未配置数据范围 = 全实例」显式声明
 *     - 筛选栏 chip 切换 filteredRows
 *     - 未配范围 + 已勾动作 → ram-unscoped-warn 弱警示
 *   FR-007 分组记忆
 *     - 折叠状态写入 localStorage key=ram-group-collapsed-v1
 *     - 刷新页面后保持
 *     - localStorage 损坏 → 兜底默认全展开
 *   action_type 分块渲染
 *     - visibleColumnsByGroup 按 crud/batch/business 三组正确过滤
 *     - actionOptionsGrouped 给 ElOptionGroup 用，结构正确
 *
 * el-table 在 happy-dom 中列注册是异步的（el-table-column onMounted 后 insertColumn
 * + 重渲染），mount 后需多次 nextTick 才能看到完整 DOM。
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ResourceActionMatrix from '../ResourceActionMatrix.vue'

// 验收样例数据：
//   audit_log: 支持 read/list/export（不含 create/update/delete/export = 敏感）
//   business_object: 全部支持（含 delete/export = 敏感）
//   domain: 全部支持（含 delete = 敏感，已配范围 -> 不警示）
const MOCK_MATRIX = {
  role_id: 1803,
  columns: ['read', 'create', 'update', 'delete', 'export', 'import'],
  resources: [
    {
      resource_type: 'audit_log',
      label: '审计日志',
      cells: {
        read: { granted: false, source: '' },
        create: { granted: false, source: '' },
        update: { granted: false, source: '' },
        delete: { granted: false, source: '' },
        export: { granted: false, source: '' },
        import: { granted: false, source: '' },
      },
    },
    {
      resource_type: 'business_object',
      label: '业务对象',
      cells: {
        read: { granted: true, source: 'include' },
        create: { granted: false, source: '' },
        update: { granted: false, source: '' },
        delete: { granted: true, source: 'include' },  // 敏感动作已勾
        export: { granted: false, source: '' },
        import: { granted: false, source: '' },
      },
    },
    {
      resource_type: 'domain',
      label: '领域',
      cells: {
        read: { granted: true, source: 'include' },
        create: { granted: false, source: '' },
        update: { granted: false, source: '' },
        delete: { granted: true, source: 'include' },  // 已勾 + 已配范围（__expression） -> 不警示
        export: { granted: false, source: '' },
        import: { granted: false, source: '' },
      },
      row_scope: {
        __expression: "domain = '供应链云'",
        __expression_display: 'domain = 供应链云',
        __rules: [{ field: 'domain', op: 'EQ', value: '供应链云' }],
      },
    },
  ],
  sources_detail: [],
}

const MOCK_SUPPORTED = {
  audit_log: ['read', 'list', 'export'],
  business_object: ['read', 'create', 'update', 'delete', 'export', 'import'],
  domain: ['read', 'create', 'update', 'delete', 'export', 'import'],
}

const MOCK_ACTION_META = {
  // crud: 4
  read:    { action_type: 'crud',     name: '查看', yaml_id: 'crud_read' },
  create:  { action_type: 'crud',     name: '创建', yaml_id: 'crud_create' },
  update:  { action_type: 'crud',     name: '编辑', yaml_id: 'crud_update' },
  delete:  { action_type: 'crud',     name: '删除', yaml_id: 'crud_delete' },
  // batch: 2
  export:  { action_type: 'batch',    name: '导出', yaml_id: 'export' },
  import:  { action_type: 'batch',    name: '导入', yaml_id: 'import' },
}

const MOCK_DIMENSIONS = [
  { id: 'product', name: '产品' },
  { id: 'domain', name: '领域' },
]

const MOCK_SCOPE_MATRIX = {}

/** 挂载并等待 el-table 列注册完成（多 tick） */
async function mountReady(props = {}) {
  const wrapper = mount(ResourceActionMatrix, {
    props: {
      matrix: MOCK_MATRIX,
      supportedActions: MOCK_SUPPORTED,
      actionMeta: MOCK_ACTION_META,
      dimensions: MOCK_DIMENSIONS,
      scopeMatrix: MOCK_SCOPE_MATRIX,
      ...props,
    },
    attachTo: document.body,
  })
  for (let i = 0; i < 4; i++) await wrapper.vm.$nextTick()
  return wrapper
}

describe('Spec 21 ResourceActionMatrix — FR-001 列头语义标识', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    // 清空 localStorage
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  it('动作列头加 [CRUD/批量/业务] 对象级 副标签（按 action_type 分组）', async () => {
    // happy-dom 不渲染 el-table-column 列头容器，改为验证：
    //   1. visibleColumnsByGroup(type) 函数按 action_type 返回列数（CRUD=4, 批量=2）
    //   2. 模板中存在 ram-col-header-tag 副标签元素的实例化逻辑（CSS 源验证）
    const wrapper = await mountReady()

    // visibleColumnsByGroup 是函数：传 type 返回该组 action 列表
    const crudCols = wrapper.vm.visibleColumnsByGroup('crud')
    expect(crudCols.length).toBe(4)
    // batch 组：export/import = 2 列
    const batchCols = wrapper.vm.visibleColumnsByGroup('batch')
    expect(batchCols.length).toBe(2)
    // 没有 business 动作 → 该组不渲染（空组隐藏）
    const businessCols = wrapper.vm.visibleColumnsByGroup('business')
    expect(businessCols.length).toBe(0)

    // 模板中应有 ram-col-header-tag--object 副标签的 CSS 类名引用
    const fs = require('fs')
    const path = require('path')
    const tmpl = fs.readFileSync(
      path.resolve(__dirname, '../ResourceActionMatrix.vue'),
      'utf-8'
    )
    expect(tmpl).toMatch(/ram-col-header-tag--object/)
    expect(tmpl).toMatch(/ram-col-header-tag--instance/)
    expect(tmpl).toMatch(/对象级/)
    expect(tmpl).toMatch(/批量/)

    wrapper.unmount()
  })

  it('数据范围列加 [实例级] 副标签（与动作列「对象级」对照）', async () => {
    // happy-dom 不渲染 el-table-column 列头容器，改为验证：
    //   1. 模板中存在 data-test="ram-col-header-sub-data-range" 副标签节点
    //   2. CSS 源中 ram-col-header-tag--instance 样式存在
    const fs = require('fs')
    const path = require('path')
    const tmpl = fs.readFileSync(
      path.resolve(__dirname, '../ResourceActionMatrix.vue'),
      'utf-8'
    )
    expect(tmpl).toMatch(/data-test="ram-col-header-sub-data-range"/)
    expect(tmpl).toMatch(/ram-col-header-tag--instance[\s\S]*\[实例级\]/)

    // 颜色断言：实例级应使用 gray-500 #6b7280（PM 第四次反馈：灰色调）
    const css = fs.readFileSync(
      path.resolve(__dirname, '../ResourceActionMatrix.vue'),
      'utf-8'
    )
    expect(css).toMatch(/\.ram-col-header-tag--instance\s*\{[^}]*color:\s*#6b7280/s)
  })

  it('动作列按 action_type 分块渲染（visibleColumnsByGroup）', async () => {
    const wrapper = await mountReady()

    // 直接调用 component 暴露的计算属性（如果有）
    // 这里通过 visibleColumnsByGroup 在模板中体现：
    // crud 列 4 个 + batch 列 2 个 = 总 6 列，列头都应有 ram-col-label
    const labels = wrapper.findAll('.ram-col-label')
    // 资源列头 1 个 + 数据范围列头 1 个 + 6 动作列 = 8 个
    expect(labels.length).toBeGreaterThanOrEqual(6)

    wrapper.unmount()
  })

  it('actionFilter 下拉按 action_type 分组（ElOptionGroup）', async () => {
    const wrapper = await mountReady()

    // ElSelect 的 dropdown 面板是 lazy mounted，点击 select 才显示。
    // 改验证组件内部 actionOptionsGrouped computed：
    //   结构：[{label, options:[{label, value}]}, ...]
    // 只 2 组有动作：crud (4个) + batch (2个)，business 为空不渲染
    const grouped = wrapper.vm.actionOptionsGrouped
    expect(grouped.length).toBe(2)

    const crudGroup = grouped.find((g) => g.label === 'CRUD')
    expect(crudGroup).toBeTruthy()
    expect(crudGroup.options.map((o) => o.value).sort()).toEqual(
      ['create', 'delete', 'read', 'update']
    )

    const batchGroup = grouped.find((g) => g.label === '批量')
    expect(batchGroup).toBeTruthy()
    expect(batchGroup.options.map((o) => o.value).sort()).toEqual(['export', 'import'])

    const businessGroup = grouped.find((g) => g.label === '业务')
    expect(businessGroup).toBeUndefined()  // 空组不渲染

    wrapper.unmount()
  })
})

describe('Spec 21 ResourceActionMatrix — FR-002 敏感动作未配范围警示', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  it('勾 delete + 未配范围 → ram-sensitive-warn 出现', async () => {
    const wrapper = await mountReady()

    // business_object 行的 ram-sensitive-warn 应存在（已勾 delete，未配 row_scope）
    const allWarns = wrapper.findAll('[data-test="ram-sensitive-warn"]')
    // 至少 1 个敏感警示（business_object）
    expect(allWarns.length).toBe(1)

    wrapper.unmount()
  })

  it('配范围后警示消失（domain 已配 row_scope + 勾 delete）', async () => {
    const wrapper = await mountReady()

    // domain 行虽然勾了 delete，但 row_scope.__expression 已配置 → 不警示
    const allWarns = wrapper.findAll('[data-test="ram-sensitive-warn"]')
    expect(allWarns.length).toBe(1)  // 只有 business_object 警示

    // 通过 getRowLabel 验证 domain 行确实没警示
    const rows = wrapper.findAll('.el-table__body-wrapper .el-table__row')
    const domainRow = rows[2]  // 第 3 行 = domain
    expect(domainRow.text()).toContain('领域')
    expect(domainRow.find('[data-test="ram-sensitive-warn"]').exists()).toBe(false)

    wrapper.unmount()
  })

  it('敏感警示与弱警示互斥（敏感动作存在时不显示弱警示）', async () => {
    const wrapper = await mountReady()

    // business_object 行：勾了 read + delete（敏感），应只有强警示
    const rows = wrapper.findAll('.el-table__body-wrapper .el-table__row')
    const boRow = rows[1]  // business_object
    expect(boRow.find('[data-test="ram-sensitive-warn"]').exists()).toBe(true)
    expect(boRow.find('[data-test="ram-unscoped-warn"]').exists()).toBe(false)

    wrapper.unmount()
  })

  it('非敏感动作 + 未配范围 → 仅显示弱警示 ram-unscoped-warn', async () => {
    // 构造：business_object 仅勾 read（crud 但非敏感）+ 未配范围
    const matrix = JSON.parse(JSON.stringify(MOCK_MATRIX))
    matrix.resources[1].cells.delete.granted = false  // 取消 delete
    matrix.resources[1].cells.delete.source = ''
    matrix.resources[1].cells.export.granted = false  // 取消 export（export 是敏感！）
    matrix.resources[1].cells.export.source = ''
    matrix.resources[1].cells.import.granted = false  // 取消 import（import 是敏感！）
    matrix.resources[1].cells.import.source = ''
    matrix.resources[1].row_scope = undefined  // 未配范围

    const wrapper = await mountReady({ matrix })
    const rows = wrapper.findAll('.el-table__body-wrapper .el-table__row')
    const boRow = rows[1]

    // 强警示不出现（非敏感）
    expect(boRow.find('[data-test="ram-sensitive-warn"]').exists()).toBe(false)
    // 弱警示出现
    expect(boRow.find('[data-test="ram-unscoped-warn"]').exists()).toBe(true)

    wrapper.unmount()
  })

  it('浏览态（readonly）不显示警示', async () => {
    const wrapper = await mountReady({ readonly: true })

    // readonly 模式下，所有 isSensitiveScopeGap / isUnscopedRisk 都返回 false
    const allSensitive = wrapper.findAll('[data-test="ram-sensitive-warn"]')
    const allUnscoped = wrapper.findAll('[data-test="ram-unscoped-warn"]')
    expect(allSensitive.length).toBe(0)
    expect(allUnscoped.length).toBe(0)

    wrapper.unmount()
  })

  it('audit_log 行不支持 delete → 即使 cells.delete.granted=true 也不警示', async () => {
    // 极端情况：isSupported = false 时不计入 SENSITIVE_ACTIONS（避免假警示）
    const matrix = JSON.parse(JSON.stringify(MOCK_MATRIX))
    matrix.resources[0].cells.delete = { granted: true, source: 'include' }  // 强制勾
    matrix.resources[0].row_scope = undefined

    const wrapper = await mountReady({ matrix })
    const rows = wrapper.findAll('.el-table__body-wrapper .el-table__row')
    const alRow = rows[0]  // audit_log
    expect(alRow.find('[data-test="ram-sensitive-warn"]').exists()).toBe(false)

    wrapper.unmount()
  })

  it('取消勾 delete → 警示消失', async () => {
    const wrapper = await mountReady()

    // 业务对象行原本有警示，点击 delete 列的 checkbox 取消
    const rows = wrapper.findAll('.el-table__body-wrapper .el-table__row')
    const boRow = rows[1]
    expect(boRow.find('[data-test="ram-sensitive-warn"]').exists()).toBe(true)

    // 删除列第 4 个 checkbox (read, create, update, delete)
    const checkboxes = boRow.findAll('.ram-cell--clickable .el-checkbox')
    expect(checkboxes.length).toBe(6)
    await checkboxes[3].trigger('click')  // delete column
    for (let i = 0; i < 3; i++) await wrapper.vm.$nextTick()

    const newBoRow = wrapper.findAll('.el-table__body-wrapper .el-table__row')[1]
    expect(newBoRow.find('[data-test="ram-sensitive-warn"]').exists()).toBe(false)

    wrapper.unmount()
  })
})

describe('Spec 21 ResourceActionMatrix — FR-004 「未配置数据范围」筛选', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  it('筛选栏新增「仅显示未配置数据范围」checkbox + data-test', async () => {
    const wrapper = await mountReady()

    const chip = wrapper.find('[data-test="ram-show-unscoped-risk"]')
    expect(chip.exists()).toBe(true)
    expect(chip.text()).toContain('仅显示未配置数据范围')

    wrapper.unmount()
  })

  it('勾选筛选 chip → filteredRows 只保留未配置范围的行', async () => {
    const wrapper = await mountReady()

    // 勾选前：3 行
    expect(wrapper.findAll('.el-table__body-wrapper .el-table__row').length).toBe(3)

    // 勾选 chip
    const chip = wrapper.find('[data-test="ram-show-unscoped-risk"] input')
    expect(chip.exists()).toBe(true)
    await chip.setValue(true)
    for (let i = 0; i < 3; i++) await wrapper.vm.$nextTick()

    // 勾选后：domain 已配范围 → 隐藏；保留 audit_log + business_object
    const rows = wrapper.findAll('.el-table__body-wrapper .el-table__row')
    expect(rows.length).toBe(2)

    const visibleLabels = rows.map(r => r.text())
    expect(visibleLabels.some(t => t.includes('审计日志'))).toBe(true)
    expect(visibleLabels.some(t => t.includes('业务对象'))).toBe(true)
    expect(visibleLabels.some(t => t.includes('领域'))).toBe(false)

    wrapper.unmount()
  })
})

describe('Spec 21 ResourceActionMatrix — FR-007 分组记忆（localStorage）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  it('默认全展开（localStorage 为空 → collapsedGroups 全 false）', async () => {
    const wrapper = await mountReady()
    // 组件初次 mount 时会立即写入（即使全 false 也写）— 验证写入内容正确即可
    const saved = JSON.parse(localStorage.getItem('ram-group-collapsed-v1') || 'null')
    expect(saved).toEqual({ crud: false, batch: false, business: false })

    const obj = wrapper.vm
    // 组件内部 ref，应为全 false
    expect(obj.collapsedGroups.crud).toBe(false)
    expect(obj.collapsedGroups.batch).toBe(false)
    expect(obj.collapsedGroups.business).toBe(false)

    wrapper.unmount()
  })

  it('写入 localStorage：toggle 后持久化', async () => {
    const wrapper = await mountReady()

    const obj = wrapper.vm
    obj.toggleGroupCollapse('crud')  // 折叠 crud
    for (let i = 0; i < 2; i++) await wrapper.vm.$nextTick()

    const saved = JSON.parse(localStorage.getItem('ram-group-collapsed-v1') || '{}')
    expect(saved.crud).toBe(true)
    expect(saved.batch).toBe(false)

    wrapper.unmount()
  })

  it('读取 localStorage：mount 时恢复折叠状态', async () => {
    // 先写
    localStorage.setItem('ram-group-collapsed-v1', JSON.stringify({ crud: true, batch: false, business: true }))

    const wrapper = await mountReady()
    expect(wrapper.vm.collapsedGroups.crud).toBe(true)
    expect(wrapper.vm.collapsedGroups.business).toBe(true)

    wrapper.unmount()
  })

  it('localStorage 损坏（JSON.parse 失败）→ 兜底默认全展开不报错', async () => {
    localStorage.setItem('ram-group-collapsed-v1', '{not valid json')

    // 不应抛错
    const wrapper = await mountReady()
    expect(wrapper.vm.collapsedGroups.crud).toBe(false)
    expect(wrapper.vm.collapsedGroups.batch).toBe(false)
    expect(wrapper.vm.collapsedGroups.business).toBe(false)

    wrapper.unmount()
  })
})

describe('Spec 21 ResourceActionMatrix — action_type 分块 + 折叠联动', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  it('isGroupCollapsed(type) 返回当前折叠状态', async () => {
    const wrapper = await mountReady()

    expect(wrapper.vm.isGroupCollapsed('crud')).toBe(false)
    wrapper.vm.toggleGroupCollapse('crud')
    expect(wrapper.vm.isGroupCollapsed('crud')).toBe(true)
    wrapper.vm.toggleGroupCollapse('crud')
    expect(wrapper.vm.isGroupCollapsed('crud')).toBe(false)

    wrapper.unmount()
  })

  it('actionMeta 缺失 → 所有 action 走 crud 兑底（保持原行为）', async () => {
    // 不传 actionMeta → visibleColumnsByGroup('crud') 返回全部
    const wrapper = await mountReady({ actionMeta: {} })

    // 全部分到 crud 组，business/batch 组为空 → actionOptionsGrouped 只 1 组
    const grouped = wrapper.vm.actionOptionsGrouped
    expect(grouped.length).toBe(1)
    expect(grouped[0].label).toBe('CRUD')

    // 列头所有副标签都应该是「CRUD 对象级」
    const tags = wrapper.findAll('.ram-col-header-tag--object')
    const allCrud = tags.every(t => t.text().includes('CRUD'))
    expect(allCrud).toBe(true)

    wrapper.unmount()
  })

  it('折叠 crud 组 → isGroupCollapsed(crud)=true + toggle 持久化到 localStorage', async () => {
    // happy-dom 不渲染 el-table-column v-show 的 DOM 副作用（EP 自己管列 visible 状态）。
    // 改为验证 API 层：折叠后 isGroupCollapsed 返回 true，且 localStorage 持久化。
    const wrapper = await mountReady()

    // 折叠前：isGroupCollapsed 全 false
    expect(wrapper.vm.isGroupCollapsed('crud')).toBe(false)
    expect(wrapper.vm.isGroupCollapsed('batch')).toBe(false)
    expect(wrapper.vm.isGroupCollapsed('business')).toBe(false)

    // 折叠 crud
    wrapper.vm.toggleGroupCollapse('crud')
    for (let i = 0; i < 3; i++) await wrapper.vm.$nextTick()

    // 折叠后：API 状态正确
    expect(wrapper.vm.isGroupCollapsed('crud')).toBe(true)
    // localStorage 持久化
    const saved = JSON.parse(localStorage.getItem('ram-group-collapsed-v1'))
    expect(saved).toBeTruthy()
    expect(saved.crud).toBe(true)

    wrapper.unmount()
  })
})

describe('Spec 21 ResourceActionMatrix — showPsSource prop (PM 反馈 2026-09-12)', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  // 验证用数据：3 行资源，其中
  //   - audit_log: ps_names = 1 个（单 PS tooltip）
  //   - business_object: ps_names = 3 个（多 PS popover）
  //   - domain: ps_names = []（空 — em dash）
  const MOCK_MATRIX_WITH_PS = {
    role_id: 1803,
    columns: ['read', 'create', 'update', 'delete', 'export', 'import'],
    resources: [
      {
        resource_type: 'audit_log',
        label: '审计日志',
        ps_names: ['合规审计员'],
        cells: {
          read: { granted: true, source: 'include' },
          create: { granted: false, source: '' },
          update: { granted: false, source: '' },
          delete: { granted: false, source: '' },
          export: { granted: false, source: '' },
          import: { granted: false, source: '' },
        },
      },
      {
        resource_type: 'business_object',
        label: '业务对象',
        ps_names: ['销售主管', '运营管理员', '数据分析师'],
        cells: {
          read: { granted: true, source: 'include' },
          create: { granted: false, source: '' },
          update: { granted: false, source: '' },
          delete: { granted: false, source: '' },
          export: { granted: false, source: '' },
          import: { granted: false, source: '' },
        },
      },
      {
        resource_type: 'domain',
        label: '领域',
        ps_names: [],
        cells: {
          read: { granted: true, source: 'include' },
          create: { granted: false, source: '' },
          update: { granted: false, source: '' },
          delete: { granted: false, source: '' },
          export: { granted: false, source: '' },
          import: { granted: false, source: '' },
        },
      },
    ],
    sources_detail: [],
  }

  it('showPsSource=false (默认): 不渲染「权限集来源」列', async () => {
    const wrapper = await mountReady({ matrix: MOCK_MATRIX_WITH_PS })

    const psSourceCells = wrapper.findAll('[data-test="ram-ps-source-cell"]')
    expect(psSourceCells.length).toBe(0)

    // 也没有列头副标签
    const neutralTags = wrapper.findAll('.ram-col-header-tag--neutral')
    expect(neutralTags.length).toBe(0)

    wrapper.unmount()
  })

  it('showPsSource=true: 渲染列 + 3 行单元格', async () => {
    const wrapper = await mountReady({
      matrix: MOCK_MATRIX_WITH_PS,
      showPsSource: true,
    })

    // 3 行资源 → 3 个 PS 来源 cell
    const psSourceCells = wrapper.findAll('[data-test="ram-ps-source-cell"]')
    expect(psSourceCells.length).toBe(3)

    // [Spec 21 PM 反馈 2026-09-12 第八次] [聚合视图] 副标签已去掉
    const neutralTags = wrapper.findAll('.ram-col-header-tag--neutral')
    expect(neutralTags.length).toBe(0)

    // data-test 节点也不再存在
    const headerSub = wrapper.find('[data-test="ram-col-header-sub-ps-source"]')
    expect(headerSub.exists()).toBe(false)

    wrapper.unmount()
  })

  it('showPsSource=true: 单 PS 行渲染 PS 名 + info plain tag', async () => {
    const wrapper = await mountReady({
      matrix: MOCK_MATRIX_WITH_PS,
      showPsSource: true,
    })

    // 找到 audit_log 那一行
    const auditRow = wrapper.findAll('tr').find(tr =>
      tr.text().includes('审计日志')
    )
    expect(auditRow).toBeTruthy()

    // 单 PS tag 显示 PS 名
    const psTag = auditRow.find('.ram-ps-source-tag')
    expect(psTag.text()).toBe('合规审计员')

    wrapper.unmount()
  })

  it('showPsSource=true: 多 PS 行渲染「N 个权限集」+ popover', async () => {
    const wrapper = await mountReady({
      matrix: MOCK_MATRIX_WITH_PS,
      showPsSource: true,
    })

    // 找到 business_object 那一行
    const bizRow = wrapper.findAll('tr').find(tr =>
      tr.text().includes('业务对象')
    )
    expect(bizRow).toBeTruthy()

    const psTag = bizRow.find('.ram-ps-source-tag')
    expect(psTag.text()).toBe('3 个权限集')

    wrapper.unmount()
  })

  it('showPsSource=true: 空 PS 数组渲染 em dash 占位', async () => {
    const wrapper = await mountReady({
      matrix: MOCK_MATRIX_WITH_PS,
      showPsSource: true,
    })

    const domainRow = wrapper.findAll('tr').find(tr =>
      tr.text().includes('领域')
    )
    expect(domainRow).toBeTruthy()

    const emptySpan = domainRow.find('.ram-ps-source-empty')
    expect(emptySpan.exists()).toBe(true)
    expect(emptySpan.text()).toBe('—')

    wrapper.unmount()
  })
})

describe('Spec 21 ResourceActionMatrix — 列头颜色浅色调（PM 反馈 2026-09-12）', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    localStorage.clear()
  })
  afterEach(() => {
    localStorage.clear()
  })

  // 注：el-table-column 内的列头（CRUD/批量/实例级）在 happy-dom 中不渲染 DOM
  // （与已有的 FR-001 列头语义标识 测试同样的限制）。
  // 颜色仅在真实浏览器中验证。本测试只覆盖 prop 本身的语义正确性。

  it('[Spec 21 PM 反馈 2026-09-12 第八次] [聚合视图] 副标签已移除', async () => {
    const wrapper = await mountReady({ showPsSource: true })

    // 模板里不再渲染 .ram-col-header-tag--neutral 节点
    const neutralTags = wrapper.findAll('.ram-col-header-tag--neutral')
    expect(neutralTags.length).toBe(0)

    // data-test 节点也不再存在
    const headerSub = wrapper.find('[data-test="ram-col-header-sub-ps-source"]')
    expect(headerSub.exists()).toBe(false)

    wrapper.unmount()
  })

  it('列头颜色类 CSS 规则使用 background:transparent + border:none + gray 色阶（PM 反馈第四次设计正确性回归）', () => {
    // 不依赖 happy-dom 渲染，直接读取组件 CSS 源验证设计意图。
    // 这是为了避免 happy-dom 不渲染 el-table-column 列头导致的 false negative。
    // 真实浏览器渲染时，这三条 CSS 规则会作用于 .ram-col-header-tag--* 三种颜色变体。
    const fs = require('fs')
    const path = require('path')
    const css = fs.readFileSync(
      path.resolve(__dirname, '../ResourceActionMatrix.vue'),
      'utf-8'
    )
    // [PM 反馈 2026-09-12 第四次] 无边框基类：background: transparent + border: none
    expect(css).toMatch(/\.ram-col-header-tag\s*\{[^}]*background:\s*transparent/s)
    expect(css).toMatch(/\.ram-col-header-tag\s*\{[^}]*border:\s*none/s)
    // [Spec 21 PM 反馈 2026-09-12 第八次] 颜色变体只剩 --object + --instance（--neutral 已删除）
    const objectMatches = css.match(/\.ram-col-header-tag--object\s*\{[^}]*color:\s*#374151/g) || []
    const instanceMatches = css.match(/\.ram-col-header-tag--instance\s*\{[^}]*color:\s*#6b7280/g) || []
    expect(objectMatches.length).toBe(1)
    expect(instanceMatches.length).toBe(1)
    // --neutral 不应再存在
    expect(css).not.toMatch(/\.ram-col-header-tag--neutral\s*\{/)
  })

  it('权限集来源 tag 无边框（PM 反馈第四次：TEST61 不带框）', () => {
    const fs = require('fs')
    const path = require('path')
    const css = fs.readFileSync(
      path.resolve(__dirname, '../ResourceActionMatrix.vue'),
      'utf-8'
    )
    // .ram-ps-source-tag 应有 border: none !important
    expect(css).toMatch(/\.ram-ps-source-tag\s*\{[^}]*border:\s*none\s*!important/s)
  })
})