/**
 * metaService.spec.js - Meta Service 单元测试
 *
 * 测试 metaService 单例的所有公开方法：
 * - 缓存与同步访问: getViewConfigSync, getChildSections
 * - UI Config 解析器: getFieldsByGroup / getRequiredFields / getEditableFields
 *                       getAssociationsByType / getActionsByCategory
 *                       getConstraintsByField / getRulesByState
 * - Schema 解析器:   getImportExportConfig / getCascadeFields / getHierarchyConfig
 *                     getChildObjectTypes / getParentObjectTypes / buildCascadeChain
 * - 关系/层级辅助:    getParentChildRelations / getChildObjectTypes (objectType)
 *                     getParentIdField
 * - 异步方法:         getChildSectionsAsync
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// 必须先 mock auth store 和 api util，再 import metaService
vi.mock('@/stores/authStore', () => ({
  useAuthStore: () => ({
    token: 'test-token',
    isAuthenticated: true,
    getAuthHeaders: () => ({ Authorization: 'Bearer test-token' })
  })
}))

vi.mock('@/utils/api', () => ({
  API_BASE: '/api/v1',
  API_BASE_V2: '/api/v2',
  getHeaders: () => ({ 'Content-Type': 'application/json' }),
  getAuthHeaders: () => ({ Authorization: 'Bearer test-token' })
}))

import { metaService } from '../metaService'

function createMockResponse(data, ok = true, status = 200) {
  return {
    ok,
    status,
    headers: new Headers({ 'content-type': 'application/json' }),
    json: () => Promise.resolve(data)
  }
}

function createSuccessResponse(data) {
  return createMockResponse({ success: true, data })
}

function createErrorResponse(message, status = 400) {
  return createMockResponse({ success: false, message }, false, status)
}

describe('MetaService (singleton)', () => {
  const mockSchema = {
    id: 'business_object',
    name: '业务对象',
    hierarchy: {
      enabled: true,
      hierarchy_id: 'biz_hierarchy',
      level: 5,
      parent_field: 'service_module_id',
      path_field: 'hierarchy_path',
      depth_field: 'hierarchy_depth'
    },
    fields: [
      { id: 'id', name: 'ID', ui: { cascade_level: null } },
      { id: 'version_id', name: '版本', ui: { cascade_level: 1 } },
      { id: 'domain_id', name: '领域', ui: { cascade_level: 2, depends_on: 'version_id', relation: 'domain' } },
      { id: 'sub_domain_id', name: '子领域', ui: { cascade_level: 3, depends_on: 'domain_id', relation: 'sub_domain' } },
      { id: 'service_module_id', name: '服务模块', ui: { cascade_level: 4, depends_on: 'sub_domain_id', relation: 'service_module' } },
      { id: 'name', name: '名称', ui: { cascade_level: null } },
      { id: 'code', name: '编码', ui: { cascade_level: null } }
    ],
    import_export: {
      import_enabled: true,
      export_enabled: true,
      cascade_export: true,
      cascade_import: true,
      conflict_strategy: 'upsert',
      conflict_key: 'code'
    }
  }

  const mockUIConfig = {
    fields: [
      { id: 'name', name: '名称', group: 'basic', required: true, readonly: false },
      { id: 'code', name: '编码', group: 'basic', required: false, readonly: true },
      { id: 'desc', name: '描述', group: 'extra', required: false, readonly: false }
    ],
    associations: [
      { id: 'a1', type: 'many_to_many' },
      { id: 'a2', type: 'reference' },
      { id: 'a3', type: 'composition' },
      { id: 'a4', type: 'reference' }
    ],
    actions: [
      { id: 'create', category: 'general' },
      { id: 'delete', category: 'destructive' },
      { id: 'archive', category: 'general' }
    ],
    constraints: [
      { id: 'c1', field: 'name' },
      { id: 'c2', field: 'name' },
      { id: 'c3', field: 'code' }
    ],
    rules: [
      { id: 'r1', from_state: 'draft' },
      { id: 'r2', from_state: 'draft' },
      { id: 'r3', from_state: 'active' },
      { id: 'r4' } // 无 from_state,应被忽略
    ]
  }

  beforeEach(() => {
    // 每次测试前清空缓存，确保测试隔离
    metaService.clearCache()
  })

  // ========== getViewConfigSync ==========
  describe('getViewConfigSync', () => {
    it('should return null when not cached', () => {
      const result = metaService.getViewConfigSync('business_object')
      expect(result).toBeNull()
    })

    it('should return cached view-config by viewName', () => {
      const cached = { success: true, data: { ui_view_config: {} } }
      metaService._setCache('business_object:view-config:default', cached)

      const result = metaService.getViewConfigSync('business_object')
      expect(result).toEqual(cached)
    })

    it('should use different cache keys for different viewNames', () => {
      const cachedA = { success: true, data: { name: 'A' } }
      const cachedB = { success: true, data: { name: 'B' } }
      metaService._setCache('business_object:view-config:mobile', cachedA)
      metaService._setCache('business_object:view-config:desktop', cachedB)

      expect(metaService.getViewConfigSync('business_object', 'mobile').data.name).toBe('A')
      expect(metaService.getViewConfigSync('business_object', 'desktop').data.name).toBe('B')
    })
  })

  // ========== getFieldsByGroup ==========
  describe('getFieldsByGroup', () => {
    it('should group fields by their group attribute', () => {
      const groups = metaService.getFieldsByGroup(mockUIConfig)
      expect(groups.basic).toHaveLength(2)
      expect(groups.extra).toHaveLength(1)
    })

    it('should return empty object when uiConfig has no fields', () => {
      expect(metaService.getFieldsByGroup({})).toEqual({})
      expect(metaService.getFieldsByGroup(null)).toEqual({})
    })

    it('should default missing group to "default"', () => {
      const cfg = { fields: [{ id: 'f1' }, { id: 'f2', group: 'g1' }] }
      const groups = metaService.getFieldsByGroup(cfg)
      expect(groups.default).toHaveLength(1)
      expect(groups.g1).toHaveLength(1)
    })
  })

  // ========== getRequiredFields ==========
  describe('getRequiredFields', () => {
    it('should return only required fields', () => {
      const required = metaService.getRequiredFields(mockUIConfig)
      expect(required).toHaveLength(1)
      expect(required[0].id).toBe('name')
    })

    it('should return empty array when no fields or all optional', () => {
      expect(metaService.getRequiredFields(null)).toEqual([])
      expect(metaService.getRequiredFields({ fields: [{ id: 'a', required: false }] })).toEqual([])
    })
  })

  // ========== getEditableFields ==========
  describe('getEditableFields', () => {
    it('should return only non-readonly fields', () => {
      const editable = metaService.getEditableFields(mockUIConfig)
      expect(editable).toHaveLength(2)
      expect(editable.every(f => !f.readonly)).toBe(true)
    })

    it('should return empty array when no fields or all readonly', () => {
      expect(metaService.getEditableFields(null)).toEqual([])
      expect(metaService.getEditableFields({ fields: [{ id: 'a', readonly: true }] })).toEqual([])
    })
  })

  // ========== getAssociationsByType ==========
  describe('getAssociationsByType', () => {
    it('should bucket associations by type', () => {
      const result = metaService.getAssociationsByType(mockUIConfig)
      expect(result.manyToMany).toHaveLength(1)
      expect(result.reference).toHaveLength(2)
      expect(result.composition).toHaveLength(1)
    })

    it('should return empty buckets when no associations', () => {
      const result = metaService.getAssociationsByType({})
      expect(result).toEqual({ manyToMany: [], reference: [], composition: [] })
      expect(metaService.getAssociationsByType(null)).toEqual({ manyToMany: [], reference: [], composition: [] })
    })
  })

  // ========== getActionsByCategory ==========
  describe('getActionsByCategory', () => {
    it('should group actions by category', () => {
      const cats = metaService.getActionsByCategory(mockUIConfig)
      expect(cats.general).toHaveLength(2)
      expect(cats.destructive).toHaveLength(1)
    })

    it('should return empty object when no actions', () => {
      expect(metaService.getActionsByCategory({})).toEqual({})
      expect(metaService.getActionsByCategory(null)).toEqual({})
    })
  })

  // ========== getConstraintsByField ==========
  describe('getConstraintsByField', () => {
    it('should group constraints by field', () => {
      const byField = metaService.getConstraintsByField(mockUIConfig)
      expect(byField.name).toHaveLength(2)
      expect(byField.code).toHaveLength(1)
    })

    it('should return empty object when no constraints', () => {
      expect(metaService.getConstraintsByField({})).toEqual({})
      expect(metaService.getConstraintsByField(null)).toEqual({})
    })
  })

  // ========== getRulesByState ==========
  describe('getRulesByState', () => {
    it('should group rules by from_state', () => {
      const byState = metaService.getRulesByState(mockUIConfig)
      expect(byState.draft).toHaveLength(2)
      expect(byState.active).toHaveLength(1)
    })

    it('should ignore rules without from_state', () => {
      const byState = metaService.getRulesByState(mockUIConfig)
      // r4 没有 from_state,应被过滤掉
      const totalRules = Object.values(byState).reduce((sum, arr) => sum + arr.length, 0)
      expect(totalRules).toBe(3)
    })

    it('should return empty object when no rules', () => {
      expect(metaService.getRulesByState({})).toEqual({})
      expect(metaService.getRulesByState(null)).toEqual({})
    })
  })

  // ========== getImportExportConfig ==========
  describe('getImportExportConfig', () => {
    it('should return correct import export config', () => {
      const config = metaService.getImportExportConfig(mockSchema)

      expect(config.importEnabled).toBe(true)
      expect(config.exportEnabled).toBe(true)
      expect(config.cascadeExport).toBe(true)
      expect(config.cascadeImport).toBe(true)
      expect(config.conflictStrategy).toBe('upsert')
      expect(config.conflictKey).toBe('code')
    })

    it('should return defaults for missing config', () => {
      const schemaWithoutConfig = { id: 'test' }
      const config = metaService.getImportExportConfig(schemaWithoutConfig)

      expect(config.importEnabled).toBe(true)
      expect(config.exportEnabled).toBe(true)
      expect(config.cascadeExport).toBe(false)
      expect(config.conflictStrategy).toBe('upsert')
    })

    it('should return null for null schema', () => {
      const config = metaService.getImportExportConfig(null)
      expect(config).toBeNull()
    })
  })

  // ========== getCascadeFields ==========
  describe('getCascadeFields', () => {
    it('should return cascade fields sorted by level', () => {
      const cascadeFields = metaService.getCascadeFields(mockSchema)

      expect(cascadeFields).toHaveLength(4)
      expect(cascadeFields[0].field).toBe('version_id')
      expect(cascadeFields[0].cascadeLevel).toBe(1)
      expect(cascadeFields[1].field).toBe('domain_id')
      expect(cascadeFields[2].field).toBe('sub_domain_id')
      expect(cascadeFields[3].field).toBe('service_module_id')
    })

    it('should extract correct field properties', () => {
      const cascadeFields = metaService.getCascadeFields(mockSchema)
      const domainField = cascadeFields.find(f => f.field === 'domain_id')

      expect(domainField.label).toBe('领域')
      expect(domainField.dependsOn).toBe('version_id')
      expect(domainField.cascadeGroup).toBeUndefined()
      expect(domainField.relation).toBe('domain')
    })

    it('should return empty array for schema without cascade fields', () => {
      const schema = { id: 'test', fields: [{ id: 'name', ui: {} }] }
      const cascadeFields = metaService.getCascadeFields(schema)

      expect(cascadeFields).toHaveLength(0)
    })

    it('should return empty array for null schema', () => {
      const cascadeFields = metaService.getCascadeFields(null)
      expect(cascadeFields).toHaveLength(0)
    })
  })

  // ========== getChildSections (sync, uses cache) ==========
  describe('getChildSections', () => {
    it('should return child_sections from cached view-config', () => {
      const sections = [{ id: 'sec1' }, { id: 'sec2' }]
      metaService._setCache('business_object:view-config:default', {
        success: true,
        data: { ui_view_config: { child_sections: sections } }
      })

      const result = metaService.getChildSections('business_object')
      expect(result).toEqual(sections)
    })

    it('should return empty array when not cached and no view-config', () => {
      const result = metaService.getChildSections('business_object')
      expect(result).toEqual([])
    })
  })

  // ========== getChildSectionsAsync ==========
  describe('getChildSectionsAsync', () => {
    afterEach(() => {
      vi.unstubAllGlobals()
    })

    it('should return child_sections from view-config via cache', async () => {
      const sections = [{ id: 'secA' }]
      metaService._setCache('business_object:view-config:default', {
        success: true,
        data: { ui_view_config: { child_sections: sections } }
      })

      const result = await metaService.getChildSectionsAsync('business_object')
      expect(result).toEqual(sections)
    })

    it('should fetch from API when cache miss and return child_sections', async () => {
      const sections = [{ id: 'secFromApi' }]
      const mockFetch = vi.fn().mockResolvedValue(
        createSuccessResponse({ ui_view_config: { child_sections: sections } })
      )
      vi.stubGlobal('fetch', mockFetch)

      const result = await metaService.getChildSectionsAsync('business_object')

      expect(result).toEqual(sections)
      expect(mockFetch).toHaveBeenCalledTimes(1)
      const url = mockFetch.mock.calls[0][0]
      expect(url).toContain('/meta/business_object/view-config/default')
    })

    it('should return empty array when API response has no child_sections', async () => {
      const mockFetch = vi.fn().mockResolvedValue(
        createSuccessResponse({ ui_view_config: {} })
      )
      vi.stubGlobal('fetch', mockFetch)

      const result = await metaService.getChildSectionsAsync('business_object')
      expect(result).toEqual([])
    })

    it('should return empty array when API call fails', async () => {
      const mockFetch = vi.fn().mockResolvedValue(
        createErrorResponse('not found', 404)
      )
      vi.stubGlobal('fetch', mockFetch)

      const result = await metaService.getChildSectionsAsync('business_object')
      expect(result).toEqual([])
    })
  })

  // ========== getParentChildRelations ==========
  describe('getParentChildRelations', () => {
    it('should return only parent_child type relations from cache', () => {
      metaService._setCache('business_object:view-config:default', {
        success: true,
        data: {
          relations: [
            { id: 'r1', type: 'parent_child', target: 'child_a' },
            { id: 'r2', type: 'reference', target: 'ref_b' },
            { id: 'r3', type: 'parent_child', target: 'child_c' }
          ]
        }
      })

      const result = metaService.getParentChildRelations('business_object')
      expect(result).toHaveLength(2)
      expect(result.every(r => r.type === 'parent_child')).toBe(true)
    })

    it('should return empty array when no cached relations', () => {
      const result = metaService.getParentChildRelations('business_object')
      expect(result).toEqual([])
    })
  })

  // 注意: 源码中 getChildObjectTypes(objectType) 和 getChildObjectTypes(schema) 是两个同名方法。
  // JavaScript 中后者会覆盖前者,运行时实际可用的是 schema 版本(由 hierarchy 推导)。
  // 因此这里只测试 schema 版本(在下方 "from schema hierarchy" describe 中)。

  // ========== getParentIdField ==========
  describe('getParentIdField', () => {
    it('should return default field name when no child meta cached', () => {
      const result = metaService.getParentIdField('business_object', 'child_a')
      expect(result).toBe('business_object_id')
    })

    it('should return matching field id from child fields by ui.relation', () => {
      metaService._setCache('child_a:view-config:default', {
        success: true,
        data: {
          fields: [
            { id: 'a_name', name: 'A Name' },
            { id: 'biz_id', name: '业务ID', ui: { relation: 'business_object' } }
          ]
        }
      })

      const result = metaService.getParentIdField('business_object', 'child_a')
      expect(result).toBe('biz_id')
    })

    it('should return matching field id by semantics.meaning', () => {
      metaService._setCache('child_b:view-config:default', {
        success: true,
        data: {
          fields: [
            { id: 'parent_bo', name: '父业务', semantics: { meaning: 'business_object_id' } }
          ]
        }
      })

      const result = metaService.getParentIdField('business_object', 'child_b')
      expect(result).toBe('parent_bo')
    })
  })

  // ========== getHierarchyConfig ==========
  describe('getHierarchyConfig', () => {
    it('should return correct hierarchy config', () => {
      const config = metaService.getHierarchyConfig(mockSchema)

      expect(config.enabled).toBe(true)
      expect(config.hierarchyId).toBe('biz_hierarchy')
      expect(config.level).toBe(5)
      expect(config.parentField).toBe('service_module_id')
      expect(config.pathField).toBe('hierarchy_path')
      expect(config.depthField).toBe('hierarchy_depth')
    })

    it('should return null for schema without hierarchy', () => {
      const schema = { id: 'test' }
      const config = metaService.getHierarchyConfig(schema)

      expect(config).toBeNull()
    })

    it('should return null for null schema', () => {
      const config = metaService.getHierarchyConfig(null)
      expect(config).toBeNull()
    })
  })

  // ========== getChildObjectTypes (schema - hierarchy) ==========
  describe('getChildObjectTypes (from schema hierarchy)', () => {
    it('should return child object type from parent field', () => {
      const childTypes = metaService.getChildObjectTypes(mockSchema)

      expect(childTypes).toEqual(['service_module'])
    })

    it('should return empty array if no parent field defined', () => {
      const schema = {
        hierarchy: { enabled: true }
      }
      const childTypes = metaService.getChildObjectTypes(schema)

      expect(childTypes).toHaveLength(0)
    })

    it('should return empty array for null schema', () => {
      const childTypes = metaService.getChildObjectTypes(null)
      expect(childTypes).toHaveLength(0)
    })
  })

  // ========== getParentObjectTypes ==========
  describe('getParentObjectTypes', () => {
    it('should return parent object types only for fields with defined relation', () => {
      // 实际行为:
      // - version_id 被 .filter(f => f.dependsOn) 过滤(无 depends_on)
      // - domain_id 的 depends_on=version_id, version_id.ui.relation=undefined, 被 .filter(item => item.objectType) 过滤
      // - sub_domain_id 的 depends_on=domain_id, relation='domain' → 保留
      // - service_module_id 的 depends_on=sub_domain_id, relation='sub_domain' → 保留
      const parentTypes = metaService.getParentObjectTypes(mockSchema)

      expect(parentTypes).toHaveLength(2)
      expect(parentTypes[0]).toEqual({ field: 'domain_id', objectType: 'domain' })
      expect(parentTypes[1]).toEqual({ field: 'sub_domain_id', objectType: 'sub_domain' })
    })

    it('should return empty array for null schema', () => {
      const parentTypes = metaService.getParentObjectTypes(null)
      expect(parentTypes).toHaveLength(0)
    })

    it('should return empty array when no cascade fields have defined parent relations', () => {
      const schema = {
        fields: [
          { id: 'a', name: 'A', ui: { cascade_level: 1 } },
          { id: 'b', name: 'B', ui: { cascade_level: 2, depends_on: 'a' } } // a.ui.relation is undefined
        ]
      }
      const parentTypes = metaService.getParentObjectTypes(schema)
      expect(parentTypes).toEqual([])
    })
  })

  // ========== buildCascadeChain ==========
  describe('buildCascadeChain', () => {
    it('should build correct cascade chain', () => {
      const chain = metaService.buildCascadeChain(mockSchema)

      expect(chain).toHaveLength(4)

      // version_id: 顶层, 无 dependsOn
      expect(chain[0]).toEqual({
        field: 'version_id',
        label: '版本',
        parentField: undefined,
        parentObject: undefined,
        parentLabel: undefined,
        cascadeLevel: 1,
        cascadeGroup: undefined,
        displayField: 'name'
      })

      // domain_id: 依赖 version_id; version_id.ui.relation 未定义, 所以 parentObject=undefined
      expect(chain[1]).toEqual({
        field: 'domain_id',
        label: '领域',
        parentField: 'version_id',
        parentObject: undefined,
        parentLabel: '版本',
        cascadeLevel: 2,
        cascadeGroup: undefined,
        displayField: 'name'
      })

      // sub_domain_id: 依赖 domain_id; domain_id.ui.relation='domain'
      expect(chain[2]).toEqual({
        field: 'sub_domain_id',
        label: '子领域',
        parentField: 'domain_id',
        parentObject: 'domain',
        parentLabel: '领域',
        cascadeLevel: 3,
        cascadeGroup: undefined,
        displayField: 'name'
      })

      // service_module_id: 依赖 sub_domain_id; sub_domain_id.ui.relation='sub_domain'
      expect(chain[3]).toEqual({
        field: 'service_module_id',
        label: '服务模块',
        parentField: 'sub_domain_id',
        parentObject: 'sub_domain',
        parentLabel: '子领域',
        cascadeLevel: 4,
        cascadeGroup: undefined,
        displayField: 'name'
      })
    })

    it('should use name as default displayField', () => {
      const chain = metaService.buildCascadeChain(mockSchema)

      expect(chain.every(item => item.displayField === 'name')).toBe(true)
    })

    it('should return empty array for null schema', () => {
      const chain = metaService.buildCascadeChain(null)
      expect(chain).toHaveLength(0)
    })

    it('should return empty array for schema without cascade fields', () => {
      const schema = {
        fields: [
          { id: 'name', ui: {} }
        ]
      }
      const chain = metaService.buildCascadeChain(schema)

      expect(chain).toHaveLength(0)
    })
  })

  // ========== Cache Management ==========
  describe('cache management', () => {
    it('should clear all cache when clearCache() called with no arg', () => {
      metaService._setCache('a:view-config:default', { success: true })
      metaService._setCache('b:view-config:default', { success: true })
      expect(metaService.getViewConfigSync('a')).not.toBeNull()

      metaService.clearCache()

      expect(metaService.getViewConfigSync('a')).toBeNull()
      expect(metaService.getViewConfigSync('b')).toBeNull()
    })

    it('should clear only specific objectType cache when arg provided', () => {
      metaService._setCache('a:view-config:default', { success: true, data: { x: 1 } })
      metaService._setCache('b:view-config:default', { success: true, data: { x: 2 } })

      metaService.clearCache('a')

      expect(metaService.getViewConfigSync('a')).toBeNull()
      expect(metaService.getViewConfigSync('b')).not.toBeNull()
    })
  })
})
