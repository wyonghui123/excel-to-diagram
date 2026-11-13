/**
 * Meta Service - v2 API 元数据服务
 *
 * 提供业务对象的 UI Config、Schema、View Config 获取
 * 支持客户端缓存和预加载
 */

import { BaseService } from '@/services/baseService'
import { createLogger } from '@/utils/logger'

const logger = createLogger('metaService')

// [T13-2 2026-11-13] ui-meta 迁移期回退旧 3 端点（§13.8），warn 只打一次
let legacyFallbackWarned = false

/**
 * 旧端点动作项统一成 UiActionMeta 形状（字符串形态保留 id/label）
 */
function toLegacyActionMeta(action) {
  if (typeof action === 'string') {
    return { id: action, label: action }
  }
  const id = action?.id || action?.key || action?.label || ''
  return { ...action, id, label: action?.label || id }
}

/**
 * 旧 list-view 列（UIListViewColumn）→ UiColumnMeta
 */
function toLegacyColumnMeta(column) {
  const field = column?.key || column?.field || ''
  return {
    field,
    label: column?.title || column?.label || field,
    width: typeof column?.width === 'number' ? column.width : undefined,
    sortable: column?.sortable,
    filterable: column?.filterable,
    tag_enum: column?.enum_type || undefined
  }
}

/**
 * 旧 detail-view facet / form-view section → UiSectionMeta
 */
function toLegacySectionMeta(section) {
  const key = section?.key || section?.id || ''
  return {
    key,
    label: section?.label || section?.title || key,
    columns: section?.columns === 1 ? 1 : 2,
    fields: Array.isArray(section?.fields) ? section.fields : [],
    col_span_map: section?.col_span_map || {}
  }
}

/**
 * 旧 3 端点载荷拼成 UiMeta 形状（schema_version 标记为 legacy）
 */
function buildLegacyUiMeta(objectType, listData, detailData, formData) {
  const listActions = [
    ...(listData?.actions || []),
    ...(listData?.batch_actions || [])
  ].map(toLegacyActionMeta)

  const formSections = (formData?.sections || []).map(toLegacySectionMeta)
  // 旧 form-view 不含 fields 声明，按分区字段引用顺序去重派生最小字段元数据
  const fields = []
  const seenFields = new Set()
  for (const section of formSections) {
    for (const fieldKey of section.fields) {
      if (seenFields.has(fieldKey)) continue
      seenFields.add(fieldKey)
      fields.push({ key: fieldKey, label: fieldKey, widget: 'text' })
    }
  }

  return {
    schema_version: 'legacy',
    object_type: objectType,
    label: listData?.title || objectType,
    partial: true,
    list: {
      columns: (listData?.columns || []).map(toLegacyColumnMeta),
      actions: listActions
    },
    detail: {
      sections: (detailData?.facets || []).map(toLegacySectionMeta),
      tabs: (detailData?.section_tabs || []).map(tab => ({
        key: tab.key,
        label: tab.label || tab.key,
        section_keys: tab.section_keys || []
      }))
    },
    form: {
      sections: formSections,
      tabs: (formData?.tabs || []).map(tab => ({
        key: tab.key,
        label: tab.label || tab.key,
        section_keys: tab.section_keys || []
      })),
      fields,
      layout: formData?.layout
    },
    filters: [],
    field_policies: {},
    actions: []
  }
}

class MetaService extends BaseService {
  constructor() {
    super(100, 10 * 60 * 1000)
    this.preloadedTypes = new Set()
    // [T13-2] ui-meta 缓存：objectType -> { schema_version, data }
    this._uiMetaCache = new Map()
    // [T13-2] 并发去重：objectType -> Promise
    this._uiMetaInflight = new Map()
  }

  /**
   * 聚合 UI 元数据（T13-2）
   *
   * 单请求取齐 list/detail/form/filters；按 objectType 缓存并比对 schema_version，
   * 同 key 并发只发一次。失败时回退旧 list-view / detail-view / form-view 三端点
   * （仅迁移期，§13.8），回退也失败则原样抛出。
   *
   * @param {string} objectType
   * @param {{ force?: boolean }} [options]
   * @returns {Promise<object>} UiMeta（§13.3 形状，snake_case）
   */
  async getUiMeta(objectType, { force = false } = {}) {
    if (!objectType) throw new Error('getUiMeta: objectType 不能为空')

    if (!force) {
      const cached = this._uiMetaCache.get(objectType)
      if (cached) return cached.data
    }

    if (this._uiMetaInflight.has(objectType)) {
      return this._uiMetaInflight.get(objectType)
    }

    const promise = (async () => {
      let data
      try {
        const result = await this._request('GET', `/meta/${objectType}/ui-meta`, { version: 1 })
        if (!result?.success) {
          throw new Error(result?.message || `ui-meta 请求失败: ${objectType}`)
        }
        data = result.data || {}
      } catch (err) {
        // 迁移期回退（§13.8）：旧 3 端点同源，仅作降级
        try {
          data = await this._loadLegacyUiMeta(objectType)
          if (!legacyFallbackWarned) {
            legacyFallbackWarned = true
            logger.warn('ui-meta 不可用，已回退旧 3 端点:', objectType, err?.message || err)
          }
        } catch {
          throw err
        }
      }

      const previous = this._uiMetaCache.get(objectType)
      const entry = { schema_version: data.schema_version || '', data }
      if (previous && previous.schema_version !== entry.schema_version) {
        logger.debug('ui-meta 版本变化，整块替换:', objectType, previous.schema_version, '→', entry.schema_version)
      }
      this._uiMetaCache.set(objectType, entry)
      return data
    })().finally(() => {
      this._uiMetaInflight.delete(objectType)
    })

    this._uiMetaInflight.set(objectType, promise)
    return promise
  }

  /**
   * 回退旧 3 端点并拼成 UiMeta 形状（仅迁移期使用）
   */
  async _loadLegacyUiMeta(objectType) {
    const [listResult, detailResult, formResult] = await Promise.all([
      this._request('GET', `/meta/${objectType}/list-view`, { version: 1 }),
      this._request('GET', `/meta/${objectType}/detail-view`, { version: 1 }),
      this._request('GET', `/meta/${objectType}/form-view`, { version: 1 })
    ])
    const failed = [listResult, detailResult, formResult].find(result => !result?.success)
    if (failed) {
      throw new Error(failed.message || `旧视图端点回退失败: ${objectType}`)
    }
    return buildLegacyUiMeta(
      objectType,
      listResult.data || {},
      detailResult.data || {},
      formResult.data || {}
    )
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
      this._uiMetaCache.delete(objectType)
      this.preloadedTypes.delete(objectType)
    } else {
      this.cache.clear()
      this._uiMetaCache.clear()
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
