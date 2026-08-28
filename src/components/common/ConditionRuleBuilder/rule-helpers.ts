/**
 * ConditionRuleBuilder Rule helpers — picker / fetcher / handlers
 *
 * [v26 2026-08-26] 抽取自 ConditionRuleDialog.vue (v18-v21)
 * [v29 2026-08-27] 维度 picker 树展开 — 对齐业务对象详情页 service_module 字段的 UX
 *
 * 设计原则:
 *   - 工厂模式接收 permService 作为依赖（避免硬编码具体 service）
 *   - 业务主键 self-reference 需要 form.resource_type 作为 context
 *   - 提供三个核心函数:
 *       getRuleValueHelpConfig(rule, ctx) → value-help-config
 *       createRuleValueFetcher(permService) → (rule, ctx) => fetcher
 *       handleRulePickerConfirm(rule, selection) → 更新 rule.value + picker 缓存
 */

import * as permServiceDefault from '@/services/permissionService'

// [v29 2026-08-27] 层级化 picker — 维度白名单
//   与后端 chain_owner_resolver.HIERARCHY_CHAIN / permission_dimension_api._PARENT_INFO_MAP
//   保持一致（product / version / domain / sub_domain / service_module / business_object）
//   命中即在 SearchHelpDialog 切到 tree 模式（HierarchicalTreePicker 展开式树）。
//   参考业务对象详情页 service_module 字段（service_module.yaml L560-565: display_mode: tree）。
const HIERARCHY_DIMENSIONS = new Set([
  'product', 'version', 'domain', 'sub_domain', 'service_module', 'business_object',
])

/**
 * 构造 picker value-help-config
 *
 * @param rule  rule 节点
 * @param ctx  { resourceType, form } — form 用于业务主键 self-reference
 *
 * 字段来源:
 *   - FK 字段: target_bo = rule.relationObject
 *   - 业务主键 (v18): target_bo = form.resource_type (self-reference)
 *   - 固定枚举 (v21): sourceType='enum', target_bo='inline'
 *   - 引用枚举 (v21): sourceType='enum', target_bo=rule.enumRef
 *
 * 头部产品对照:
 *   - SAP F4 Search Help on Authorization Field: 自身字段也支持 F4
 *   - Salesforce Lookup Dialog: 默认 field 是 Id，返回值是 Id
 */
export function getRuleValueHelpConfig(rule, ctx = {}) {
  const { form } = ctx
  let sourceType = 'bo'
  let targetBo = rule.isBusinessKey && form ? form.resource_type : rule.relationObject
  let displayColumns = [
    { field: 'name', label: '名称' },
    { field: 'code', label: '编码' },
  ]
  let displayMode = 'flat'  // 默认 flat；维度命中后切 tree
  if (rule.isEnum) {
    if (rule.enumRef) {
      sourceType = 'enum'
      targetBo = rule.enumRef
    } else {
      sourceType = 'enum'
      targetBo = 'inline'  // 标识本地 enumValues 渲染
    }
    displayColumns = [
      { field: 'name', label: '值' },
      { field: 'code', label: '编码' },
    ]
  } else if (HIERARCHY_DIMENSIONS.has(targetBo)) {
    // [v29 2026-08-27] 对齐业务对象详情页 service_module 字段 UX
    //   切到 display_mode='tree' → SearchHelpDialog 渲染 HierarchicalTreePicker
    //   展开式树（产品→版本→领域→子领域→服务模块→业务对象）
    //   - 多选：HierarchicalTreePicker 内置 show-checkbox + check-strictly，OK
    //   - 单选：单选时点节点即选中（@node-click 触发 confirm），OK
    //   - 数据源：/api/v2/bo/permission_dimension/<dimId>/tree，自带默认展开级 + 搜索
    //   - flat 模式 fetcher 在 tree 模式下不会被 SearchHelpDialog 调用，安全降级
    displayMode = 'tree'
  }
  return {
    source: { type: sourceType, target_bo: targetBo },
    presentation: {
      // [Phase 3.18 2026-08-26] v18 fix: display_mode 必须是 'flat' / 'tree_flat' / 'tree' 之一
      // [v29 2026-08-27] 维度命中时切到 tree 模式（与详情页 service_module 字段一致）
      display_mode: displayMode,
      display_columns: displayColumns,
    },
    behavior: {
      multiple: ['IN', 'NOT IN', 'LIKE', 'NOT LIKE'].includes(rule.operator),
    },
  }
}

/**
 * 创建 picker fetcher — 工厂模式接收 permService
 *
 * @param permService  默认从 '@/services/permissionService' 导入，可被父组件覆盖（用于 mock 测试）
 * @returns (rule, ctx, params) => Promise
 *
 * 字段 picker:
 *   - 枚举字段: 直接从 rule.enumValues 取，不用走 API
 *   - FK / 业务主键: 调后端 loadDimensionInstances
 */
export function createRuleValueFetcher(permService = permServiceDefault) {
  return async function ruleValueFetcher(rule, ctx = {}, params = {}) {
    const { form } = ctx
    const { page = 1, pageSize: ps = 20, keyword = '' } = params || {}

    // [v21 2026-08-26] 枚举字段: 固定值 (enum_values) 或引用枚举 (enum_ref)
    if (rule.isEnum) {
      const allItems = rule.enumValues || []
      const lowerKw = (keyword || '').toLowerCase()
      const filtered = lowerKw
        ? allItems.filter((item) =>
            String(item.label).toLowerCase().includes(lowerKw) ||
            String(item.value).toLowerCase().includes(lowerKw)
          )
        : allItems
      const start = (page - 1) * ps
      const paged = filtered.slice(start, start + ps)
      return {
        success: true,
        data: {
          items: paged.map((item) => ({
            ...item,
            value: String(item.value),
            id: String(item.value),
            name: item.label || String(item.value),
            code: String(item.value),
            display: item.label || String(item.value),
            title: item.label || String(item.value),
          })),
          total: filtered.length,
        },
      }
    }

    // FK / 业务主键 → 后端 /bo/permission_dimension/<resource_type>/instances
    const targetBo = rule.isBusinessKey && form ? form.resource_type : rule.relationObject
    const serviceParams = {
      page: page || 1,
      page_size: ps || 20,
    }
    if (keyword) serviceParams.search = keyword
    try {
      const result = await permService.loadDimensionInstances(targetBo, serviceParams)
      const allInstances = result.data?.instances || result.data || []
      const total = result.data?.pagination?.total_count || allInstances.length
      return {
        success: true,
        data: {
          items: allInstances.map((inst) => {
            const value = inst.id  // [v20-2026-08-26 FIX] rowKey = 'value', 必须注入 value 字段
            return {
              ...inst,
              value,
              id: value,
              name: inst.name || inst.code || String(value),
              code: inst.code || '',
              display: inst.name || inst.code || String(value),
              title: inst.name || inst.code || String(value),
            }
          }),
          total,
        },
      }
    } catch (e) {
      console.error('[ConditionRuleBuilder.ruleValueFetcher]', e)
      return { success: false, data: { items: [], total: 0 }, message: String(e) }
    }
  }
}

/**
 * picker confirm 事件回调 — 更新 rule.value + rule.pickerSelectedItems
 *
 * 注意: 不调用 syncCustomRules，由父组件 emit 触发
 */
export function handleRulePickerConfirm(rule, selection) {
  const items = Array.isArray(selection) ? selection : (selection ? [selection] : [])
  rule.pickerSelectedItems = items.map((item) => ({
    id: item.value != null ? item.value : item.id,
    name: item.name || item.display || item.title || item.code || String(item.value || item.id),
    code: item.code || '',
  }))
  rule.pickerSelectedIds = rule.pickerSelectedItems.map((i) => i.id)
  rule.value = rule.pickerSelectedIds.join(',')
  rule.pickerVisible = false
}

/**
 * 解析 picker selectedValue — 优先用 pickerSelectedIds 缓存，兜底从 value 字符串解析
 */
export function parseRuleValueIds(rule) {
  if (rule.pickerSelectedIds && rule.pickerSelectedIds.length) return rule.pickerSelectedIds
  if (rule.value && typeof rule.value === 'string') {
    return rule.value.split(',').map((s) => s.trim()).filter(Boolean)
  }
  return []
}

/**
 * 格式化显示已选值（rule.value 是字符串 "id1,id2"，但 picker 显示用名字）
 */
export function formatRuleValue(rule) {
  if (!rule.value) return ''
  const ids = rule.value.split(',').map((s) => s.trim()).filter(Boolean)
  if (!rule.pickerSelectedItems || !rule.pickerSelectedItems.length) {
    // 无 items 缓存（编辑模式首次渲染）— 显示 ID
    return ids.join(', ')
  }
  const items = rule.pickerSelectedItems
  if (items.length === 1) {
    return items[0].name || items[0].id
  }
  if (items.length === 2) {
    return items.map((i) => i.name || i.id).join(' / ')
  }
  // 多于 2 个:「前 2 个...」+ 剩余数量
  const head = items.slice(0, 2).map((i) => i.name || i.id).join(' / ')
  return `${head} 等 ${items.length} 项`
}