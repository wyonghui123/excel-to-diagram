/**
 * [Spec 19 FR-014] ResourceActionMatrix 类型层树形呈现 组件测试
 *
 * T1 树模式：按 parent 链嵌套（version 挂 product 下 → level-1 行存在，business_object level-5）
 * T2 融合拆行（同 rt 多行）→ 自动回退平铺（无 level-N 行）
 * T3 外部筛选激活 → 自动回退平铺
 * T4 树模式下 toggleColumn 全行生效（rows 平铺真源不变）
 * T5 getRows() 不泄漏树表内部字段 __rowKey
 *
 * [v6 2026-09-06 PM 六次评审·来源列 + 明细直读] 树模式不再合并动作/范围：同 rt 的 N 行 →
 *   节点行（首行带资源名）+ 明细行（资源列留空缩进），每行范围/动作/来源原样直读；
 *   来源信息保留在 row.ps_names（详情悬浮可见），主表不再单独成列；
 *   平铺模式 = 行原样 + 资源列 rowspan 合并。
 * T6 树模式节点行+明细行：各行原样直读，子层级跟在明细行后
 * T7 配置侧浏览态拆行 → 平铺，行集 = 后端行原样
 * T8 同 rt 同 scope 异动作：节点行/明细行各行原样（不再 OR 合并）
 * T9 无层级只读态同口径：平铺行集 = 后端行原样
 * T10 同 rt 拆行父子挂载：SM×2/BO×2 → SM 节点行下挂 [SM 明细行, BO 节点行]
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import ResourceActionMatrix from '../components/ResourceActionMatrix.vue'

vi.mock('@/composables/useMessage', () => ({
  useMessage: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}))

vi.mock('@/services/permissionService', () => ({
  deleteConditionRule: vi.fn().mockResolvedValue({ success: true }),
}))

// 与 /meta 实际下发同构的最小层级（SSOT: hierarchies.yaml biz_hierarchy levels kind=entity）
const HIERARCHY = {
  product: { parent: '', level: 0, kind: 'entity' },
  version: { parent: 'product', level: 1, kind: 'entity' },
  domain: { parent: 'version', level: 2, kind: 'entity' },
  sub_domain: { parent: 'domain', level: 3, kind: 'entity' },
  service_module: { parent: 'sub_domain', level: 4, kind: 'entity' },
  business_object: { parent: 'service_module', level: 5, kind: 'entity' },
}

const CHAIN = ['product', 'version', 'domain', 'sub_domain', 'service_module', 'business_object']

function makeMatrix({ splitVersion = false } = {}) {
  const rts = [...CHAIN, 'org', 'user', 'scheduled_task', 'task_queue', 'task_execution', 'ai_async_task', 'enum_type', 'audit_log']
  const resources = []
  for (const rt of rts) {
    resources.push({
      resource_type: rt,
      label: rt,
      ps_names: [],
      cells: { read: { granted: false, source: '' }, create: { granted: false, source: '' } },
    })
    if (rt === 'version' && splitVersion) {
      resources.push({
        resource_type: rt,
        label: rt,
        ps_names: ['PS-B'],
        cells: { read: { granted: true, source: '' }, create: { granted: false, source: '' } },
      })
    }
  }
  return { columns: ['read', 'create'], resources }
}

// [v2 2026-09-06 PM 评审] 拆行行带独立 row_scope + 来源 PS（预览侧 org_service 透传形态）
function makeMatrixWithScopes() {
  const m = makeMatrix({ splitVersion: true })
  for (const r of m.resources) {
    if (r.resource_type === 'version') {
      if (!r.ps_names.length) r.ps_names = ['PS-A']
      r.row_scope = r.ps_names.includes('PS-B')
        ? { __configured: true, __expression: 'id IN (1)', __expression_display: '仅以下资源：A' }
        : { __configured: true, __expression: 'id = 2', __expression_display: 'id 等于 2' }
    }
  }
  return m
}

function mountMatrix({ matrix, hierarchy = HIERARCHY, externalFilters = [], filterMode = 'allowlist', splitRows = false, readonly = false } = {}) {
  return mount(ResourceActionMatrix, {
    props: {
      matrix: matrix || makeMatrix(),
      resourceHierarchy: hierarchy,
      supportedActions: { [Symbol()]: undefined, ...Object.fromEntries([...CHAIN, 'org', 'user', 'scheduled_task', 'task_queue', 'task_execution', 'ai_async_task', 'enum_type', 'audit_log'].map(rt => [rt, ['read', 'create']])) },
      resourceTypeLabels: {},
      externalResourceFilters: externalFilters,
      externalResourceFilterMode: filterMode,
      treeAllowSplitRows: splitRows,
      readonly,
    },
    global: { stubs: { AppCard: false } },
  })
}

beforeEach(() => {
  document.body.innerHTML = ''
})

describe('ResourceActionMatrix - FR-014 类型层树形呈现', () => {
  it('T1 树模式：子类型按 parent 链嵌套（displayRows 树结构 + el-table level 类）', async () => {
    const wrapper = mountMatrix()
    await nextTick()
    expect(wrapper.vm.treeMode).toBe(true)
    // 结构断言：product → version → domain → sub_domain → service_module → business_object 5 层嵌套
    const roots = wrapper.vm.displayRows
    expect(roots.length).toBe(9) // product + org/user + task 系 4 + enum/audit 2
    const product = roots.find(r => r.resource_type === 'product')
    expect(product?.children?.length).toBe(1)
    const version = product.children[0]
    expect(version.resource_type).toBe('version')
    expect(version.children[0].resource_type).toBe('domain')
    const bo = version.children[0].children[0].children[0].children[0]
    expect(bo.resource_type).toBe('business_object')
    expect(bo.children).toBeUndefined()
    // el-table 已接收树形数据（happy-dom 不渲染 cell 内容，但行级 level 类可证）
    expect(wrapper.findAll('.el-table__row--level-1').length).toBeGreaterThanOrEqual(1)
    expect(wrapper.findAll('.el-table__row--level-5').length).toBe(1)
    wrapper.unmount()
  })

  it('T2 融合拆行（同 rt 两行）→ 自动回退平铺', async () => {
    const wrapper = mountMatrix({ matrix: makeMatrix({ splitVersion: true }) })
    await nextTick()
    expect(wrapper.vm.treeMode).toBe(false)
    // 平铺分页：15 行 → 第 1 页 10 行
    expect(wrapper.vm.displayRows.length).toBe(10)
    expect(wrapper.findAll('.el-table__row--level-1').length).toBe(0)
    wrapper.unmount()
  })

  it('T3 外部筛选激活 → 自动回退平铺', async () => {
    const wrapper = mountMatrix({ externalFilters: ['domain'] })
    await nextTick()
    expect(wrapper.vm.treeMode).toBe(false)
    expect(wrapper.vm.displayRows.length).toBe(1) // allowlist 仅 domain
    expect(wrapper.findAll('.el-table__row--level-1').length).toBe(0)
    wrapper.unmount()
  })

  it('T4 树模式下 toggleColumn 对全部行生效（rows 平铺真源不变）', async () => {
    const wrapper = mountMatrix()
    await nextTick()
    wrapper.vm.toggleColumn('read', true)
    await nextTick()
    const rows = wrapper.vm.getRows()
    const grantedRows = rows.filter(r => r.cells.read?.granted)
    // rows 共 14 行（chain 6 + org/user + task 系 4 + enum/audit 2），全部 read 勾选
    expect(grantedRows.length).toBe(rows.length)
    expect(rows.length).toBe(14)
    wrapper.unmount()
  })

  it('T5 getRows() 不泄漏树表内部字段 __rowKey', async () => {
    const wrapper = mountMatrix()
    await nextTick()
    for (const row of wrapper.vm.getRows()) {
      expect(row).not.toHaveProperty('__rowKey')
    }
    wrapper.unmount()
  })

  it('T6 [v6] 树模式节点行+明细行：同 rt 异 scope → 首行带资源名，其余行留空缩进，各行原样直读', async () => {
    const wrapper = mountMatrix({ matrix: makeMatrixWithScopes(), splitRows: true, readonly: true })
    await nextTick()
    expect(wrapper.vm.treeMode).toBe(true)
    const roots = wrapper.vm.displayRows
    const product = roots.find(r => r.resource_type === 'product')
    // version 两行拆行 → 节点行（首行，在 product.children）+ 明细行（节点行 children 前置）
    const node = product.children.find(r => r.resource_type === 'version')
    expect(node).toBeTruthy()
    const detail = node.children[0]
    expect(detail.resource_type).toBe('version')
    // 节点行 = 后端第 1 行原样（PS-A：read 未授予，范围 id=2），不做 OR 合并
    expect(node.ps_names).toEqual(['PS-A'])
    expect(node.cells.read.granted).toBe(false)
    expect(node.row_scope.__expression).toBe('id = 2')
    expect(node.__variantRow).toBeUndefined()
    // 明细行 = 第 2 行原样（PS-B：read 授予，范围 id IN (1)），资源列留空标记
    expect(detail.__variantRow).toBe(true)
    expect(detail.ps_names).toEqual(['PS-B'])
    expect(detail.cells.read.granted).toBe(true)
    expect(detail.row_scope.__expression).toBe('id IN (1)')
    expect(detail).not.toHaveProperty('row_scope_variants')
    // 子层级挂在节点行 children 末尾（明细行之后）：domain 链仍在 version 下
    const domainNode = node.children.find(r => r.resource_type === 'domain')
    expect(domainNode).toBeTruthy()
    // __rowKey 唯一稳定（沿用原行 key 规则）
    expect(node.__rowKey).not.toBe(detail.__rowKey)
    wrapper.unmount()
  })

  it('T7 [v4] 配置侧浏览态（readonly + 不传 treeAllowSplitRows）拆行回退平铺，行集 = 后端行原样', async () => {
    const wrapper = mountMatrix({ matrix: makeMatrixWithScopes(), readonly: true })
    await nextTick()
    expect(wrapper.vm.treeMode).toBe(false)
    // 平铺展示行 = 后端行原样：version 异 scope → 2 行（前端不做任何二次合并）
    expect(wrapper.vm.displayRows.filter(r => r.resource_type === 'version').length).toBe(2)
    expect(wrapper.findAll('.el-table__row--level-1').length).toBe(0)
    wrapper.unmount()
  })

  it('T8 [v6] 同 rt 同 scope 异动作：节点行/明细行各行原样（不再 OR 合并），来源列独立', async () => {
    const m = makeMatrixWithScopes()
    // 把 PS-B 行范围改为与 PS-A 相同：后端语义下「同范围异动作」= 两行拆行（PS-A: read=false / PS-B: read=true）
    for (const r of m.resources) {
      if (r.resource_type === 'version' && r.ps_names.includes('PS-B')) {
        r.row_scope = { __configured: true, __expression: 'id = 2', __expression_display: 'id 等于 2' }
      }
    }
    const wrapper = mountMatrix({ matrix: m, splitRows: true, readonly: true })
    await nextTick()
    expect(wrapper.vm.treeMode).toBe(true)
    const product = wrapper.vm.displayRows.find(r => r.resource_type === 'product')
    // v5 曾合并为 1 节点（动作 OR）；v6 保持 节点行 + 明细行，各自原样
    const node = product.children.find(r => r.resource_type === 'version')
    expect(node).toBeTruthy()
    const detail = node.children[0]
    expect(detail.resource_type).toBe('version')
    // 各行动作保持各自原值（范围↔动作一一对应，无需交互即直读）
    expect(node.cells.read.granted).toBe(false)
    expect(detail.cells.read.granted).toBe(true)
    // 同 scope 两行各自保留范围条件，ps_names 不跨行合并（来源列各行独立）
    expect(node.row_scope.__expression).toBe('id = 2')
    expect(detail.row_scope.__expression).toBe('id = 2')
    expect(node.ps_names).toEqual(['PS-A'])
    expect(detail.ps_names).toEqual(['PS-B'])
    expect(node).not.toHaveProperty('row_scope_variants')
    wrapper.unmount()
  })

  it('T9 [v4] 无层级只读态同口径（层级一致性）：行集 = 后端行原样，不再前端分组', async () => {
    const scope1 = { __configured: true, __expression: 'org IN (1)', __expression_display: 'org 1' }
    const m = {
      columns: ['read', 'create'],
      resources: [
        { resource_type: 'org', label: 'org', ps_names: ['PS-A'], cells: { read: { granted: true, source: '' }, create: { granted: false, source: '' } }, row_scope: scope1 },
        { resource_type: 'org', label: 'org', ps_names: ['PS-B'], cells: { read: { granted: false, source: '' }, create: { granted: true, source: '' } }, row_scope: scope1 },
        { resource_type: 'user', label: 'user', ps_names: ['PS-A'], cells: { read: { granted: true, source: '' }, create: { granted: false, source: '' } }, row_scope: { __configured: true, __expression: 'u = 1', __expression_display: 'u 1' } },
        { resource_type: 'user', label: 'user', ps_names: ['PS-B'], cells: { read: { granted: false, source: '' }, create: { granted: false, source: '' } }, row_scope: { __configured: true, __expression: 'u = 2', __expression_display: 'u 2' } },
      ],
    }
    // hierarchy = {} → 无层级元数据，treeMode 回退平铺；展示口径必须与树模式一致（后端行原样）
    const wrapper = mountMatrix({ matrix: m, hierarchy: {}, readonly: true, splitRows: true })
    await nextTick()
    expect(wrapper.vm.treeMode).toBe(false)
    const rows = wrapper.vm.displayRows
    // org 两行同 scope 异动作 → 保持 2 行；user 两行异 scope → 2 行；共 4 行（v3 曾合并 org → 3 行）
    expect(rows.length).toBe(4)
    const orgRows = rows.filter(r => r.resource_type === 'org')
    expect(orgRows.length).toBe(2)
    expect(orgRows[0].cells.read.granted).toBe(true)
    expect(orgRows[0].cells.create.granted).toBe(false)
    expect(orgRows[1].cells.read.granted).toBe(false)
    expect(orgRows[1].cells.create.granted).toBe(true)
    expect(orgRows[0].row_scope.__expression).toBe('org IN (1)')
    expect(orgRows[1].row_scope.__expression).toBe('org IN (1)')
    expect(orgRows[0].__rowKey).not.toBe(orgRows[1].__rowKey)
    const userRows = rows.filter(r => r.resource_type === 'user')
    expect(userRows.length).toBe(2)
    expect(userRows[0].row_scope.__expression).toBe('u = 1')
    expect(userRows[1].row_scope.__expression).toBe('u = 2')
    expect(userRows[0].__rowKey).not.toBe(userRows[1].__rowKey)
    wrapper.unmount()
  })

  it('T10 [v6] 同 rt 拆行父子挂载：SM×2/BO×2 → SM 节点行下挂 [SM 明细行, BO 节点行]（不再全挂首个/另一 SM 空置）', async () => {
    const scopeX = { __configured: true, __expression: 'sm IN (1)', __expression_display: 'sm 1' }
    const scopeY = { __configured: true, __expression: 'sm IN (2)', __expression_display: 'sm 2' }
    const m = makeMatrix()
    // 构造用户场景：service_module 两行 + business_object 两行（PM 复现：BO 拆行全挂首个 SM，另一 SM 空置）
    const sm0 = m.resources.find(r => r.resource_type === 'service_module')
    const sm1 = { ...sm0, ps_names: ['PS-B'], row_scope: scopeY }
    sm0.ps_names = ['PS-A']
    sm0.row_scope = scopeX
    m.resources.splice(m.resources.indexOf(sm0) + 1, 0, sm1)
    const bo0 = m.resources.find(r => r.resource_type === 'business_object')
    const bo1 = { ...bo0, ps_names: ['PS-B'], row_scope: scopeY }
    bo0.ps_names = ['PS-A']
    bo0.row_scope = scopeX
    m.resources.splice(m.resources.indexOf(bo0) + 1, 0, bo1)

    const wrapper = mountMatrix({ matrix: m, splitRows: true, readonly: true })
    await nextTick()
    expect(wrapper.vm.treeMode).toBe(true)
    const roots = wrapper.vm.displayRows
    const countRt = (rows, rt) => rows.reduce(
      (n, r) => n + (r.resource_type === rt ? 1 : 0) + (r.children ? countRt(r.children, rt) : 0), 0)
    const findRt = (rows, rt) => {
      for (const r of rows) {
        if (r.resource_type === rt) return r
        const hit = r.children ? findRt(r.children, rt) : null
        if (hit) return hit
      }
      return null
    }
    // 总行数 = 后端行数（不增减）：SM×2 + BO×2
    expect(countRt(roots, 'service_module')).toBe(2)
    expect(countRt(roots, 'business_object')).toBe(2)
    // SM 节点行 children = [SM 明细行, BO 节点行]：层级链路正确、无空置父节点
    const smNode = findRt(roots, 'service_module')
    expect(smNode).toBeTruthy()
    expect(smNode.__variantRow).toBeUndefined()
    expect(smNode.children[0].resource_type).toBe('service_module')
    expect(smNode.children[0].__variantRow).toBe(true)
    const boNode = smNode.children[1]
    expect(boNode.resource_type).toBe('business_object')
    expect(boNode.__variantRow).toBeUndefined()
    // BO 节点行 children = [BO 明细行]
    expect(boNode.children.length).toBe(1)
    expect(boNode.children[0].resource_type).toBe('business_object')
    expect(boNode.children[0].__variantRow).toBe(true)
    // 各行范围/来源原样直读
    expect(smNode.row_scope.__expression).toBe('sm IN (1)')
    expect(smNode.children[0].row_scope.__expression).toBe('sm IN (2)')
    expect(smNode.ps_names).toEqual(['PS-A'])
    expect(smNode.children[0].ps_names).toEqual(['PS-B'])
    wrapper.unmount()
  })
})
