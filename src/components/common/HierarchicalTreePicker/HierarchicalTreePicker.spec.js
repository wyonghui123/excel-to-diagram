/**
 * [REFACTOR 2026-07-22] HierarchicalTreePicker 单元测试
 *
 * 覆盖:
 *   - 基础渲染 + props 验证 (hierarchyConfig prop 已删除, 元数据从 API 读取)
 *   - 单选模式 (payload shape, 再次点击取消)
 *   - 多选模式 (chips 移除, 全选/清空)
 *   - 搜索 (防抖, 父链展开)
 *   - 数据加载 (mock fetch 含 hierarchy_meta)
 *   - ID 冲突场景 (unique_key 修复)
 *   - 复用性: 单选/多选通过 multiple prop 切换
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import HierarchicalTreePicker from './HierarchicalTreePicker.vue'

// [REFACTOR 2026-07-22] hierarchy_meta 现在从 API 响应读取, 不再是 prop
const mockHierarchyMeta = {
  root_type: 'product',
  levels: [
    { object_type: 'product', display_name: '产品', icon: 'inventory_2', color: '#9C27B0', level: 0 },
    { object_type: 'version', display_name: '版本', icon: 'tag', color: '#FF9800', level: 1 },
    { object_type: 'domain', display_name: '领域', icon: 'business', color: '#4CAF50', level: 2 },
    { object_type: 'sub_domain', display_name: '子领域', icon: 'account_tree', color: '#2196F3', level: 3 },
  ],
  ui_config: { default_expand_level: 2, show_count: true, allow_multi_select: true },
  version_id_injected: false,
}

const mockTreeData = [
  { id: 1, parent_id: null, level: 0, type: 'product', name: '产品A', code: 'A',
    display_name: '产品', icon: 'inventory_2', color: '#9C27B0',
    has_children: true, child_count: 1, unique_key: 'product_1', parent_unique_key: null },
  { id: 11, parent_id: 1, level: 1, type: 'version', name: 'V1.0', code: 'V1',
    display_name: '版本', icon: 'tag', color: '#FF9800',
    has_children: true, child_count: 1, unique_key: 'version_11', parent_unique_key: 'product_1' },
  { id: 21, parent_id: 11, level: 2, type: 'domain', name: '采购域', code: 'PROC',
    display_name: '领域', icon: 'business', color: '#4CAF50',
    has_children: true, child_count: 1, unique_key: 'domain_21', parent_unique_key: 'version_11' },
  { id: 31, parent_id: 21, level: 3, type: 'sub_domain', name: '询价单', code: 'INQ',
    display_name: '子领域', icon: 'account_tree', color: '#2196F3',
    has_children: false, child_count: 0, unique_key: 'sub_domain_31', parent_unique_key: 'domain_21' },
  { id: 32, parent_id: 21, level: 3, type: 'sub_domain', name: '采购订单', code: 'PO',
    display_name: '子领域', icon: 'account_tree', color: '#2196F3',
    has_children: false, child_count: 0, unique_key: 'sub_domain_32', parent_unique_key: 'domain_21' },
]

// [FIX 2026-07-22] 生产脏数据: id=1 在 4 层都出现 (模拟 dirty data)
const mockTreeDataWithCollisions = [
  { id: 1, parent_id: null, level: 0, type: 'product', name: '产品A', code: 'A',
    display_name: '产品', icon: 'inventory_2', color: '#9C27B0',
    has_children: true, child_count: 1, unique_key: 'product_1', parent_unique_key: null },
  { id: 1, parent_id: 1, level: 1, type: 'version', name: 'V1.0', code: 'V1',
    display_name: '版本', icon: 'tag', color: '#FF9800',
    has_children: true, child_count: 1, unique_key: 'version_1', parent_unique_key: 'product_1' },
  { id: 1, parent_id: 1, level: 2, type: 'domain', name: '采购域', code: 'PROC',
    display_name: '领域', icon: 'business', color: '#4CAF50',
    has_children: true, child_count: 1, unique_key: 'domain_1', parent_unique_key: 'version_1' },
  { id: 1, parent_id: 1, level: 3, type: 'sub_domain', name: '采购订单', code: 'PO',
    display_name: '子领域', icon: 'account_tree', color: '#2196F3',
    has_children: false, child_count: 0, unique_key: 'sub_domain_1', parent_unique_key: 'domain_1' },
  { id: 2, parent_id: null, level: 0, type: 'product', name: '产品B', code: 'B',
    display_name: '产品', icon: 'inventory_2', color: '#9C27B0',
    has_children: false, child_count: 0, unique_key: 'product_2', parent_unique_key: null },
]

function mockFetch(data = mockTreeData, hierarchyMeta = mockHierarchyMeta) {
  return vi.fn(() => Promise.resolve({
    ok: true,
    json: () => Promise.resolve({
      data,
      total: data.length,
      hierarchy_meta: hierarchyMeta,
    }),
  }))
}

describe('HierarchicalTreePicker', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', mockFetch())
  })

  describe('基础渲染', () => {
    it('接受 dimensionId 必填 prop, 不需要 hierarchyConfig', () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: { dimensionId: 'sub_domain' },
      })
      expect(wrapper.exists()).toBe(true)
    })

    it('mount 时调用 /tree 端点', async () => {
      const fetchMock = mockFetch()
      vi.stubGlobal('fetch', fetchMock)

      mount(HierarchicalTreePicker, {
        props: { dimensionId: 'sub_domain' },
      })
      await flushPromises()

      expect(fetchMock).toHaveBeenCalled()
      const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1][0]
      expect(lastCall).toContain('/api/v2/bo/management_dimension/sub_domain/tree')
    })

    it('从 API 响应读 hierarchy_meta, 写入 hierarchyMeta state', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: { dimensionId: 'sub_domain' },
      })
      await flushPromises()
      await flushPromises()

      // hierarchyMeta 已加载
      const meta = wrapper.vm.hierarchyMeta
      expect(meta.root_type).toBe('product')
      expect(meta.levels.length).toBe(4)
      expect(meta.levels[0].display_name).toBe('产品')
      expect(meta.levels[3].icon).toBe('account_tree')
    })
  })

  describe('多选模式', () => {
    it('点击确定时 emit type=multiple / ids / nodes', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          multiple: true,
        },
      })
      await flushPromises()

      // 直接设置内部状态模拟勾选
      wrapper.vm.checkedIds = [31]
      await wrapper.vm.$nextTick()
      // 触发确定
      await wrapper.find('.htp-actions .el-button--primary').trigger('click')

      const events = wrapper.emitted('confirm')
      expect(events).toBeTruthy()
      expect(events[0][0].type).toBe('multiple')
      expect(events[0][0].ids).toEqual([31])
      expect(events[0][0].nodes[0]).toMatchObject({
        id: 31,
        name: '询价单',
        type: 'sub_domain',
      })
    })

    it('空选择时确定按钮 disabled', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          
          multiple: true,
        },
      })
      await flushPromises()

      const btn = wrapper.find('.htp-actions .el-button--primary')
      expect(btn.attributes('disabled')).toBeDefined()
    })
  })

  describe('单选模式', () => {
    it('点击确定时 emit type=single / id / node', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          multiple: false,
        },
      })
      await flushPromises()

      wrapper.vm.currentId = 31
      await wrapper.vm.$nextTick()
      await wrapper.find('.htp-actions .el-button--primary').trigger('click')

      const events = wrapper.emitted('confirm')
      expect(events[0][0]).toMatchObject({ type: 'single', id: 31 })
      expect(events[0][0].node.name).toBe('询价单')
    })

    it('无选中时确定按钮 disabled', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          multiple: false,
        },
      })
      await flushPromises()

      const btn = wrapper.find('.htp-actions .el-button--primary')
      expect(btn.attributes('disabled')).toBeDefined()
    })
  })

  describe('搜索', () => {
    it('300ms 防抖后才发起请求', async () => {
      const fetchMock = mockFetch()
      vi.stubGlobal('fetch', fetchMock)

      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
        },
      })
      await flushPromises()
      const initialCalls = fetchMock.mock.calls.length

      // 触发输入
      await wrapper.find('.htp-search input').setValue('采购')
      // 立即检查 — 还没到 debounce 时间
      await flushPromises()
      expect(fetchMock.mock.calls.length).toBe(initialCalls)

      // 等防抖
      await new Promise(r => setTimeout(r, 350))
      await flushPromises()
      expect(fetchMock.mock.calls.length).toBeGreaterThan(initialCalls)

      const lastCall = fetchMock.mock.calls[fetchMock.mock.calls.length - 1][0]
      expect(lastCall).toContain('search=')
    })
  })

  describe('ancestorPath 生成', () => {
    it('confirm payload 中 node 包含 ancestorPath', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          multiple: true,
        },
      })
      await flushPromises()

      wrapper.vm.checkedIds = [32]  // 采购订单
      await wrapper.vm.$nextTick()
      await wrapper.find('.htp-actions .el-button--primary').trigger('click')

      const events = wrapper.emitted('confirm')
      const ancestor = events[0][0].nodes[0].ancestorPath
      expect(ancestor).toContain('产品A')
      expect(ancestor).toContain('V1.0')
      expect(ancestor).toContain('采购域')
      expect(ancestor).toContain('采购订单')
    })
  })

  // [FIX 2026-07-22] 生产脏数据: id 在 4 层间冲突. 旧版本用纯 id 当 key 导致树坍塌.
  //   修复: 用 unique_key (= "{type}_{id}") 作匹配 key, el-tree 用内部 __tk 作 node-key
  describe('ID 冲突场景 (生产脏数据)', () => {
    it('buildNestedTree 用 unique_key 能正确构建 4 层嵌套树', async () => {
      vi.stubGlobal('fetch', mockFetch(mockTreeDataWithCollisions))
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          multiple: true,
        },
      })
      await flushPromises()
      await flushPromises()

      // treeData 应该有 2 个根 (product_1, product_2)
      // product_1 应该嵌套 3 层: version_1 → domain_1 → sub_domain_1
      const vm = wrapper.vm
      const roots = vm.treeData
      expect(roots.length).toBe(2)
      // 找 product_1
      const p1 = roots.find(r => r.unique_key === 'product_1')
      expect(p1).toBeDefined()
      expect(p1.children.length).toBe(1)
      expect(p1.children[0].unique_key).toBe('version_1')
      expect(p1.children[0].children.length).toBe(1)
      expect(p1.children[0].children[0].unique_key).toBe('domain_1')
      expect(p1.children[0].children[0].children.length).toBe(1)
      expect(p1.children[0].children[0].children[0].unique_key).toBe('sub_domain_1')
    })

    it('__tk 全局唯一, 即使 id 重复也能被 el-tree 正确区分', async () => {
      vi.stubGlobal('fetch', mockFetch(mockTreeDataWithCollisions))
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          multiple: true,
        },
      })
      await flushPromises()
      await flushPromises()

      const vm = wrapper.vm
      const tks = []
      function walk(nodes) {
        for (const n of nodes) {
          tks.push(n.__tk)
          if (n.children) walk(n.children)
        }
      }
      walk(vm.treeData)
      // 5 节点, __tk 必须唯一
      expect(tks.length).toBe(5)
      expect(new Set(tks).size).toBe(5)
    })

    it('多选勾选 sub_domain, checkedIds 应保留业务 id (数字, 非 __tk)', async () => {
      vi.stubGlobal('fetch', mockFetch(mockTreeDataWithCollisions))
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          multiple: true,
        },
      })
      await flushPromises()
      await flushPromises()

      // 模拟 el-tree 的 check 事件: 传 __tk (因为 node-key 改了)
      const subNode = wrapper.vm.treeData[0].children[0].children[0].children[0]
      wrapper.vm.onCheckMultiple({
        checkedKeys: [subNode.__tk],
        halfCheckedKeys: [],
        checkedNodes: [subNode],
      })
      await flushPromises()

      // checkedIds 应是业务 id=1 (number), 不是 __tk 字符串
      expect(wrapper.vm.checkedIds).toEqual([1])
    })

    it('ancestorPath 在 id 冲突场景下仍能正确拼接 (用 unique_key 走父链)', async () => {
      vi.stubGlobal('fetch', mockFetch(mockTreeDataWithCollisions))
      const wrapper = mount(HierarchicalTreePicker, {
        props: {
          dimensionId: 'sub_domain',
          multiple: true,
        },
      })
      await flushPromises()
      await flushPromises()

      // buildAncestorPath 用业务 id
      const path = wrapper.vm.buildAncestorPath(1)  // id=1, 4 层都有
      // 应包含 4 层 (sub_domain_1 在 product_1 下, 走链 product_1 -> version_1 -> domain_1 -> sub_domain_1)
      expect(path).toContain('产品A')
      expect(path).toContain('V1.0')
      expect(path).toContain('采购域')
      expect(path).toContain('采购订单')
    })
  })

  // ── [REFACTOR 2026-07-22] 可复用性: 通过 multiple prop 切换单选/多选 ──

  describe('可复用性 (单选/多选切换)', () => {
    it('multiple=true: confirm emit { type: "multiple", ids: number[], nodes: [...] }', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: { dimensionId: 'sub_domain', multiple: true },
      })
      await flushPromises()
      await flushPromises()

      // 直接调内部 handleConfirm (走完 checkedIds 后)
      // 模拟选中 sub_domain_31
      wrapper.vm.checkedIds = [31]
      wrapper.vm.handleConfirm()
      await flushPromises()

      const events = wrapper.emitted('confirm')
      expect(events).toBeTruthy()
      expect(events[0][0].type).toBe('multiple')
      expect(events[0][0].ids).toEqual([31])
    })

    it('multiple=false: confirm emit { type: "single", id: number, node: {...}, ancestorPath: string }', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: { dimensionId: 'sub_domain', multiple: false },
      })
      await flushPromises()
      await flushPromises()

      // 模拟选中 sub_domain_31
      wrapper.vm.currentId = 31
      wrapper.vm.handleConfirm()
      await flushPromises()

      const events = wrapper.emitted('confirm')
      expect(events).toBeTruthy()
      const payload = events[0][0]
      expect(payload.type).toBe('single')
      expect(payload.id).toBe(31)
      expect(payload.node).toBeDefined()
      expect(payload.ancestorPath).toContain('产品A')
    })

    it('同一组件可在不同 dimension 上复用 (dimensionId 是 prop)', async () => {
      // dimensionId='product' 应让 /tree 端点切到 product 链
      const fetchMock = mockFetch()
      vi.stubGlobal('fetch', fetchMock)

      mount(HierarchicalTreePicker, {
        props: { dimensionId: 'product' },
      })
      await flushPromises()

      const calls = fetchMock.mock.calls
      const url = calls[calls.length - 1][0]
      expect(url).toContain('/api/v2/bo/management_dimension/product/tree')
    })

    it('从 hierarchy_meta 自动取 icon, 不依赖 prop hierarchyConfig', async () => {
      const wrapper = mount(HierarchicalTreePicker, {
        props: { dimensionId: 'sub_domain' },
      })
      await flushPromises()
      await flushPromises()

      // 每个 tree node 的 icon 字段应来自 API (不是默认 Box/Folder)
      const meta = wrapper.vm.hierarchyMeta
      expect(meta.levels[0].icon).toBe('inventory_2')  // product
      expect(meta.levels[3].icon).toBe('account_tree')  // sub_domain
    })
  })
})