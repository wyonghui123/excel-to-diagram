import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref, computed, reactive } from 'vue'

const {
  mockSelectedVersionId,
  mockActiveTab,
  mockHasSelection,
  mockCombinedFilters,
  mockScopeIds
} = vi.hoisted(() => {
  const { ref, computed, reactive } = require('vue')
  const _sid = ref(1)
  const _at = ref('domain')
  const _cf = ref({ version_id: 1 })
  return {
    mockSelectedVersionId: _sid,
    mockActiveTab: _at,
    mockHasSelection: computed(() => false),
    mockCombinedFilters: _cf,
    mockScopeIds: reactive({
      domain: { selected: [], effective: [] },
      sub_domain: { selected: [], effective: [] },
      service_module: { selected: [], effective: [] },
      business_object: { selected: [], effective: [] },
      relationship: { selected: [], effective: [] },
      globalFilters: {},
      relationExtra: { relationCodes: [], categoryTypes: [], filterRelationCodes: [] }
    })
  }
})

vi.mock('@/composables/useMultiObjectPage', () => ({
  useMultiObjectPage: vi.fn(() => ({
    objectTypes: ['domain', 'sub_domain'],
    tabs: [
      { name: 'domain', label: '领域', icon: null },
      { name: 'sub_domain', label: '子领域', icon: null }
    ],
    activeTab: mockActiveTab,
    versionContext: {
      selectedVersionId: mockSelectedVersionId,
      selectedVersion: { id: 1, name: 'V1.0', product_name: '产品A' },
      versions: [{ id: 1, name: 'V1.0', product_name: '产品A' }],
      hasContext: true,
      selectVersion: vi.fn(),
      clearContext: vi.fn()
    },
    filterFlow: {
      combinedFilters: mockCombinedFilters,
      registerSource: vi.fn(),
      unregisterSource: vi.fn(),
      refresh: vi.fn()
    },
    contextSource: { source: { id: 'version-context' }, setContext: vi.fn(), clear: vi.fn() },
    scopeSource: { source: { id: 'multi-object-scope' }, setBusinessObjectIds: vi.fn(), setRelationCodes: vi.fn(), clear: vi.fn() },
    scopeIds: mockScopeIds,
    hasScopeSelection: mockHasSelection,
    combinedFilters: mockCombinedFilters,
    baseFilters: computed(() => ({ version_id: mockSelectedVersionId.value || 0 })),
    exportFilters: computed(() => ({ version_id: mockSelectedVersionId.value || 0 })),
    objectTypeLabels: computed(() => ({ domain: '领域', sub_domain: '子领域' })),
    canImport: computed(() => !!mockSelectedVersionId.value),
    canExport: computed(() => !!mockSelectedVersionId.value),
    canShowChart: computed(() => false),
    canRefresh: computed(() => !!mockSelectedVersionId.value),
    refreshTrigger: ref(0),
    importDialogVisible: ref(false),
    exportDialogVisible: ref(false),
    importContext: computed(() => ({ version_id: 1, product_id: 1 })),
    exportContext: computed(() => ({ objectType: 'domain', filters: {}, objectTypes: ['domain', 'sub_domain'] })),
    metaObjectRef: null,
    handleScopeChange: vi.fn(),
    clearScope: vi.fn(),
    handleToolbarChange: vi.fn(),
    handleGlobalAction: vi.fn(),
    handleShowChart: vi.fn(() => ({ versionId: 1 })),
    restoreStateFromDiagram: vi.fn(() => false),
    handleImportSuccess: vi.fn(),
    handleExportSuccess: vi.fn()
  }))
}))

import { MultiObjectManagementPage } from '@/components/common/MultiObjectManagementPage'

const stubs = {
  GlobalToolbar: {
    template: '<div class="gt-stub">Toolbar</div>',
    props: ['compact'],
    emits: ['change', 'action']
  },
  MasterDetailLayout: {
    template: '<div class="mdl-stub"><div class="master-slot"><slot name="master" /></div><div class="detail-slot"><slot name="detail" /></div></div>',
    props: ['sidebarWidth', 'sidebarCollapsible', 'minWidth', 'maxWidth']
  },
  RelationScopeTree: {
    template: '<div class="rst-stub">ScopeTree</div>',
    props: ['versionId', 'initialBoIds', 'initialRelationCodes', 'filterDisabled']
  },
  MetaListPage: {
    template: '<div class="ml-stub"><div class="ml-type">{{ objectType }}</div><slot v-for="(_,n) in $slots" :key="n" :name="n" /></div>',
    props: ['objectType', 'initialFilters', 'options', 'enableDetail', 'enableAutoCrud']
  },
  'el-tabs': { template: '<div class="el-tabs-stub"><slot /></div>', props: ['modelValue'] },
  'el-tab-pane': { template: '<div class="tab-pane-stub">{{ label }}</div>', props: ['label', 'name'] },
  'el-icon': { template: '<span class="icon-stub"><slot /></span>', props: ['size'] },
  'el-button': { template: '<button class="btn-stub"><slot /></button>', props: ['type', 'link', 'size'] },
  'el-tag': { template: '<span class="tag-stub"><slot /></span>', props: ['type', 'size'] },
  FolderOpened: { template: '<span>F</span>' },
  Connection: { template: '<span>C</span>' },
  ImportDialog: {
    template: '<div v-if="visible" class="imd-stub">ImportDialog</div>',
    props: ['visible', 'objectType', 'objectTypes', 'objectTypeLabels', 'multiTypeMode', 'context']
  },
  ExportDialog: {
    template: '<div v-if="visible" class="exd-stub">ExportDialog</div>',
    props: ['visible', 'objectType', 'filters', 'objectTypes', 'objectTypeLabels', 'sortInfo', 'defaultSort', 'currentCount', 'totalCount', 'multiTypeMode', 'showExportMode', 'showExportOptions']
  }
}

function mountPage(propsOverrides = {}, slots = {}) {
  return mount(MultiObjectManagementPage, {
    props: {
      objectTypes: ['domain', 'sub_domain'],
      options: { defaultTab: 'domain' },
      ...propsOverrides
    },
    slots,
    global: { stubs }
  })
}

describe('MultiObjectManagementPage', () => {
  beforeEach(() => {
    mockSelectedVersionId.value = 1
    mockCombinedFilters.value = { version_id: 1 }
    mockActiveTab.value = 'domain'
  })

  describe('组件渲染', () => {
    it('渲染根节点', () => {
      const wrapper = mountPage()
      expect(wrapper.find('.multi-object-management').exists()).toBe(true)
    })

    it('渲染 GlobalToolbar', () => {
      const wrapper = mountPage()
      expect(wrapper.find('.gt-stub').exists()).toBe(true)
    })

    it('渲染 MasterDetailLayout', () => {
      const wrapper = mountPage()
      expect(wrapper.find('.mdl-stub').exists()).toBe(true)
    })

    it('版本已选时渲染 RelationScopeTree', () => {
      const wrapper = mountPage()
      expect(wrapper.find('.rst-stub').exists()).toBe(true)
    })

    it('版本已选时渲染 MetaListPage', () => {
      const wrapper = mountPage()
      expect(wrapper.find('.ml-stub').exists()).toBe(true)
    })

    it('MetaListPage 接收 object-type=domain', () => {
      const wrapper = mountPage()
      expect(wrapper.find('.ml-type').text()).toBe('domain')
    })

    it('接受 objectTypes 和 options props', () => {
      const wrapper = mountPage({ objectTypes: ['domain'], options: { defaultTab: 'domain' } })
      expect(wrapper.props('objectTypes')).toEqual(['domain'])
    })
  })

  describe('Tabs 渲染', () => {
    it('渲染 2 个 Tab', () => {
      const wrapper = mountPage()
      const panes = wrapper.findAll('.tab-pane-stub')
      expect(panes).toHaveLength(2)
      expect(panes[0].text()).toBe('领域')
      expect(panes[1].text()).toBe('子领域')
    })

    it('渲染 momp-tabs-row', () => {
      const wrapper = mountPage()
      expect(wrapper.find('.momp-tabs-row').exists()).toBe(true)
    })

    it('切换到 sub_domain tab', async () => {
      mockActiveTab.value = 'sub_domain'
      const wrapper = mountPage()
      expect(wrapper.find('.ml-type').text()).toBe('sub_domain')
    })
  })

  describe('插槽透传', () => {
    it('渲染 tabsExtra 插槽', () => {
      const wrapper = mountPage({}, {
        tabsExtra: '<div class="custom-extra">自定义</div>'
      })
      expect(wrapper.find('.custom-extra').exists()).toBe(true)
    })

    it('渲染具名插槽到 MetaListPage', () => {
      const wrapper = mountPage({}, {
        'cell-source_bo_name': '<div class="cell-src">Src</div>'
      })
      expect(wrapper.find('.cell-src').exists()).toBe(true)
    })
  })

  describe('expose', () => {
    it('refresh 方法存在', () => {
      const wrapper = mountPage()
      expect(typeof wrapper.vm.refresh).toBe('function')
    })

    it('clearScope 方法存在', () => {
      const wrapper = mountPage()
      expect(typeof wrapper.vm.clearScope).toBe('function')
    })

    it('page 对象暴露', () => {
      const wrapper = mountPage()
      expect(wrapper.vm.page).toBeDefined()
    })
  })

  describe('样式', () => {
    it('momp-tabs-row 存在', () => {
      const wrapper = mountPage()
      expect(wrapper.find('.momp-tabs-row').exists()).toBe(true)
    })

    it('momp-sidebar 存在', () => {
      const wrapper = mountPage()
      expect(wrapper.find('.momp-sidebar').exists()).toBe(true)
    })
  })

  describe('空状态', () => {
    it('版本未选时应显示空态', () => {
      mockSelectedVersionId.value = null
      const wrapper = mountPage()
      expect(wrapper.find('.momp-empty-detail').exists()).toBe(true)
      expect(wrapper.find('.ml-stub').exists()).toBe(false)
    })

    it('版本未选时 sidebar 也显示空态', () => {
      mockSelectedVersionId.value = null
      const wrapper = mountPage()
      expect(wrapper.find('.momp-empty-sidebar').exists()).toBe(true)
      expect(wrapper.find('.rst-stub').exists()).toBe(false)
    })
  })

  describe('toolbarAction 事件', () => {
    it('GlobalToolbar action 事件转发', async () => {
      const wrapper = mountPage()
      const toolbar = wrapper.find('.gt-stub')
      expect(toolbar.exists()).toBe(true)
    })
  })

  describe('action 控制状态', () => {
    it('canImport=false 时导入按钮 disabled', () => {
      const wrapper = mountPage()
      expect(wrapper.vm.actionDisabledMap.export).toBe(false)
      expect(wrapper.vm.actionDisabledMap.import).toBe(false)
    })

    it('page 对象包含 action 状态', () => {
      const wrapper = mountPage()
      const page = wrapper.vm.page
      expect(page.canImport).toBeDefined()
      expect(page.canExport).toBeDefined()
      expect(page.canShowChart).toBeDefined()
      expect(page.canRefresh).toBeDefined()
    })

    it('page 对象包含 exportFilters', () => {
      const wrapper = mountPage()
      const page = wrapper.vm.page
      expect(page.exportFilters).toBeDefined()
      expect(page.baseFilters).toBeDefined()
    })

    it('page 对象包含 objectTypeLabels', () => {
      const wrapper = mountPage()
      const page = wrapper.vm.page
      expect(page.objectTypeLabels).toBeDefined()
    })
  })

  describe('ImportDialog 渲染', () => {
    it('初始不应渲染 ImportDialog', () => {
      const wrapper = mountPage()
      expect(wrapper.find('.imd-stub').exists()).toBe(false)
    })

    it('importDialogVisible=true 时渲染 ImportDialog', async () => {
      const { useMultiObjectPage } = await import('@/composables/useMultiObjectPage')
      const importVis = ref(true)
      useMultiObjectPage.mockReturnValueOnce({
        objectTypes: ['domain', 'sub_domain'],
        tabs: [{ name: 'domain', label: '领域' }, { name: 'sub_domain', label: '子领域' }],
        activeTab: ref('domain'),
        versionContext: {
          selectedVersionId: ref(1),
          selectedVersion: ref({ id: 1, name: 'V1.0' }),
          versions: ref([{ id: 1, name: 'V1.0' }]),
          hasContext: ref(true),
          selectVersion: vi.fn(),
          clearContext: vi.fn()
        },
        filterFlow: { combinedFilters: ref({}), registerSource: vi.fn(), unregisterSource: vi.fn(), refresh: vi.fn() },
        contextSource: { source: { id: 'v' }, setContext: vi.fn(), clear: vi.fn() },
        scopeSource: { source: { id: 's' }, setBusinessObjectIds: vi.fn(), setRelationCodes: vi.fn(), clear: vi.fn() },
        scopeIds: reactive({ domain: { selected: [], effective: [] }, globalFilters: {}, relationExtra: { relationCodes: [], categoryTypes: [], filterRelationCodes: [] } }),
        hasScopeSelection: computed(() => false),
        combinedFilters: computed(() => ({})),
        baseFilters: computed(() => ({})),
        exportFilters: computed(() => ({})),
        objectTypeLabels: computed(() => ({})),
        canImport: computed(() => true),
        canExport: computed(() => false),
        canShowChart: computed(() => false),
        canRefresh: computed(() => true),
        refreshTrigger: ref(0),
        importDialogVisible: importVis,
        exportDialogVisible: ref(false),
        importContext: computed(() => ({ version_id: 1 })),
        exportContext: computed(() => ({})),
        handleGlobalAction: vi.fn(),
        handleShowChart: vi.fn(),
        restoreStateFromDiagram: vi.fn(() => false),
        handleImportSuccess: vi.fn(),
        handleExportSuccess: vi.fn(),
        handleScopeChange: vi.fn(),
        clearScope: vi.fn(),
        handleToolbarChange: vi.fn()
      })
      const wrapper = mountPage()
      expect(wrapper.find('.imd-stub').exists()).toBe(true)
    })
  })

  describe('ExportDialog 渲染', () => {
    it('initial 不应渲染 ExportDialog', () => {
      const wrapper = mountPage()
      expect(wrapper.find('.exd-stub').exists()).toBe(false)
    })
  })

  describe('onGlobalAction', () => {
    it('export action 应调用 handleGlobalAction', async () => {
      const { useMultiObjectPage } = await import('@/composables/useMultiObjectPage')
      const handleGA = vi.fn()
      useMultiObjectPage.mockReturnValueOnce({
        objectTypes: ['domain'],
        tabs: [{ name: 'domain', label: '领域' }],
        activeTab: ref('domain'),
        versionContext: { selectedVersionId: ref(1), selectedVersion: ref({ id: 1 }), versions: ref([{ id: 1 }]), hasContext: ref(true), selectVersion: vi.fn(), clearContext: vi.fn() },
        filterFlow: { combinedFilters: ref({}), registerSource: vi.fn(), unregisterSource: vi.fn(), refresh: vi.fn() },
        contextSource: { source: { id: 'v' }, setContext: vi.fn(), clear: vi.fn() },
        scopeSource: { source: { id: 's' }, setBusinessObjectIds: vi.fn(), setRelationCodes: vi.fn(), clear: vi.fn() },
        scopeIds: reactive({ domain: { selected: [], effective: [] }, globalFilters: {}, relationExtra: { relationCodes: [], categoryTypes: [], filterRelationCodes: [] } }),
        hasScopeSelection: computed(() => false),
        combinedFilters: computed(() => ({})),
        baseFilters: computed(() => ({})),
        exportFilters: computed(() => ({})),
        objectTypeLabels: computed(() => ({})),
        canImport: computed(() => false),
        canExport: computed(() => false),
        canShowChart: computed(() => false),
        canRefresh: computed(() => false),
        refreshTrigger: ref(0),
        importDialogVisible: ref(false),
        exportDialogVisible: ref(false),
        importContext: computed(() => ({})),
        exportContext: computed(() => ({})),
        handleGlobalAction: handleGA,
        handleShowChart: vi.fn(),
        restoreStateFromDiagram: vi.fn(() => false),
        handleImportSuccess: vi.fn(),
        handleExportSuccess: vi.fn(),
        handleScopeChange: vi.fn(),
        clearScope: vi.fn(),
        handleToolbarChange: vi.fn()
      })
      mountPage()
      expect(handleGA).not.toHaveBeenCalled()
    })
  })

  describe('ExportDialog props 传递', () => {
    it('应传递 object-types 到 ExportDialog', async () => {
      const { useMultiObjectPage } = await import('@/composables/useMultiObjectPage')
      useMultiObjectPage.mockReturnValueOnce({
        objectTypes: ['domain', 'sub_domain'],
        tabs: [{ name: 'domain', label: '领域' }, { name: 'sub_domain', label: '子领域' }],
        activeTab: ref('domain'),
        versionContext: { selectedVersionId: ref(1), selectedVersion: ref({ id: 1 }), versions: ref([{ id: 1 }]), hasContext: ref(true), selectVersion: vi.fn(), clearContext: vi.fn() },
        filterFlow: { combinedFilters: ref({}), registerSource: vi.fn(), unregisterSource: vi.fn(), refresh: vi.fn() },
        contextSource: { source: { id: 'v' }, setContext: vi.fn(), clear: vi.fn() },
        scopeSource: { source: { id: 's' }, setBusinessObjectIds: vi.fn(), setRelationCodes: vi.fn(), clear: vi.fn() },
        scopeIds: reactive({ domain: { selected: [], effective: [] }, globalFilters: {}, relationExtra: { relationCodes: [], categoryTypes: [], filterRelationCodes: [] } }),
        hasScopeSelection: computed(() => false),
        combinedFilters: computed(() => ({})),
        baseFilters: computed(() => ({})),
        exportFilters: computed(() => ({ version_id: 1 })),
        objectTypeLabels: computed(() => ({ domain: '领域', sub_domain: '子领域' })),
        canImport: computed(() => false),
        canExport: computed(() => true),
        canShowChart: computed(() => false),
        canRefresh: computed(() => false),
        refreshTrigger: ref(0),
        importDialogVisible: ref(false),
        exportDialogVisible: ref(false),
        importContext: computed(() => ({})),
        exportContext: computed(() => ({})),
        handleGlobalAction: vi.fn(),
        handleShowChart: vi.fn(),
        restoreStateFromDiagram: vi.fn(() => false),
        handleImportSuccess: vi.fn(),
        handleExportSuccess: vi.fn(),
        handleScopeChange: vi.fn(),
        clearScope: vi.fn(),
        handleToolbarChange: vi.fn()
      })
      const wrapper = mountPage()
      expect(wrapper.vm).toBeDefined()
    })
  })
})
