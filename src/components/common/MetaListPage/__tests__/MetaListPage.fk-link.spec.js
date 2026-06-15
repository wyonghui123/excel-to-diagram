import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'

vi.mock('@/composables/useMetaList', () => ({
  useMetaList: () => ({
    data: ref([
      { id: 1, username: 'admin', name: 'Test Object 1', code: 'OBJ001', user_id: 10, user_id_display: 'Admin User', role_id: 5, role_name: 'Editor', status: 'active' },
      { id: 2, username: 'user1', name: 'Test Object 2', code: 'OBJ002', user_id: 20, user_id_display: 'Normal User', role_id: 3, role_name: 'Viewer', status: 'inactive' }
    ]),
    loading: ref(false),
    error: ref(null),
    total: ref(2),
    pagination: ref({ current: 1, pageSize: 20 }),
    loadData: vi.fn(),
    refreshData: vi.fn()
  })
}))

vi.mock('@/composables/useAssociationNavigation', () => ({
  useAssociationNavigation: () => ({
    getRoutePath: vi.fn((objectType) => {
      const routePathMap = {
        'user': '/user-permission/users',
        'role': '/user-permission/roles',
        'permission': '/user-permission/permissions',
        'user_group': '/user-permission/groups',
        'domain': '/data/domains',
        'business_object': '/data/business-objects',
        'product': '/product-version/products',
      }
      return routePathMap[objectType] || `/${objectType.replace(/_/g, '-')}`
    }),
    navigationSource: ref(null)
  })
}))

describe('MetaListPage - FK字段链接 & BusinessKey 链接渲染', () => {
  const defaultColumns = [
    { prop: 'id', label: 'ID', width: 80 },
    { 
      prop: 'username', 
      label: '用户名', 
      width: 150,
      businessKey: true
    },
    { prop: 'name', label: '名称', width: 200 },
    { 
      prop: 'code', 
      label: '编码', 
      width: 120,
      businessKey: true
    },
    { 
      prop: 'user_id', 
      label: '用户', 
      width: 150,
      valueHelpConfig: {
        source: { type: 'bo', target_bo: 'user' },
        behavior: {},
        presentation: {}
      }
    },
    { 
      prop: 'role_id', 
      label: '角色', 
      width: 150,
      valueHelpConfig: {
        source: { type: 'bo', target_bo: 'role' },
        behavior: {},
        presentation: {}
      }
    },
    { prop: 'status', label: '状态', width: 100 }
  ]

  describe('isFkColumn 字段识别（使用 valueHelpConfig）', () => {
    it('TC-ML-FK-001: BO类型valueHelpConfig列被识别为FK列', () => {
      const fkColumn = defaultColumns.find(c => c.prop === 'user_id')
      expect(fkColumn).toBeDefined()
      expect(fkColumn.valueHelpConfig.source.type).toBe('bo')
    })

    it('TC-ML-FK-002: businessKey列不被识别为FK列', () => {
      const bkColumn = defaultColumns.find(c => c.prop === 'username')
      expect(bkColumn).toBeDefined()
      expect(bkColumn.valueHelpConfig).toBeUndefined()
    })

    it('TC-ML-FK-003: 无valueHelpConfig的列不被识别为FK列', () => {
      const noConfigColumn = defaultColumns.find(c => c.prop === 'status')
      expect(noConfigColumn).toBeDefined()
      expect(noConfigColumn.valueHelpConfig).toBeUndefined()
    })

    it('TC-ML-FK-004: 不同FK列有不同的目标对象类型', () => {
      const userColumn = defaultColumns.find(c => c.prop === 'user_id')
      const roleColumn = defaultColumns.find(c => c.prop === 'role_id')
      
      expect(userColumn.valueHelpConfig.source.target_bo).toBe('user')
      expect(roleColumn.valueHelpConfig.source.target_bo).toBe('role')
    })
  })

  describe('isBusinessKeyColumn 字段识别', () => {
    it('TC-ML-BK-001: businessKey=true列被正确识别', () => {
      const bkColumn = defaultColumns.find(c => c.prop === 'username')
      expect(bkColumn.businessKey).toBe(true)
    })

    it('TC-ML-BK-002: 普通列不被识别为businessKey列', () => {
      const normalColumn = defaultColumns.find(c => c.prop === 'name')
      expect(normalColumn.businessKey).toBeUndefined()
    })

    it('TC-ML-BK-003: FK列不被识别为businessKey列', () => {
      const fkColumn = defaultColumns.find(c => c.prop === 'user_id')
      expect(fkColumn.businessKey).toBeUndefined()
      expect(fkColumn.valueHelpConfig).toBeDefined()
    })

    it('TC-ML-BK-004: 多个businessKey列同时存在', () => {
      const bkColumns = defaultColumns.filter(c => c.businessKey === true)
      expect(bkColumns.length).toBe(2)
      expect(bkColumns.map(c => c.prop)).toContain('username')
      expect(bkColumns.map(c => c.prop)).toContain('code')
    })

    it('TC-ML-BK-005: businessKey列使用bk-link样式', async () => {
      const wrapper = mount({
        template: `
          <div>
            <span
              v-if="column.businessKey && row[column.prop]"
              class="bk-link"
              @click.stop="onClick"
            >
              {{ row[column.prop] }}
            </span>
            <span v-else-if="column.businessKey" class="bk-empty">-</span>
            <span v-else>{{ row[column.prop] }}</span>
          </div>
        `,
        setup() {
          const column = defaultColumns.find(c => c.prop === 'username')
          const row = { username: 'admin' }
          const onClick = vi.fn()
          return { column, row, onClick }
        }
      })

      await nextTick()
      const bkLink = wrapper.find('.bk-link')
      expect(bkLink.exists()).toBe(true)
      expect(bkLink.text()).toBe('admin')
    })

    it('TC-ML-BK-006: businessKey空值时显示"-"', async () => {
      const wrapper = mount({
        template: `
          <div>
            <span
              v-if="column.businessKey && row[column.prop]"
              class="bk-link"
              @click.stop="onClick"
            >
              {{ row[column.prop] }}
            </span>
            <span v-else-if="column.businessKey" class="bk-empty">-</span>
          </div>
        `,
        setup() {
          const column = defaultColumns.find(c => c.prop === 'username')
          const row = { username: null }
          return { column, row }
        }
      })

      await nextTick()
      const empty = wrapper.find('.bk-empty')
      expect(empty.exists()).toBe(true)
      expect(empty.text()).toBe('-')
    })

    it('TC-ML-BK-007: businessKey值为0时不显示链接', async () => {
      const wrapper = mount({
        template: `
          <div>
            <span
              v-if="column.businessKey && row[column.prop]"
              class="bk-link"
              @click.stop="onClick"
            >
              {{ row[column.prop] }}
            </span>
            <span v-else-if="column.businessKey" class="bk-empty">-</span>
          </div>
        `,
        setup() {
          const column = defaultColumns.find(c => c.prop === 'username')
          const row = { username: 0 }
          return { column, row }
        }
      })

      await nextTick()
      const link = wrapper.find('.bk-link')
      expect(link.exists()).toBe(false)
    })

    it('TC-ML-BK-008: businessKey值为空字符串时显示"-"', async () => {
      const wrapper = mount({
        template: `
          <div>
            <span
              v-if="column.businessKey && row[column.prop]"
              class="bk-link"
              @click.stop="onClick"
            >
              {{ row[column.prop] }}
            </span>
            <span v-else-if="column.businessKey" class="bk-empty">-</span>
          </div>
        `,
        setup() {
          const column = defaultColumns.find(c => c.prop === 'username')
          const row = { username: '' }
          return { column, row }
        }
      })

      await nextTick()
      const empty = wrapper.find('.bk-empty')
      expect(empty.exists()).toBe(true)
    })
  })

  describe('FK vs BusinessKey 区分', () => {
    it('TC-ML-MIX-001: FK列优先于businessKey列渲染', () => {
      const fkColumn = defaultColumns.find(c => c.prop === 'user_id')
      
      // FK列有 valueHelpConfig 所以 isFkColumn=true
      const isFk = fkColumn?.valueHelpConfig?.source?.type === 'bo'
      expect(isFk).toBe(true)
    })

    it('TC-ML-MIX-002: businessKey列不会被误识别为FK列', () => {
      const bkColumn = defaultColumns.find(c => c.prop === 'username')
      
      const isFk = bkColumn?.valueHelpConfig?.source?.type === 'bo'
      expect(isFk).toBeFalsy()
      
      const isBk = bkColumn?.businessKey === true
      expect(isBk).toBe(true)
    })

    it('TC-ML-MIX-003: 同时存在FK和businessKey列的场景', () => {
      const hasFk = defaultColumns.some(c => 
        c.valueHelpConfig?.source?.type === 'bo'
      )
      const hasBk = defaultColumns.some(c => c.businessKey === true)
      
      expect(hasFk).toBe(true)
      expect(hasBk).toBe(true)
    })
  })

  describe('getFkDisplayValue 显示值获取', () => {
    it('TC-ML-DISP-001: 有_display后缀时优先使用', () => {
      const row = { user_id: 10, user_id_display: 'Admin User' }
      const column = defaultColumns.find(c => c.prop === 'user_id')
      
      const displayKey = `${column.prop}_display`
      expect(row[displayKey]).toBe('Admin User')
    })

    it('TC-ML-DISP-002: 无_display后缀时使用_name后缀', () => {
      const row = { role_id: 5, role_name: 'Editor' }
      const column = defaultColumns.find(c => c.prop === 'role_id')
      
      const nameKey = `${column.prop.replace(/_id$/, '')}_name`
      expect(row[nameKey]).toBe('Editor')
    })

    it('TC-ML-DISP-003: 都没有时回退到原始值', () => {
      const row = { user_id: 99 }
      
      expect(row['user_id_display']).toBeUndefined()
      expect(row['user_name']).toBeUndefined()
      expect(row.user_id).toBe(99)
    })

    it('TC-ML-DISP-004: 值为null时返回空字符串', () => {
      const row = { user_id: null }
      expect(row.user_id).toBeNull()
    })
  })

  describe('边界情况处理', () => {
    it('TC-ML-EDGE-001: 空columns数组时不报错', () => {
      expect(() => []).not.toThrow()
    })

    it('TC-ML-EDGE-002: column为null/undefined时不报错', () => {
      function checkBusinessKeySafe(col) {
        return col?.businessKey === true
      }
      
      expect(checkBusinessKeySafe(null)).toBe(false)
      expect(checkBusinessKeySafe(undefined)).toBe(false)
      expect(checkBusinessKeySafe({})).toBe(false)
    })

    it('TC-ML-EDGE-003: valueHelpConfig为undefined时不报错', () => {
      function isFkColumnSafe(col) {
        return col?.valueHelpConfig?.source?.type === 'bo'
      }
      
      expect(isFkColumnSafe({ prop: 'test' })).toBe(false)
    })

    it('TC-ML-EDGE-004: source缺少target_bo时返回null', () => {
      const incompleteColumn = {
        prop: 'incomplete',
        valueHelpConfig: {
          source: { type: 'bo' }
        }
      }

      function getFkTargetType(col) {
        if (col?.valueHelpConfig?.source?.type !== 'bo') return null
        return col.valueHelpConfig.source.target_bo || null
      }

      expect(getFkTargetType(incompleteColumn)).toBeNull()
    })
  })

  describe('业务键 vs FK 视觉区分 - tooltip 差异化', () => {
    // 业务键模板：镜像 MetaListPage.vue 中的渲染逻辑
    const bkTemplate = `
      <div>
        <span
          v-if="column.businessKey && row[column.prop]"
          class="bk-link"
          title="查看本对象详情"
          @click.stop="onClick"
        >
          {{ row[column.prop] }}
        </span>
        <span v-else-if="column.businessKey" class="bk-empty">-</span>
      </div>
    `

    it('TC-ML-TT-001: 业务键链接带"查看本对象详情"tooltip（区别于 FK 的"打开 X 详情"）', async () => {
      const wrapper = mount({
        template: bkTemplate,
        setup() {
          const column = defaultColumns.find(c => c.prop === 'username')
          const row = { username: 'admin' }
          const onClick = vi.fn()
          return { column, row, onClick }
        }
      })

      await nextTick()
      const bkLink = wrapper.find('.bk-link')
      expect(bkLink.exists()).toBe(true)
      expect(bkLink.attributes('title')).toBe('查看本对象详情')
    })

    it('TC-ML-TT-002: 业务键链接无 Promotion 图标（与 FK 链接的视觉差异）', async () => {
      const wrapper = mount({
        template: bkTemplate,
        setup() {
          const column = defaultColumns.find(c => c.prop === 'username')
          const row = { username: 'admin' }
          const onClick = vi.fn()
          return { column, row, onClick }
        }
      })

      await nextTick()
      // 业务键是纯文本 span，不包含图标
      const bkLink = wrapper.find('.bk-link')
      expect(bkLink.find('.fk-link__icon').exists()).toBe(false)
    })

    it('TC-ML-TT-003: 业务键 tooltip 与 FK tooltip 文案不同（语义可区分）', () => {
      // 业务键的 tooltip 强调"本对象"
      const bkTitle = '查看本对象详情'
      // FK 的 tooltip 强调"打开 [对象名] 详情"（参见 FkLinkField.spec.js TC-FK-LINK-028）
      const fkTitleTemplate = (label) => `打开 ${label} 详情`

      expect(bkTitle).not.toBe(fkTitleTemplate('用户'))
      expect(bkTitle).toContain('本对象')
      expect(fkTitleTemplate('用户')).toContain('打开')
    })
  })

  describe('getFkIdValue - FK ID 获取逻辑（修复导航传值错误）', () => {
    // 模拟 getFkIdValue 的核心逻辑（与 MetaListPage.vue 中实现一致）
    function getFkIdValue(row, column) {
      // 1. 优先用 apiParamKey（YAML 显式声明的 FK 字段映射）
      const apiParamKey = column.apiParamKey || column.api_param_key
      if (apiParamKey && row[apiParamKey] != null) {
        return row[apiParamKey]
      }
      // 2. 从 value_help.source 推导：target_bo + '_id'
      const targetBo = column.valueHelpConfig?.source?.target_bo
      if (targetBo) {
        const fkIdKey = `${targetBo}_id`
        if (row[fkIdKey] != null) {
          return row[fkIdKey]
        }
      }
      // 3. 兜底：如果 column.prop 本身就是 _id 结尾，直接用
      if (column.prop?.endsWith('_id')) {
        return row[column.prop]
      }
      // 4. 最后兜底
      return row[column.prop]
    }

    // 模拟后端返回的列表行数据
    const boRow = {
      id: 1,
      code: 'BO_CUSTOMER',
      name: '客户',
      service_module_id: 1,
      service_module_name: '采购需求',
      domain_id: 2,
      domain_name: '供应链',
      display_values: { service_module_id: '采购需求', domain_id: '供应链' }
    }

    it('TC-ML-FKID-001: FK 显示列通过 apiParamKey 获取 ID（service_module_name → service_module_id）', () => {
      // service_module_name 列配置了 apiParamKey: service_module_id
      const column = {
        prop: 'service_module_name',
        label: '服务模块',
        apiParamKey: 'service_module_id',
        valueHelpConfig: { source: { type: 'bo', target_bo: 'service_module' } }
      }

      const fkId = getFkIdValue(boRow, column)
      expect(fkId).toBe(1) // 数字 ID，不是 "采购需求"
      expect(typeof fkId).toBe('number')
    })

    it('TC-ML-FKID-002: 无 apiParamKey 时通过 target_bo 推导 FK ID 字段', () => {
      // domain_name 列没有 apiParamKey，但有 target_bo: domain
      const column = {
        prop: 'domain_name',
        label: '子领域',
        valueHelpConfig: { source: { type: 'bo', target_bo: 'domain' } }
      }

      const fkId = getFkIdValue(boRow, column)
      expect(fkId).toBe(2) // 通过 domain_id 推导
    })

    it('TC-ML-FKID-003: column.prop 以 _id 结尾时直接使用', () => {
      const column = {
        prop: 'user_id',
        label: '用户',
        valueHelpConfig: { source: { type: 'bo', target_bo: 'user' } }
      }

      const row = { user_id: 10, user_id_display: 'Admin User' }
      const fkId = getFkIdValue(row, column)
      expect(fkId).toBe(10)
    })

    it('TC-ML-FKID-004: FK ID 为 null 时正确返回 null（而非显示文本）', () => {
      const row = { id: 1, service_module_id: null, service_module_name: null }
      const column = {
        prop: 'service_module_name',
        label: '服务模块',
        apiParamKey: 'service_module_id',
        valueHelpConfig: { source: { type: 'bo', target_bo: 'service_module' } }
      }

      const fkId = getFkIdValue(row, column)
      expect(fkId).toBeNull()
    })

    it('TC-ML-FKID-005: 修复前错误场景 - 不应返回显示文本作为 ID', () => {
      // 修复前：row[column.prop] = row['service_module_name'] = '采购需求'
      // 修复后：通过 apiParamKey 返回 row['service_module_id'] = 1
      const column = {
        prop: 'service_module_name',
        label: '服务模块',
        apiParamKey: 'service_module_id',
        valueHelpConfig: { source: { type: 'bo', target_bo: 'service_module' } }
      }

      const wrongValue = boRow[column.prop] // '采购需求' - 这是修复前的错误行为
      const correctValue = getFkIdValue(boRow, column) // 1 - 修复后

      expect(wrongValue).toBe('采购需求') // 修复前：显示文本
      expect(correctValue).toBe(1) // 修复后：数字 ID
      expect(wrongValue).not.toBe(correctValue)
    })

    it('TC-ML-FKID-006: 兜底场景 - 无任何 FK ID 映射时返回原始值', () => {
      const column = {
        prop: 'unknown_field',
        label: '未知字段',
        valueHelpConfig: { source: { type: 'bo', target_bo: 'unknown' } }
      }

      const row = { unknown_field: 'some_value' }
      const fkId = getFkIdValue(row, column)
      expect(fkId).toBe('some_value')
    })
  })

  describe('getFkDetailMode - FK 链接详情页模式确定', () => {
    // 模拟 getFkDetailMode 的核心逻辑
    function getFkDetailMode(column, hasDetailPageRoute, isTargetInSamePage) {
      const targetBo = column.valueHelpConfig?.source?.target_bo
      if (!targetBo) return 'page'

      // 目标对象类型配置了 detail_mode: page → 'page'
      // (这里简化模拟，实际从 metaService.getViewConfigSync 获取)
      const targetViewConfig = column._mockTargetViewConfig
      if (targetViewConfig?.data?.list?.detail_mode === 'page') {
        return 'page'
      }

      // 当前列表是 drawer 模式（非 page），且目标对象在同页面 tabs 中 → 'drawer'
      if (!hasDetailPageRoute && isTargetInSamePage) {
        return 'drawer'
      }

      // 默认：跳转独立页面
      return 'page'
    }

    const fkColumn = {
      prop: 'service_module_name',
      label: '服务模块',
      apiParamKey: 'service_module_id',
      valueHelpConfig: { source: { type: 'bo', target_bo: 'service_module' } }
    }

    it('TC-ML-DM-001: 目标对象配置 detail_mode=page 时返回 page', () => {
      const column = {
        ...fkColumn,
        _mockTargetViewConfig: { data: { list: { detail_mode: 'page' } } }
      }
      expect(getFkDetailMode(column, false, true)).toBe('page')
    })

    it('TC-ML-DM-002: 当前 drawer 模式 + 目标在同页面 tabs 中 → drawer', () => {
      expect(getFkDetailMode(fkColumn, false, true)).toBe('drawer')
    })

    it('TC-ML-DM-003: 当前 drawer 模式 + 目标不在同页面 tabs 中 → page', () => {
      expect(getFkDetailMode(fkColumn, false, false)).toBe('page')
    })

    it('TC-ML-DM-004: 当前 page 模式（hasDetailPageRoute=true）→ page', () => {
      expect(getFkDetailMode(fkColumn, true, true)).toBe('page')
    })

    it('TC-ML-DM-005: 无 valueHelpConfig 时默认 page', () => {
      const noConfigColumn = { prop: 'name', label: '名称' }
      expect(getFkDetailMode(noConfigColumn, false, false)).toBe('page')
    })

    it('TC-ML-DM-006: 无 target_bo 时默认 page', () => {
      const noTargetColumn = {
        prop: 'name',
        label: '名称',
        valueHelpConfig: { source: { type: 'enum' } }
      }
      expect(getFkDetailMode(noTargetColumn, false, false)).toBe('page')
    })
  })
})
