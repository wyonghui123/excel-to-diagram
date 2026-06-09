import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

// Mock factories: vi.fn() 必须在 factory 内部创建以避免 hoist 问题
vi.mock('@/services/metaService', () => ({
  metaService: {
    getSchema: vi.fn(),
    getHierarchyConfig: vi.fn(),
    getImportExportConfig: vi.fn(),
    buildCascadeChain: vi.fn()
  }
}))

vi.mock('@/services/boService', () => ({
  boService: {
    exportData: vi.fn(),
    exportDataAsync: vi.fn(),
    getExportStatus: vi.fn(),
    downloadExportFile: vi.fn()
  }
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
}))

// Top-level imports（vi.mock 已被 hoist，import 自动应用 mock）
import { metaService } from '@/services/metaService'
import { boService } from '@/services/boService'
import ExportDialog from '../ExportDialog.vue'

describe('ExportDialog Component', () => {
  let wrapper

  const defaultProps = {
    visible: true,
    objectType: 'business_object'
  }

  const mockSchema = {
    id: 'business_object',
    name: '业务对象',
    hierarchy: {
      enabled: true,
      level: 5,
      parent_field: 'service_module_id'
    },
    fields: [
      { id: 'version_id', name: '版本', ui: { cascade_level: 1 } },
      { id: 'domain_id', name: '领域', ui: { cascade_level: 2, depends_on: 'version_id' } },
      { id: 'sub_domain_id', name: '子领域', ui: { cascade_level: 3, depends_on: 'domain_id' } },
      { id: 'service_module_id', name: '服务模块', ui: { cascade_level: 4, depends_on: 'sub_domain_id' } }
    ],
    import_export: {
      cascade_export: true,
      export_enabled: true
    }
  }

  // 仅 stub el-dialog（避免 portal/teleport 副作用），其他 ElementPlus 组件由 setup.js 全局插件渲染
  // 关键：stub 必须渲染 <slot />，否则 el-dialog 内部内容（包括 .export-mode / .cascade-selection 等）不会出现在 DOM
  const dialogStubs = {
    'el-dialog': { template: '<div class="el-dialog-stub"><slot /></div>' }
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount()
      wrapper = null
    }
  })

  describe('元数据驱动 - Schema 加载', () => {
    it('TC-1: 组件 visible 时调 getSchema("business_object")', async () => {
      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      wrapper = mount(ExportDialog, {
        props: defaultProps,
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      expect(metaService.getSchema).toHaveBeenCalledWith('business_object')
    })

    it('TC-2: showExportMode=true 时调 getHierarchyConfig(schema)', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })
      metaService.getHierarchyConfig.mockReturnValue({ enabled: true, level: 5 })

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, showExportMode: true },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      // 触发 hierarchyConfig computed 评估
      void wrapper.vm.hierarchyConfig

      expect(metaService.getHierarchyConfig).toHaveBeenCalledWith(mockSchema)
    })

    it('TC-3: showExportMode=true 时调 buildCascadeChain(schema)', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })
      metaService.buildCascadeChain.mockReturnValue([
        { field: 'domain_id', label: '领域', parentLabel: '版本' },
        { field: 'sub_domain_id', label: '子领域', parentLabel: '领域' }
      ])

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, showExportMode: true },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      // 主动访问 cascadeChain 以触发 buildCascadeChain spy
      void wrapper.vm.cascadeChain

      expect(metaService.buildCascadeChain).toHaveBeenCalledWith(mockSchema)
    })

    it('TC-4: getImportExportConfig 返回 cascadeExport=true 时 localExportMode=cascade', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })
      metaService.getImportExportConfig.mockReturnValue({ cascadeExport: true })

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, showExportMode: true },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      expect(wrapper.vm.localExportMode).toBe('cascade')
    })
  })

  describe('元数据驱动 - hierarchyConfig', () => {
    it('TC-5: hierarchyConfig 正确返回 {enabled, level}', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })
      metaService.getHierarchyConfig.mockReturnValue({ enabled: true, level: 5, parentField: 'service_module_id' })

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, showExportMode: true },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      expect(wrapper.vm.hierarchyConfig.enabled).toBe(true)
      expect(wrapper.vm.hierarchyConfig.level).toBe(5)
    })

    it('TC-6: schema.hierarchy.enabled=false 时 hierarchyConfig.enabled=false', async () => {
      const schemaDisabled = { ...mockSchema, hierarchy: { enabled: false } }
      metaService.getSchema.mockResolvedValue({ success: true, data: schemaDisabled })
      metaService.getHierarchyConfig.mockReturnValue({ enabled: false })

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, showExportMode: true },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      expect(wrapper.vm.hierarchyConfig.enabled).toBe(false)
    })
  })

  describe('元数据驱动 - cascadeChain', () => {
    it('TC-7: cascadeChain 从 metaService buildCascadeChain 取', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })
      metaService.buildCascadeChain.mockReturnValue([
        { field: 'domain_id', label: '领域' },
        { field: 'sub_domain_id', label: '子领域' },
        { field: 'service_module_id', label: '服务模块' }
      ])

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, showExportMode: true },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      expect(wrapper.vm.cascadeChain).toHaveLength(3)
    })

    it('TC-8: selectedCascadeFields 计算正确（默认全选）', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })
      metaService.buildCascadeChain.mockReturnValue([
        { field: 'domain_id', label: '领域' },
        { field: 'sub_domain_id', label: '子领域' }
      ])

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, showExportMode: true },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      const selectedFields = wrapper.vm.selectedCascadeFields
      expect(selectedFields).toContain('domain_id')
      expect(selectedFields).toContain('sub_domain_id')
    })
  })

  describe('元数据驱动 - objectTypeName', () => {
    it('TC-9: schema.fields[0].id 与 objectType 匹配时取 name', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, objectType: 'domain_id' },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      expect(wrapper.vm.objectTypeName).toBe('领域')
    })

    it('TC-10: 使用 prop objectTypeName（若提供）', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, objectTypeName: '自定义名称' },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      expect(wrapper.vm.objectTypeName).toBe('自定义名称')
    })

    it('TC-11: schema 中未找到时 fallback 到 schema.name', async () => {
      // 源代码逻辑：field?.name || schema.value.name || props.objectType
      // 当 field 找不到但 schema 有 name 时，返回 schema.name（不是 props.objectType）
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, objectType: 'unknown_type' },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      expect(wrapper.vm.objectTypeName).toBe('业务对象')
    })
  })

  describe('UI 渲染', () => {
    it('TC-12: showExportMode=true 且 hierarchy enabled 时显示 export-mode', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })
      metaService.getHierarchyConfig.mockReturnValue({ enabled: true })

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, showExportMode: true },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      expect(wrapper.find('.export-mode').exists()).toBe(true)
    })

    it('TC-13: localExportMode=cascade 且 cascadeChain.length>0 时显示 cascade-selection', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })
      metaService.buildCascadeChain.mockReturnValue([
        { field: 'domain_id', label: '领域' }
      ])

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, showExportMode: true },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      // 直接通过 wrapper.vm 设置 ref（<script setup> 下 setData 不可用：data proxy 不可扩展）
      wrapper.vm.localExportMode = 'cascade'
      await nextTick()

      expect(wrapper.find('.cascade-selection').exists()).toBe(true)
    })

    it('TC-14: showExportOptions=true 时显示 export-options', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, showExportOptions: true },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      expect(wrapper.find('.export-options').exists()).toBe(true)
    })

    it('TC-15: 默认 options 正确（protectSheet=false 等）', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, showExportOptions: true },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()

      expect(wrapper.vm.localOptions.includeHierarchyPath).toBe(false)
      expect(wrapper.vm.localOptions.protectSheet).toBe(false)
      expect(wrapper.vm.localOptions.markReadonly).toBe(false)
    })
  })

  describe('Export Flow', () => {
    it('TC-16: cascade mode 时 exportData API 传 selected_types', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })
      metaService.buildCascadeChain.mockReturnValue([
        { field: 'domain_id', label: '领域' }
      ])
      boService.exportData.mockResolvedValue({ success: true, total_rows: 100 })

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, showExportMode: true },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()
      wrapper.vm.localExportMode = 'cascade'
      await nextTick()
      await wrapper.vm.handleExport()

      expect(boService.exportData).toHaveBeenCalledWith(
        'business_object',
        expect.objectContaining({
          scope: 'cascade',
          selected_types: expect.arrayContaining(['domain_id'])
        })
      )
    })

    it('TC-17: showExportOptions=true 时 exportData API 传 options', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })
      boService.exportData.mockResolvedValue({ success: true, total_rows: 100 })

      wrapper = mount(ExportDialog, {
        props: { ...defaultProps, showExportOptions: true },
        global: { stubs: dialogStubs }
      })

      await flushPromises()
      await nextTick()
      await wrapper.vm.handleExport()

      expect(boService.exportData).toHaveBeenCalledWith(
        'business_object',
        expect.objectContaining({
          options: expect.objectContaining({
            include_hierarchy_path: expect.any(Boolean),
            protect_sheet: expect.any(Boolean),
            mark_readonly: expect.any(Boolean)
          })
        })
      )
    })
  })

  describe('Props and Defaults', () => {
    it('TC-18: 默认 props 正确', async () => {
      metaService.getSchema.mockResolvedValue({ success: true, data: mockSchema })

      wrapper = mount(ExportDialog, {
        props: defaultProps,
        global: { stubs: dialogStubs }
      })

      expect(wrapper.vm.visible).toBe(true)
      expect(wrapper.vm.objectType).toBe('business_object')
      expect(wrapper.vm.exportScope).toBe('current')
    })
  })
})
