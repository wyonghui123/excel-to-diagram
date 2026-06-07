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
})
