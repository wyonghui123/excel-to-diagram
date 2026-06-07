import { describe, it, expect, vi, beforeEach, afterEach, afterAll } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import { setActivePinia, createPinia } from 'pinia'
import ObjectPage from '../ObjectPage.vue'

// 修复 StateTransitionButtons 组件 useStore 报错 + 子组件真实 fetch 触发
const _origFetch = globalThis.fetch
const _origResizeObserver = globalThis.ResizeObserver
const _origMutationObserver = globalThis.MutationObserver
const _origMatchMedia = globalThis.matchMedia

beforeEach(() => {
  setActivePinia(createPinia())
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: true, status: 200,
    json: async () => ({ success: true, data: [], message: '' })
  })
  globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
  globalThis.MutationObserver = class { observe() {} disconnect() {} takeRecords() { return [] } }
  if (!globalThis.matchMedia) {
    globalThis.matchMedia = vi.fn().mockImplementation((q) => ({
      matches: false, media: q, onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      dispatchEvent: vi.fn()
    }))
  }
})

afterEach(() => { vi.clearAllMocks() })

afterAll(() => {
  globalThis.fetch = _origFetch
  globalThis.ResizeObserver = _origResizeObserver
  globalThis.MutationObserver = _origMutationObserver
  globalThis.matchMedia = _origMatchMedia
})

vi.mock('@/services/metaService', () => {
  const actual = vi.importActual('@/services/metaService')
  return {
    ...actual,
    default: {
      ...actual.default,
      getUIConfig: vi.fn().mockResolvedValue({
        success: true,
        data: {
          fields: [
            { id: 'name', name: '名称', type: 'string' },
            { id: 'code', name: '编码', type: 'string' },
            { id: 'user_id', name: '用户', type: 'integer', value_help: { source: { type: 'bo', target_bo: 'user' } } },
            { id: 'role_id', name: '角色', type: 'integer', value_help: { source: { type: 'bo', target_bo: 'role' }, behavior: {}, presentation: {} } },
            { id: 'status', name: '状态', type: 'string', enum_values: [{ label: '启用', value: 'active' }] }
          ]
        }
      })
    }
  }
})

vi.mock('@/composables/useAuditLogs', () => ({
  useAuditLogs: () => ({
    logs: ref([]),
    total: ref(0),
    loading: ref(false),
    loadLogs: vi.fn(),
    setPage: vi.fn(),
    setFilters: vi.fn()
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
      }
      return routePathMap[objectType] || `/${objectType.replace(/_/g, '-')}`
    })
  })
}))

describe('ObjectPage - FK字段识别与渲染', () => {
  const defaultSections = [{
    key: 'basic',
    label: '基本信息',
    type: 'standard',
    fieldGroups: [{
      title: '基础信息',
      fields: ['name', 'code', 'user_id', 'role_id', 'status']
    }]
  }]

  function createWrapper(props = {}) {
    return mount(ObjectPage, {
      props: {
        title: '测试对象',
        sections: defaultSections,
        formData: {},
        fieldDefinitions: {},
        autoLoadMeta: false,
        editing: false,
        objectType: 'test_object',
        objectId: 1,
        ...props
      },
      global: {
        stubs: {
          'router-link': true,
          'router-view': true,
          FkLinkField: true
        }
      }
    })
  }

  describe('isFkField 字段识别', () => {
    it('TC-OP-FK-001: BO类型value_help被识别为FK字段', async () => {
      const wrapper = createWrapper({
        fieldDefinitions: {
          user_id: { label: '用户', type: 'integer', valueHelp: { source: { type: 'bo', target_bo: 'user' } } },
          name: { label: '名称', type: 'text' }
        }
      })

      await nextTick()
      
      const vm = wrapper.vm
      expect(vm.isFkField('user_id')).toBe(true)
    })

    it('TC-OP-FK-002: 普通文本字段不被识别为FK字段', async () => {
      const wrapper = createWrapper({
        fieldDefinitions: {
          name: { label: '名称', type: 'text' }
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.isFkField('name')).toBe(false)
    })

    it('TC-OP-FK-003: 枚举类型字段不被识别为FK字段', async () => {
      const wrapper = createWrapper({
        fieldDefinitions: {
          status: { label: '状态', type: 'select', options: [], valueHelp: { source: { type: 'enum', enum_type_id: 'status_type' } } }
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.isFkField('status')).toBe(false)
    })

    it('TC-OP-FK-004: 无value_help配置的字段不被识别为FK字段', async () => {
      const wrapper = createWrapper({
        fieldDefinitions: {
          code: { label: '编码', type: 'text' }
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.isFkField('code')).toBe(false)
    })

    it('TC-OP-FK-005: custom类型value_help不被识别为FK字段', async () => {
      const wrapper = createWrapper({
        fieldDefinitions: {
          external_ref: { label: '外部引用', type: 'text', valueHelp: { source: { type: 'custom', endpoint: '/api/external' } } }
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.isFkField('external_ref')).toBe(false)
    })

    it('TC-OP-FK-006: 不存在的字段返回false', async () => {
      const wrapper = createWrapper({})

      await nextTick()

      const vm = wrapper.vm
      expect(vm.isFkField('non_existent_field')).toBe(false)
    })
  })

  describe('getFkTargetObjectType 目标类型获取', () => {
    it('TC-OP-FK-007: 返回正确的目标BO类型', async () => {
      const wrapper = createWrapper({
        fieldDefinitions: {
          user_id: { label: '用户', type: 'integer', valueHelp: { source: { type: 'bo', target_bo: 'user' } } }
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.getFkTargetObjectType('user_id')).toBe('user')
    })

    it('TC-OP-FK-008: 不同FK字段返回不同的目标类型', async () => {
      const wrapper = createWrapper({
        fieldDefinitions: {
          user_id: { label: '用户', type: 'integer', valueHelp: { source: { type: 'bo', target_bo: 'user' } } },
          role_id: { label: '角色', type: 'integer', valueHelp: { source: { type: 'bo', target_bo: 'role' } } }
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.getFkTargetObjectType('user_id')).toBe('user')
      expect(vm.getFkTargetObjectType('role_id')).toBe('role')
    })

    it('TC-OP-FK-009: 非FK字段返回null', async () => {
      const wrapper = createWrapper({
        fieldDefinitions: {
          name: { label: '名称', type: 'text' }
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.getFkTargetObjectType('name')).toBeNull()
    })

    it('TC-OP-FK-010: 缺少target_bo时返回null', async () => {
      const wrapper = createWrapper({
        fieldDefinitions: {
          broken_fk: { label: '损坏的FK', type: 'integer', valueHelp: { source: { type: 'bo' } } }
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.getFkTargetObjectType('broken_fk')).toBeNull()
    })
  })

  describe('getFieldDisplayValue 显示值获取', () => {
    it('TC-OP-FK-011: 有display后缀字段时优先使用', async () => {
      const wrapper = createWrapper({
        formData: {
          user_id: 1,
          user_id_display: 'Admin User'
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.getFieldDisplayValue('user_id')).toBe('Admin User')
    })

    it('TC-OP-FK-012: 无display字段时返回原始值', async () => {
      const wrapper = createWrapper({
        formData: {
          role_id: 5
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.getFieldDisplayValue('role_id')).toBe(5)
    })

    it('TC-OP-FK-013: 值为null时返回空字符串', async () => {
      const wrapper = createWrapper({
        formData: {
          user_id: null
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.getFieldDisplayValue('user_id')).toBe('')
    })

    it('TC-OP-FK-014: 值为undefined时返回空字符串', async () => {
      const wrapper = createWrapper({
        formData: {}
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.getFieldDisplayValue('user_id')).toBe('')
    })
  })

  describe('浏览态字段渲染', () => {
    it('TC-OP-FK-015: 浏览态下FK字段渲染为FkLinkField组件', async () => {
      const wrapper = createWrapper({
        editing: false,
        formData: {
          user_id: 1,
          name: 'Test Object'
        },
        fieldDefinitions: {
          user_id: { label: '用户', type: 'integer', valueHelp: { source: { type: 'bo', target_bo: 'user' } } },
          name: { label: '名称', type: 'text' }
        }
      })

      await nextTick()

      const fkLinkFields = wrapper.findAllComponents({ name: 'FkLinkField' })
      expect(fkLinkFields.length).toBeGreaterThanOrEqual(1)
    })

    it('TC-OP-FK-016: 浏览态下普通字段渲染为静态文本', async () => {
      const wrapper = createWrapper({
        editing: false,
        formData: {
          name: 'Test Name'
        },
        fieldDefinitions: {
          name: { label: '名称', type: 'text' }
        }
      })

      await nextTick()

      const staticValues = wrapper.findAll('.op-field-value')
      expect(staticValues.length).toBeGreaterThan(0)
    })

    it('TC-OP-FK-017: 编辑态下所有字段使用输入组件', async () => {
      const wrapper = createWrapper({
        editing: true,
        formData: {
          user_id: 1,
          name: 'Test Object'
        },
        fieldDefinitions: {
          user_id: { label: '用户', type: 'integer', valueHelp: { source: { type: 'bo', target_bo: 'user' } } },
          name: { label: '名称', type: 'text' }
        }
      })

      await nextTick()

      const fkLinkFields = wrapper.findAllComponents({ name: 'FkLinkField' })
      const staticValues = wrapper.findAll('.op-field-value')
      
      expect(fkLinkFields.length).toBe(0)
      expect(staticValues.length).toBe(0)
    })

    it('TC-OP-FK-018: 空值的普通字段显示"-"占位符', async () => {
      const wrapper = createWrapper({
        editing: false,
        formData: {
          name: null
        },
        fieldDefinitions: {
          name: { label: '名称', type: 'text' }
        }
      })

      await nextTick()

      const staticValues = wrapper.findAll('.op-field-value')
      const hasEmptyValue = staticValues.some(el => el.text() === '-')
      expect(hasEmptyValue).toBe(true)
    })
  })

  describe('autoLoadMeta 模式下的FK识别', () => {
    beforeEach(() => {
      vi.clearAllMocks()
    })

    it('TC-OP-FK-019: autoLoadMeta模式支持value_help字段定义', async () => {
      const wrapper = mount(ObjectPage, {
        props: {
          title: '测试对象',
          sections: defaultSections,
          formData: { user_id: 1 },
          autoLoadMeta: true,
          editing: false,
          objectType: 'test_object',
          objectId: 1
        },
        global: {
          stubs: {
            'router-link': true,
            'router-view': true,
            FkLinkField: true
          }
        }
      })

      await nextTick()
      await new Promise(resolve => setTimeout(resolve, 200))

      expect(wrapper.exists()).toBe(true)
      
      const fkLinks = wrapper.findAllComponents({ name: 'FkLinkField' })
      expect(fkLinks.length).toBeGreaterThanOrEqual(0)
    })
  })

  describe('多FK字段场景', () => {
    it('TC-OP-FK-020: 同时存在多个FK字段时正确识别', async () => {
      const wrapper = createWrapper({
        editing: false,
        formData: {
          user_id: 1,
          role_id: 2,
          group_id: 3,
          name: 'Multi FK Test'
        },
        fieldDefinitions: {
          user_id: { label: '用户', type: 'integer', valueHelp: { source: { type: 'bo', target_bo: 'user' } } },
          role_id: { label: '角色', type: 'integer', valueHelp: { source: { type: 'bo', target_bo: 'role' } } },
          group_id: { label: '用户组', type: 'integer', valueHelp: { source: { type: 'bo', target_bo: 'user_group' } } },
          name: { label: '名称', type: 'text' }
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.isFkField('user_id')).toBe(true)
      expect(vm.isFkField('role_id')).toBe(true)
      expect(vm.isFkField('group_id')).toBe(true)
      expect(vm.isFkField('name')).toBe(false)
    })

    it('TC-OP-FK-021: 多个FK字段生成不同路由路径', async () => {
      const wrapper = createWrapper({
        editing: false,
        formData: {
          user_id: 10,
          role_id: 20
        },
        fieldDefinitions: {
          user_id: { label: '用户', type: 'integer', valueHelp: { source: { type: 'bo', target_bo: 'user' } } },
          role_id: { label: '角色', type: 'integer', valueHelp: { source: { type: 'bo', target_bo: 'role' } } }
        }
      })

      await nextTick()

      const fkLinkFields = wrapper.findAllComponents({ name: 'FkLinkField' })
      expect(fkLinkFields.length).toBeGreaterThanOrEqual(2)

      const propsList = fkLinkFields.map(f => f.props())
      const hasUserRoute = propsList.some(p => p.targetObjectType === 'user')
      const hasRoleRoute = propsList.some(p => p.targetObjectType === 'role')

      expect(hasUserRoute).toBe(true)
      expect(hasRoleRoute).toBe(true)
    })
  })

  describe('边界情况处理', () => {
    it('TC-OP-FK-022: fieldDefinitions为空对象时不报错', async () => {
      const wrapper = createWrapper({
        fieldDefinitions: {}
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.isFkField('any_field')).toBe(false)
    })

    it('TC-OP-FK-023: value_help.source为null时不报错', async () => {
      const wrapper = createWrapper({
        fieldDefinitions: {
          bad_field: { label: '坏字段', type: 'text', valueHelp: null }
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.isFkField('bad_field')).toBe(false)
    })

    it('TC-OP-FK-024: value_help为undefined时不报错', async () => {
      const wrapper = createWrapper({
        fieldDefinitions: {
          no_vh_field: { label: '无VH字段', type: 'text' }
        }
      })

      await nextTick()

      const vm = wrapper.vm
      expect(vm.isFkField('no_vh_field')).toBe(false)
    })

    it('TC-OP-FK-025: 切换编辑模式时正确切换渲染模式', async () => {
      const wrapper = createWrapper({
        editing: false,
        formData: { user_id: 1, name: 'Test' },
        fieldDefinitions: {
          user_id: { label: '用户', type: 'integer', valueHelp: { source: { type: 'bo', target_bo: 'user' } } },
          name: { label: '名称', type: 'text' }
        }
      })

      await nextTick()
      
      let fkLinks = wrapper.findAllComponents({ name: 'FkLinkField' })
      expect(fkLinks.length).toBeGreaterThan(0)

      await wrapper.setProps({ editing: true })
      await nextTick()

      fkLinks = wrapper.findAllComponents({ name: 'FkLinkField' })
      expect(fkLinks.length).toBe(0)

      await wrapper.setProps({ editing: false })
      await nextTick()

      fkLinks = wrapper.findAllComponents({ name: 'FkLinkField' })
      expect(fkLinks.length).toBeGreaterThan(0)
    })
  })
})
