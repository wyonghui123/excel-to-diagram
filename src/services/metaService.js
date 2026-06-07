/**
 * Meta Service - v2 API 元数据服务
 *
 * 提供业务对象的 UI Config、Schema、View Config 获取
 * 支持客户端缓存和预加载
 */

import { BaseService } from '@/services/baseService'
import { createLogger } from '@/utils/logger'

const logger = createLogger('metaService')

class MetaService extends BaseService {
  constructor() {
    super(100, 10 * 60 * 1000)
    this.preloadedTypes = new Set()
  }

  async getUIConfig(objectType, options = {}) {
    const cacheKey = this._getCacheKey(objectType, 'ui-config')
    if (!options.forceRefresh) {
      const cached = this._getCached(cacheKey)
      if (cached) return cached
    }

    const result = await this._request('GET', `/meta/${objectType}/ui-config`)
    if (result.success) {
      this._setCache(cacheKey, result)
    }
    return result
  }

  async getSchema(objectType) {
    const cacheKey = this._getCacheKey(objectType, 'schema')
    const cached = this._getCached(cacheKey)
    if (cached) return cached

    const result = await this._request('GET', `/meta/${objectType}/schema`)
    if (result.success) {
      this._setCache(cacheKey, result)
    }
    return result
  }

  async getViewConfig(objectType, viewName = 'default', options = {}) {
    const cacheKey = this._getCacheKey(objectType, `view-config:${viewName}`)
    if (!options.forceRefresh) {
      const cached = this._getCached(cacheKey)
      if (cached) {
        logger.debug('缓存命中:', objectType, 'view-config:', viewName)
        return cached
      }
    }

    logger.debug('getViewConfig 请求:', viewName, 'for', objectType)

    const result = await this._request('GET', `/meta/${objectType}/view-config/${viewName}`)

    logger.debug('getViewConfig 解析:', result?.success)

    if (result.success) {
      this._setCache(cacheKey, result)
    } else {
      logger.warn('getViewConfig 失败:', result?.message || '无消息')
    }
    return result
  }

  getViewConfigSync(objectType, viewName = 'default') {
    const cacheKey = this._getCacheKey(objectType, `view-config:${viewName}`)
    return this._getCached(cacheKey)
  }

  async getFullMeta(objectType) {
    const cacheKey = this._getCacheKey(objectType, 'full')
    const cached = this._getCached(cacheKey)
    if (cached) return cached

    const [uiConfigResult, schemaResult] = await Promise.all([
      this.getUIConfig(objectType),
      this.getSchema(objectType)
    ])

    if (!uiConfigResult.success || !schemaResult.success) {
      return {
        success: false,
        message: '获取元数据失败',
        errors: [
          !uiConfigResult.success && { type: 'ui-config', message: uiConfigResult.message },
          !schemaResult.success && { type: 'schema', message: schemaResult.message }
        ].filter(Boolean)
      }
    }

    const result = {
      success: true,
      data: {
        objectType,
        uiConfig: uiConfigResult.data,
        schema: schemaResult.data
      }
    }

    this._setCache(cacheKey, result)
    return result
  }

  async preloadTypes(objectTypes) {
    const promises = objectTypes.map(type => this.getFullMeta(type))
    await Promise.allSettled(promises)
    objectTypes.forEach(type => this.preloadedTypes.add(type))
  }

  clearCache(objectType = null) {
    if (objectType) {
      this._clearCache(objectType)
      this.preloadedTypes.delete(objectType)
    } else {
      this.cache.clear()
      this.preloadedTypes.clear()
    }
  }

  isPreloaded(objectType) {
    return this.preloadedTypes.has(objectType)
  }

  getFieldsByGroup(uiConfig) {
    if (!uiConfig?.fields) return {}

    const groups = {}
    for (const field of uiConfig.fields) {
      const group = field.group || 'default'
      if (!groups[group]) {
        groups[group] = []
      }
      groups[group].push(field)
    }
    return groups
  }

  getRequiredFields(uiConfig) {
    if (!uiConfig?.fields) return []
    return uiConfig.fields.filter(f => f.required)
  }

  getEditableFields(uiConfig) {
    if (!uiConfig?.fields) return []
    return uiConfig.fields.filter(f => !f.readonly)
  }

  getAssociationsByType(uiConfig) {
    if (!uiConfig?.associations) return { manyToMany: [], reference: [], composition: [] }

    return {
      manyToMany: uiConfig.associations.filter(a => a.type === 'many_to_many'),
      reference: uiConfig.associations.filter(a => a.type === 'reference'),
      composition: uiConfig.associations.filter(a => a.type === 'composition')
    }
  }

  getActionsByCategory(uiConfig) {
    if (!uiConfig?.actions) return {}

    const categories = {}
    for (const action of uiConfig.actions) {
      const category = action.category || 'general'
      if (!categories[category]) {
        categories[category] = []
      }
      categories[category].push(action)
    }
    return categories
  }

  getConstraintsByField(uiConfig) {
    if (!uiConfig?.constraints) return {}

    const byField = {}
    for (const constraint of uiConfig.constraints) {
      const field = constraint.field
      if (!byField[field]) {
        byField[field] = []
      }
      byField[field].push(constraint)
    }
    return byField
  }

  getRulesByState(uiConfig) {
    if (!uiConfig?.rules) return {}

    const byState = {}
    for (const rule of uiConfig.rules) {
      if (rule.from_state) {
        if (!byState[rule.from_state]) {
          byState[rule.from_state] = []
        }
        byState[rule.from_state].push(rule)
      }
    }
    return byState
  }

  getImportExportConfig(schema) {
    if (!schema) return null

    const importExport = schema.import_export || {}

    return {
      importEnabled: importExport.import_enabled ?? true,
      exportEnabled: importExport.export_enabled ?? true,
      cascadeExport: importExport.cascade_export ?? false,
      cascadeImport: importExport.cascade_import ?? false,
      conflictStrategy: importExport.conflict_strategy || 'upsert',
      conflictKey: importExport.conflict_key || 'code',
      description: importExport.description_for_agent || ''
    }
  }

  getCascadeFields(schema) {
    if (!schema) return []

    const fields = schema.fields || []
    return fields
      .filter(f => f.ui?.cascade_level)
      .map(f => ({
        field: f.id,
        label: f.name,
        cascadeLevel: f.ui.cascade_level,
        dependsOn: f.ui.depends_on,
        cascadeGroup: f.ui.cascade_group,
        relation: f.ui.relation,
        displayField: f.ui.display_field
      }))
      .sort((a, b) => a.cascadeLevel - b.cascadeLevel)
  }

  getChildSections(objectType) {
    const cached = this.cache.get(this._getCacheKey(objectType, 'child-sections'))
    if (cached) return cached

    const result = this.getViewConfigSync(objectType)
    if (result?.success && result.data?.ui_view_config?.child_sections) {
      return result.data.ui_view_config.child_sections
    }
    return []
  }

  getChildSectionsAsync(objectType) {
    return this.getViewConfig(objectType).then(result => {
      if (result?.success && result.data?.ui_view_config?.child_sections) {
        return result.data.ui_view_config.child_sections
      }
      return []
    })
  }

  getParentChildRelations(objectType) {
    const result = this.getViewConfigSync(objectType)
    if (result?.success && result.data?.relations) {
      return result.data.relations.filter(r => r.type === 'parent_child')
    }
    return []
  }

  getChildObjectTypes(objectType) {
    const parentRelations = this.getParentChildRelations(objectType)
    return parentRelations.map(r => r.target)
  }

  getParentIdField(objectType, childObjectType) {
    const childMeta = this.getViewConfigSync(childObjectType)
    if (!childMeta?.success) return `${objectType}_id`

    const fields = childMeta.data?.fields || []
    const parentField = fields.find(f =>
      f.ui?.relation === objectType ||
      f.semantics?.meaning === `${objectType}_id`
    )

    return parentField?.id || `${objectType}_id`
  }

  getHierarchyConfig(schema) {
    if (!schema) return null

    const hierarchy = schema.hierarchy
    if (!hierarchy) return null

    return {
      enabled: hierarchy.enabled ?? false,
      hierarchyId: hierarchy.hierarchy_id,
      level: hierarchy.level,
      parentField: hierarchy.parent_field,
      pathField: hierarchy.path_field,
      depthField: hierarchy.depth_field
    }
  }

  getChildObjectTypes(schema) {
    if (!schema) return []

    const hierarchy = this.getHierarchyConfig(schema)
    if (!hierarchy || !hierarchy.parentField) return []

    const fields = schema.fields || []
    const parentField = fields.find(f => f.id === hierarchy.parentField)

    if (parentField?.ui?.relation) {
      return [parentField.ui.relation]
    }

    return []
  }

  getParentObjectTypes(schema) {
    if (!schema) return []

    const fields = schema.fields || []
    const cascadeFields = this.getCascadeFields(schema)

    return cascadeFields
      .filter(f => f.dependsOn)
      .map(f => {
        const parentField = fields.find(field => field.id === f.dependsOn)
        return {
          field: f.dependsOn,
          objectType: parentField?.ui?.relation
        }
      })
      .filter(item => item.objectType)
  }

  buildCascadeChain(schema) {
    if (!schema) return []

    const cascadeFields = this.getCascadeFields(schema)
    const chain = []

    for (const field of cascadeFields) {
      const parentField = schema.fields?.find(f => f.id === field.dependsOn)
      chain.push({
        field: field.field,
        label: field.label,
        parentField: field.dependsOn,
        parentObject: parentField?.ui?.relation,
        parentLabel: parentField?.name,
        cascadeLevel: field.cascadeLevel,
        cascadeGroup: field.cascadeGroup,
        displayField: field.displayField || 'name'
      })
    }

    return chain
  }
}

export const metaService = new MetaService()

export default metaService
