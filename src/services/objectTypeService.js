/**
 * ObjectType Service - 对象类型标签服务
 *
 * 从后端 API 获取对象类型元数据（包含 name 字段），
 * 用于前端动态生成 Tab 标签、菜单等展示名称。
 *
 * 使用方式：
 *   import { objectTypeService } from '@/services/objectTypeService'
 *
 *   // 初始化（应用启动时调用一次）
 *   await objectTypeService.init()
 *
 *   // 获取标签
 *   const label = objectTypeService.getLabel('user')  // '用户'
 *   const label = objectTypeService.getLabel('user_group')  // '用户组'
 */

import { apiV1 } from '@/utils/httpClient'

class ObjectTypeService {
  constructor() {
    this.labels = {}
    this.initialized = false
    this.initPromise = null
  }

  async init() {
    if (this.initialized) {
      return this.labels
    }

    if (this.initPromise) {
      return this.initPromise
    }

    this.initPromise = this._loadLabels()
    return this.initPromise
  }

  async _loadLabels() {
    try {
      const result = await apiV1.get('/meta/objects')

      const loadedCount = { count: 0 }
      if (result.success && Array.isArray(result.data)) {
        for (const obj of result.data) {
          if (obj.id && obj.name) {
            this.labels[obj.id] = obj.name
            loadedCount.count++
          }
        }
      }

      if (loadedCount.count === 0) {
        console.warn('[ObjectTypeService] No labels loaded from API')
        return {}
      }

      this.initialized = true
      console.debug('[ObjectTypeService] Loaded labels:', this.labels)
      return this.labels
    } catch (e) {
      console.warn('[ObjectTypeService] Error loading object types:', e)
      return {}
    }
  }

  getLabel(objectType) {
    const label = this.labels[objectType]
    if (!label) {
      console.warn(`[ObjectTypeService] Label not found for objectType: ${objectType}, using fallback`)
    }
    
    if (!label) {
      const fallbackLabels = {
        'product': '产品线',
        'version': '版本',
        'domain': '领域',
        'sub_domain': '子领域',
        'service_module': '服务模块',
        'business_object': '业务对象',
        'relationship': '关系',
        'user': '用户',
        'user_group': '用户组',
        'role': '角色',
        'permission': '权限',
        'enum_type': '枚举类型',
        'enum_value': '枚举值',
        'product_version': '产品版本',
        'audit_log': '审计日志',
        'menu_permission': '菜单权限',
        'data_permission': '数据权限',
        'condition_rule': '条件规则',
        'annotation_category': '标注类别',
        'hierarchy_type': '层级类型'
      }
      return fallbackLabels[objectType] || this._humanize(objectType)
    }
    
    return label
  }

  getCreateLabel(objectType) {
    return `新建${this.getLabel(objectType)}`
  }

  getDetailLabel(objectType, objectName = '') {
    const baseLabel = `${this.getLabel(objectType)}详情`
    if (objectName) {
      return `${baseLabel} ${objectName}`
    }
    return baseLabel
  }

  clearCache() {
    this.labels = {}
    this.initialized = false
    this.initPromise = null
  }

  isReady() {
    return this.initialized
  }

  _humanize(str) {
    if (!str) return '对象'
    return str
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase())
      .replace(/([a-z])([A-Z])/g, '$1 $2')
  }
}

export const objectTypeService = new ObjectTypeService()

export default objectTypeService
