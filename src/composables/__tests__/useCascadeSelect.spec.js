import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useCascadeSelect, useFormCascade } from '../useCascadeSelect'

vi.mock('@/services/boService', () => ({
  boService: {
    read: vi.fn()
  }
}))

const { boService } = await import('@/services/boService')

describe('useCascadeSelect', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('getDownstreamFields', () => {
    it('should return empty array for non-cascade field', () => {
      const metaObject = ref({
        cascade_select: []
      })
      
      const cascade = useCascadeSelect(metaObject)
      const result = cascade.getDownstreamFields('name')
      
      expect(result).toEqual([])
    })

    it('should return direct children fields', () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'version_id', parent_object: 'version', filter_by: 'product_id' },
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' },
          { field: 'sub_domain_id', parent_object: 'sub_domain', filter_by: 'domain_id' },
          { field: 'service_module_id', parent_object: 'service_module', filter_by: 'sub_domain_id' }
        ]
      })
      
      const cascade = useCascadeSelect(metaObject)
      
      expect(cascade.getDownstreamFields('version_id')).toContain('domain_id')
      expect(cascade.getDownstreamFields('domain_id')).toContain('sub_domain_id')
      expect(cascade.getDownstreamFields('sub_domain_id')).toContain('service_module_id')
    })

    it('should return all nested children fields', () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'version_id', parent_object: 'version', filter_by: 'product_id' },
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' },
          { field: 'sub_domain_id', parent_object: 'sub_domain', filter_by: 'domain_id' },
          { field: 'service_module_id', parent_object: 'service_module', filter_by: 'sub_domain_id' }
        ]
      })
      
      const cascade = useCascadeSelect(metaObject)
      const downstream = cascade.getDownstreamFields('version_id')
      
      expect(downstream).toContain('domain_id')
      expect(downstream).toContain('sub_domain_id')
      expect(downstream).toContain('service_module_id')
      expect(downstream.length).toBe(3)
    })

    it('should not return parent fields', () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'version_id', parent_object: 'version', filter_by: 'product_id' },
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' }
        ]
      })
      
      const cascade = useCascadeSelect(metaObject)
      const downstream = cascade.getDownstreamFields('domain_id')
      
      expect(downstream).not.toContain('version_id')
    })
  })

  describe('inferParentFields', () => {
    it('should return error for non-cascade field', async () => {
      const metaObject = ref({
        cascade_select: []
      })
      
      const cascade = useCascadeSelect(metaObject)
      const result = await cascade.inferParentFields('name', 123)
      
      expect(result.success).toBe(false)
      expect(result.message).toBe('字段未配置级联')
    })

    it('should infer parent fields recursively', async () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'version_id', parent_object: 'version', filter_by: 'product_id' },
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' },
          { field: 'sub_domain_id', parent_object: 'sub_domain', filter_by: 'domain_id' },
          { field: 'service_module_id', parent_object: 'service_module', filter_by: 'sub_domain_id' }
        ]
      })
      
      const mockedRead = vi.mocked(boService.read)
      mockedRead
        .mockResolvedValueOnce({ success: true, data: { id: 10, sub_domain_id: 5 } })
        .mockResolvedValueOnce({ success: true, data: { id: 5, domain_id: 1 } })
        .mockResolvedValueOnce({ success: true, data: { id: 1, version_id: 100 } })
      
      const cascade = useCascadeSelect(metaObject)
      const result = await cascade.inferParentFields('service_module_id', 10)
      
      expect(result.success).toBe(true)
      expect(result.data.service_module_id).toBe(10)
      expect(result.data.sub_domain_id).toBe(5)
      expect(result.data.domain_id).toBe(1)
      expect(result.data.version_id).toBe(100)
    })

    it('should handle read failure', async () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' }
        ]
      })
      
      const mockedRead = vi.mocked(boService.read)
      mockedRead.mockResolvedValueOnce({ success: false, message: 'Not found' })
      
      const cascade = useCascadeSelect(metaObject)
      const result = await cascade.inferParentFields('domain_id', 999)
      
      expect(result.success).toBe(false)
      expect(result.message).toBe('Not found')
    })

    it('should handle network error', async () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' }
        ]
      })
      
      const mockedRead = vi.mocked(boService.read)
      mockedRead.mockRejectedValueOnce(new Error('Network error'))
      
      const cascade = useCascadeSelect(metaObject)
      const result = await cascade.inferParentFields('domain_id', 1)
      
      expect(result.success).toBe(false)
      expect(result.message).toBe('Network error')
    })

    it('should return only current field when no parent exists', async () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'version_id', parent_object: 'version', filter_by: 'product_id' }
        ]
      })
      
      const mockedRead = vi.mocked(boService.read)
      mockedRead.mockResolvedValueOnce({ success: true, data: { id: 1 } })
      
      const cascade = useCascadeSelect(metaObject)
      const result = await cascade.inferParentFields('version_id', 1)
      
      expect(result.success).toBe(true)
      expect(result.data.version_id).toBe(1)
      expect(Object.keys(result.data).length).toBe(1)
    })
  })

  describe('cascadeChain', () => {
    it('should build cascade chain from config', () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id', parent_display_field: 'name' }
        ]
      })
      
      const cascade = useCascadeSelect(metaObject)
      const chain = cascade.cascadeChain.value
      
      expect(chain.domain_id).toBeDefined()
      expect(chain.domain_id.field).toBe('domain_id')
      expect(chain.domain_id.parentObject).toBe('domain')
      expect(chain.domain_id.parentField).toBe('version_id')
      expect(chain.domain_id.displayField).toBe('name')
    })

    it('should use default displayField when not specified', () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' }
        ]
      })
      
      const cascade = useCascadeSelect(metaObject)
      const chain = cascade.cascadeChain.value
      
      expect(chain.domain_id.displayField).toBe('name')
    })
  })

  describe('cascadeFields', () => {
    it('should return list of cascade field ids', () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'version_id', parent_object: 'version', filter_by: 'product_id' },
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' }
        ]
      })
      
      const cascade = useCascadeSelect(metaObject)
      
      expect(cascade.cascadeFields.value).toContain('version_id')
      expect(cascade.cascadeFields.value).toContain('domain_id')
    })
  })

  describe('parentFields', () => {
    it('should return list of parent field names', () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'version_id', parent_object: 'version', filter_by: 'product_id' },
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' }
        ]
      })
      
      const cascade = useCascadeSelect(metaObject)
      
      expect(cascade.parentFields.value).toContain('product_id')
      expect(cascade.parentFields.value).toContain('version_id')
    })
  })

  describe('loadCascadeOptions is removed', () => {
    it('should not expose loadCascadeOptions', () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' }
        ]
      })
      
      const cascade = useCascadeSelect(metaObject)
      
      expect(cascade.loadCascadeOptions).toBeUndefined()
    })

    it('should not expose loadAllCascadeOptions', () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' }
        ]
      })
      
      const cascade = useCascadeSelect(metaObject)
      
      expect(cascade.loadAllCascadeOptions).toBeUndefined()
    })
  })

  describe('clearAllDownstream with formData', () => {
    it('should clear formData values for downstream fields', () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'version_id', parent_object: 'version', filter_by: 'product_id' },
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' },
          { field: 'sub_domain_id', parent_object: 'sub_domain', filter_by: 'domain_id' }
        ]
      })
      
      const cascade = useCascadeSelect(metaObject)
      const formData = ref({
        version_id: 1,
        domain_id: 5,
        sub_domain_id: 10,
        name: 'test'
      })
      
      cascade.clearAllDownstream('version_id', formData.value)
      
      expect(formData.value.version_id).toBeNull()
      expect(formData.value.domain_id).toBeNull()
      expect(formData.value.sub_domain_id).toBeNull()
      expect(formData.value.name).toBe('test')
    })

    it('should not clear formData when formData is not provided', () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' }
        ]
      })
      
      const cascade = useCascadeSelect(metaObject)
      
      expect(() => cascade.clearAllDownstream('version_id')).not.toThrow()
    })

    it('should not modify formData for non-existing keys', () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' }
        ]
      })
      
      const cascade = useCascadeSelect(metaObject)
      const formData = ref({})
      
      cascade.clearAllDownstream('version_id', formData.value)
      
      expect(formData.value).toEqual({})
    })
  })

  describe('useFormCascade', () => {
    it('should return only cascadeFields, isCascadeField, getParentField, initialize', () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' }
        ]
      })
      const formData = ref({ version_id: 1, domain_id: 5 })
      
      const result = useFormCascade(metaObject, formData)
      
      expect(result.cascadeFields).toBeDefined()
      expect(result.isCascadeField).toBeDefined()
      expect(result.getParentField).toBeDefined()
      expect(result.initialize).toBeDefined()
      expect(result.loadCascadeOptions).toBeUndefined()
      expect(result.loadAllCascadeOptions).toBeUndefined()
      expect(Object.keys(result).length).toBe(4)
    })

    it('should not throw when cascade_select is empty', async () => {
      const metaObject = ref({})
      const formData = ref({})
      
      const result = useFormCascade(metaObject, formData)
      
      await expect(result.initialize()).resolves.toBeUndefined()
    })

    it('should not throw when metaObject has no cascade_select', () => {
      const metaObject = ref({ cascade_select: [] })
      const formData = ref({})
      
      expect(() => useFormCascade(metaObject, formData)).not.toThrow()
    })

    it('should infer parent fields on initialize', async () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' },
          { field: 'sub_domain_id', parent_object: 'sub_domain', filter_by: 'domain_id' }
        ]
      })
      const formData = ref({ sub_domain_id: 10, domain_id: null, version_id: null })
      
      const mockedRead = vi.mocked(boService.read)
      mockedRead
        .mockResolvedValueOnce({ success: true, data: { id: 10, domain_id: 5 } })
        .mockResolvedValueOnce({ success: true, data: { id: 5, version_id: 1 } })
      
      const result = useFormCascade(metaObject, formData)
      await result.initialize()
      
      expect(formData.value.sub_domain_id).toBe(10)
      expect(formData.value.domain_id).toBe(5)
      expect(formData.value.version_id).toBe(1)
    })

    it('should not fail when formData has null values', async () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' }
        ]
      })
      const formData = ref({ version_id: null, domain_id: null })
      
      const result = useFormCascade(metaObject, formData)
      await expect(result.initialize()).resolves.toBeUndefined()
    })
  })

  describe('watchParentChanges integration', () => {
    it('should call clearAllDownstream when parent changes', async () => {
      const metaObject = ref({
        cascade_select: [
          { field: 'domain_id', parent_object: 'domain', filter_by: 'version_id' }
        ]
      })
      const formData = ref({ version_id: 1, domain_id: 5 })
      
      const cascade = useCascadeSelect(metaObject)
      const callback = vi.fn()
      
      cascade.watchParentChanges(formData, callback)
      
      await nextTick()
      await nextTick()
      
      formData.value = { version_id: 2, domain_id: 5 }
      
      await nextTick()
      await nextTick()
      
      expect(callback).toHaveBeenCalledWith('domain_id', 2)
    })
  })
})
