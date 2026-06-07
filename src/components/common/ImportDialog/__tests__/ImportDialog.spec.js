import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { mount } from '@vue/test-utils'

vi.mock('@/services/boService', () => ({
  boService: {
    previewImport: vi.fn(),
    importDataAsync: vi.fn(),
    getImportStatus: vi.fn(),
    downloadTemplate: vi.fn()
  }
}))

vi.mock('@/services/metaService', () => ({
  metaService: {
    getSchema: vi.fn(),
    getImportExportConfig: vi.fn(),
    buildCascadeChain: vi.fn()
  }
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual('element-plus')
  return {
    ...actual,
    ElMessage: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn()
    }
  }
})

const { boService } = await import('@/services/boService')
const { metaService } = await import('@/services/metaService')

describe('ImportDialog Component', () => {
  let wrapper

  const defaultProps = {
    visible: true,
    objectType: 'business_object'
  }

  const mockSchema = {
    id: 'business_object',
    name: '业务对象',
    fields: [
      { id: 'version_id', name: '版本', ui: { cascade_level: 1 } },
      { id: 'domain_id', name: '领域', ui: { cascade_level: 2, depends_on: 'version_id' } },
      { id: 'sub_domain_id', name: '子领域', ui: { cascade_level: 3, depends_on: 'domain_id' } },
      { id: 'service_module_id', name: '服务模块', ui: { cascade_level: 4, depends_on: 'sub_domain_id' } }
    ],
    import_export: {
      import_enabled: true,
      cascade_import: true,
      conflict_strategy: 'upsert'
    }
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    if (wrapper) {
      wrapper.unmount()
    }
  })

  describe('元数据驱动 - Schema 加载', () => {
    it('should load schema from metaService on visible', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: {
          stubs: {
            'el-dialog': true,
            'el-steps': true,
            'el-step': true
          }
        }
      })

      expect(metaService.getSchema).toHaveBeenCalledWith('business_object')
    })

    it('should build cascadeChain from metaService', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      metaService.buildCascadeChain.mockReturnValue([
        { field: 'version_id', label: '版本', cascadeLevel: 1 },
        { field: 'domain_id', label: '领域', cascadeLevel: 2, dependsOn: 'version_id' },
        { field: 'sub_domain_id', label: '子领域', cascadeLevel: 3, dependsOn: 'domain_id' }
      ])

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: {
          stubs: {
            'el-dialog': true
          }
        }
      })

      await nextTick()

      const cascadeChain = wrapper.vm.cascadeChain
      expect(metaService.buildCascadeChain).toHaveBeenCalledWith(mockSchema)
      expect(cascadeChain.length).toBe(3)
    })

    it('should set conflictStrategy from schema import_export config', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      metaService.getImportExportConfig.mockReturnValue({
        conflictStrategy: 'skip'
      })

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: {
          stubs: {
            'el-dialog': true
          }
        }
      })

      await nextTick()

      expect(metaService.getImportExportConfig).toHaveBeenCalledWith(mockSchema)
    })

    it('should not reload schema if already loaded', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: {
          stubs: {
            'el-dialog': true
          }
        }
      })

      await nextTick()

      metaService.getSchema.mockClear()

      await wrapper.setProps({ visible: false })
      await wrapper.setProps({ visible: true })

      expect(metaService.getSchema).not.toHaveBeenCalled()
    })
  })

  describe('元数据驱动 - cascadeChain', () => {
    it('should compute cascadeChain correctly', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      metaService.buildCascadeChain.mockReturnValue([
        { field: 'version_id', label: '版本', cascadeLevel: 1, parentLabel: null },
        { field: 'domain_id', label: '领域', cascadeLevel: 2, parentLabel: '版本' }
      ])

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: {
          stubs: {
            'el-dialog': true
          }
        }
      })

      await nextTick()

      expect(wrapper.vm.cascadeChain).toHaveLength(2)
      expect(wrapper.vm.cascadeChain[0].label).toBe('版本')
      expect(wrapper.vm.cascadeChain[1].label).toBe('领域')
    })

    it('should filter cascadeChain by selected fields', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      metaService.buildCascadeChain.mockReturnValue([
        { field: 'version_id', label: '版本', cascadeLevel: 1 },
        { field: 'domain_id', label: '领域', cascadeLevel: 2 },
        { field: 'sub_domain_id', label: '子领域', cascadeLevel: 3 }
      ])

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: {
          stubs: {
            'el-dialog': true
          }
        }
      })

      await nextTick()

      const selectedFields = wrapper.vm.selectedCascadeFields
      expect(selectedFields).toContain('domain_id')
      expect(selectedFields).toContain('sub_domain_id')
    })
  })

  describe('元数据驱动 - objectTypeName', () => {
    it('should get objectTypeName from schema fields', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      wrapper = mount(ImportDialog, {
        props: { ...defaultProps, objectType: 'service_module_id' },
        global: {
          stubs: {
            'el-dialog': true
          }
        }
      })

      await nextTick()

      expect(wrapper.vm.objectTypeName).toBe('服务模块')
    })

    it('should fallback to schema.name if field not found', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      wrapper = mount(ImportDialog, {
        props: { ...defaultProps, objectType: 'unknown_field' },
        global: {
          stubs: {
            'el-dialog': true
          }
        }
      })

      await nextTick()

      // 真实实现：field?.name || schema.name || props.objectType
      // 当字段未找到时，fallback 到 schema.name = '业务对象'
      expect(wrapper.vm.objectTypeName).toBe('业务对象')
    })

    it('should fallback to props.objectType if no schema', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: false
      })

      wrapper = mount(ImportDialog, {
        props: { ...defaultProps, objectType: 'unknown_field' },
        global: {
          stubs: {
            'el-dialog': true
          }
        }
      })

      await nextTick()

      // schema 为 null 时，fallback 到 props.objectType
      expect(wrapper.vm.objectTypeName).toBe('unknown_field')
    })
  })

  describe('元数据驱动 - importResultsTable', () => {
    it('should get type labels from schema fields', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: {
          stubs: {
            'el-dialog': true
          }
        }
      })

      // script setup 下 setData 不可用；用直接 ref 赋值
      wrapper.vm.importResult = {
        success: true,
        results: {
          domain_id: { created: 5, updated: 2 },
          sub_domain_id: { created: 3 }
        }
      }

      await nextTick()

      const table = wrapper.vm.importResultsTable
      expect(table[0].type).toBe('领域')
      expect(table[1].type).toBe('子领域')
    })
  })

  describe('Props and Defaults', () => {
    it('should have correct default props', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: {
          stubs: {
            'el-dialog': true,
            'el-steps': true,
            'el-step': true
          }
        }
      })

      expect(wrapper.vm.visible).toBe(true)
      expect(wrapper.vm.objectType).toBe('business_object')
      expect(wrapper.vm.conflictStrategy).toBe('upsert')
    })
  })

  describe('Preview Flow', () => {
    it('should pass cascade_fields to previewImport API', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      metaService.buildCascadeChain.mockReturnValue([
        { field: 'version_id', label: '版本', cascadeLevel: 1 },
        { field: 'domain_id', label: '领域', cascadeLevel: 2 }
      ])

      boService.previewImport.mockResolvedValue({
        success: true,
        data: { sheets: [{ name: 'Sheet1', row_count: 10, hasErrors: false }] }
      })

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: {
          stubs: {
            'el-dialog': true
          }
        }
      })

      await nextTick()

      // script setup 下 setData 不可用；用直接 ref 赋值
      wrapper.vm.selectedFile = { name: 'test.xlsx' }
      await wrapper.vm.startPreview()

      await nextTick()
      expect(boService.previewImport).toHaveBeenCalledWith(
        'business_object',
        expect.any(Object),
        expect.objectContaining({
          cascade_fields: expect.arrayContaining(['domain_id'])
        })
      )
    })
  })

  describe('Import Flow', () => {
    it('should pass cascade_fields to importDataAsync API', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      // 显式重置——避免其他测试的 mockReturnValue 副作用
      metaService.getImportExportConfig.mockReturnValue(undefined)

      metaService.buildCascadeChain.mockReturnValue([
        { field: 'domain_id', label: '领域', cascadeLevel: 2 }
      ])

      boService.importDataAsync.mockResolvedValue({
        success: true,
        data: { task_id: 'task-123' }
      })

      boService.getImportStatus.mockResolvedValue({
        success: true,
        data: { status: 'completed', progress: 100, result: { results: {} } }
      })

      wrapper = mount(ImportDialog, {
        props: { ...defaultProps, context: { version_id: 1 } },
        global: {
          stubs: {
            'el-dialog': true
          }
        }
      })

      await nextTick()

      // script setup 下 setData 不可用；用直接 ref 赋值
      wrapper.vm.selectedFile = { name: 'test.xlsx' }
      wrapper.vm.previewResult = { sheets: [{ row_count: 10 }] }

      await wrapper.vm.startImport()

      await nextTick()
      expect(boService.importDataAsync).toHaveBeenCalledWith(
        expect.any(Object),
        'upsert',
        expect.objectContaining({
          cascade_fields: expect.arrayContaining(['domain_id']),
          version_id: 1
        })
      )
    })
  })

  describe('Computed Properties', () => {
    it('should compute dialogTitle correctly', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: { stubs: { 'el-dialog': true } }
      })

      expect(wrapper.vm.dialogTitle).toBe('导入数据')

      // script setup 下 setData 不可用；用直接 ref 赋值
      wrapper.vm.currentStep = 1
      await nextTick()
      expect(wrapper.vm.dialogTitle).toBe('数据校验')

      wrapper.vm.currentStep = 2
      await nextTick()
      expect(wrapper.vm.dialogTitle).toBe('导入结果')
    })

    it('should compute progressColor correctly', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: { stubs: { 'el-dialog': true } }
      })

      wrapper.vm.importProgress = 30
      await nextTick()
      expect(wrapper.vm.progressColor).toContain('#ea580c')

      wrapper.vm.importProgress = 60
      await nextTick()
      expect(wrapper.vm.progressColor).toContain('#e6a23c')

      wrapper.vm.importProgress = 90
      await nextTick()
      expect(wrapper.vm.progressColor).toContain('#67c23a')
    })
  })

  describe('Step Navigation', () => {
    it('should navigate steps correctly', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: { stubs: { 'el-dialog': true } }
      })

      // script setup 下 setData 不可用；用直接 ref 赋值
      wrapper.vm.currentStep = 2
      wrapper.vm.prevStep()
      expect(wrapper.vm.currentStep).toBe(1)

      wrapper.vm.prevStep()
      expect(wrapper.vm.currentStep).toBe(0)

      wrapper.vm.prevStep()
      expect(wrapper.vm.currentStep).toBe(0)
    })
  })

  describe('File Handling', () => {
    it('should handle file selection', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: { stubs: { 'el-dialog': true } }
      })

      const mockFile = { name: 'test.xlsx', raw: {} }
      wrapper.vm.handleFileChange(mockFile)

      expect(wrapper.vm.selectedFile).toEqual({})
      expect(wrapper.vm.fileList).toHaveLength(1)
    })

    it('should clear file on remove', async () => {
      const { default: ImportDialog } = await import('../ImportDialog.vue')

      metaService.getSchema.mockResolvedValue({
        success: true,
        data: mockSchema
      })

      wrapper = mount(ImportDialog, {
        props: defaultProps,
        global: { stubs: { 'el-dialog': true } }
      })

      // script setup 下 setData 不可用；用直接 ref 赋值
      wrapper.vm.selectedFile = { name: 'test.xlsx' }
      wrapper.vm.fileList = [{ name: 'test.xlsx' }]

      wrapper.vm.handleFileRemove()
      expect(wrapper.vm.selectedFile).toBeNull()
      expect(wrapper.vm.fileList).toHaveLength(0)
    })
  })
})
