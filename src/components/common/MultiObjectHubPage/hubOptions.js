/**
 * hubOptions — 把对象 YAML 的 ui_view_config.hub 声明解析为 MOMP 的 pageOptions
 *
 * 背景
 *   单页 hub（菜单 page_type=multi_object_hub 且无 children）原先靠「一对象一个 Vue 壳」
 *   注入 MOMP 配置（物料 / 区划 / 位置 / 业务伙伴 / 作业日历 / 组织 六份近乎同构的壳）。
 *   收敛为数据驱动后，页面形态只在 YAML 里声明一次，本文件负责把它翻译成
 *   MultiObjectManagementPage 认识的 objectTypes + options。
 *
 * 声明契约（全部键）
 *   hub:
 *     object_types: [item_group, item]   # 右表 tab 顺序
 *     default_tab: item
 *     tabs: { item: 物料/服务 }          # objectType → 标签；缺省用 objectType
 *     state_key: materialManagerState    # 图表态暂存键
 *     disable_version_context: true      # 主数据页默认 true
 *     scope:                             # 左树
 *       type: hierarchy                  # 当前仅 hierarchy（HierarchyScopeTree）
 *       object: item_group               # 树查询的 BO
 *       scope_key: item                  # 写入 scopeIds 的键（受过滤 tab 名）
 *       parent_field: parent_id          # 缺省 parent_id
 *       flat: true                       # 扁平分类（无 parent 自引用）
 *       order_by: ''                     # 省略 = 组件默认按 code 排；'' = 保持后端顺序
 *       badge_field / badge_map          # 节点徽标（枚举值 → { label, type }）
 *       node_icon: none | folder | location | office
 *       paginate_all: true               # 循环分页拉全量（树数据超后端单页上限时）
 *       empty_text / search_placeholder
 *     filters:                           # 每个 tab 的范围过滤；缺省 = 不受左树影响
 *       item: { field: item_group_id }   # → item_group_id__in = effective ids
 *       item_group: { mode: none }       # 显式声明「不过滤」（语义同缺省）
 *       party_archive:                   # 两段桥接：树选组 → 关系表 → 伙伴集合
 *         bridge:
 *           through: party_relation      # 中间 BO（异步查询）
 *           match_field: group_id        # 中间 BO 上承接 effective ids 的字段
 *           collect_field: party2_id     # 从中间 BO 取出的字段
 *           target_field: id             # 右表过滤字段（→ id__in）
 *           page_size: 500
 *           empty_sentinel: '-1'         # 选中但结果为空时的哨兵（防后端跳条件回退全量）
 *
 * 过滤口径
 *   effective = 勾选 ∪ 全部子孙（HierarchyScopeTree 已算好）。未勾选 → 不加过滤条件，
 *   后端返回全量；这是主数据页的业务预期（未选范围 = 看全部），不是空集守卫。
 *
 * 为什么未声明的 tab 也要显式给策略
 *   combinedFilters 是所有 tab 共享的 computed（按 tab 分派）。未声明策略的 tab 会落到
 *   useMultiObjectPage 的 _buildRelationshipFilters 默认分支，被注入 relationExtra 过滤
 *   参数 —— 对主数据对象是纯噪声。故未声明的一律给「返回原 filters」。
 */

import { FolderOpened, Location as LocationIcon, OfficeBuilding } from '@element-plus/icons-vue'
import { HierarchyScopeTree } from '@/components/common/HierarchyScopeTree'

// YAML 里不能用 JS 组件引用，故只允许枚举值；未登记的取值回退默认图标
const NODE_ICONS = {
  none: null,
  folder: FolderOpened,
  location: LocationIcon,
  office: OfficeBuilding
}

function camelize(value) {
  return String(value).replace(/_(\w)/g, (_, c) => c.toUpperCase())
}

function pascalize(value) {
  const camel = camelize(value)
  return camel.charAt(0).toUpperCase() + camel.slice(1)
}

function buildTabs(tabsConfig, objectTypes) {
  const tabs = {}
  for (const objectType of objectTypes) {
    tabs[objectType] = { label: tabsConfig?.[objectType] || objectType }
  }
  return tabs
}

function normalizeBridge(rule, scopeKey, objectType) {
  const bridge = rule?.bridge
  if (!bridge?.through || !bridge?.collect_field) {
    console.error(`[hubOptions] ${objectType} 的 bridge 声明缺少 through/collect_field`)
    return null
  }
  return {
    objectType,
    scopeKey: bridge.scope_key || scopeKey,
    through: bridge.through,
    matchField: bridge.match_field || 'id',
    collectField: bridge.collect_field,
    targetField: bridge.target_field || 'id',
    pageSize: bridge.page_size || 500,
    // 空集哨兵: 后端 __in 收到空串会整体跳过条件 → 回退全量, 故「选中但无结果」必须显式表达
    emptySentinel: bridge.empty_sentinel === undefined ? '-1' : String(bridge.empty_sentinel)
  }
}

function buildFilterStrategies(filtersConfig, objectTypes, scopeKey, { bridgeIds, bridges }) {
  const strategies = {}
  for (const objectType of objectTypes) {
    const rule = filtersConfig?.[objectType]

    if (rule?.bridge) {
      const bridge = normalizeBridge(rule, scopeKey, objectType)
      if (!bridge) {
        strategies[objectType] = (filters) => filters
        continue
      }
      bridges.push(bridge)
      strategies[objectType] = (filters) => {
        // bridgeIds[objectType] 由 MultiObjectHubPage 异步写入:
        //   null/undefined = 未选范围（全量）; [] = 选中但无关联（空集哨兵）
        const ids = bridgeIds?.[objectType]
        if (ids === null || ids === undefined) return filters
        const key = `${bridge.targetField}__in`
        if (!ids.length) return { ...filters, [key]: bridge.emptySentinel }
        return { ...filters, [key]: ids.join(',') }
      }
      continue
    }

    if (rule?.mode === 'none' || !rule?.field) {
      strategies[objectType] = (filters) => filters
      continue
    }
    strategies[objectType] = (filters, scopeIds) => {
      const ids = scopeIds?.[scopeKey]?.effective || []
      if (!ids.length) return filters
      return { ...filters, [`${rule.field}__in`]: ids.join(',') }
    }
  }
  return strategies
}

function buildScopeProps(scopeConfig, { scopeObject, scopeKey, idsKey, effectiveIdsKey }) {
  const props = {
    objectType: scopeObject,
    scopeKey,
    idsKey,
    effectiveIdsKey
  }
  if (scopeConfig.parent_field) props.parentField = scopeConfig.parent_field
  if (scopeConfig.flat) props.flat = true
  // order_by 区分「省略」与「空串」：省略 ⇒ 组件默认 code 排序；'' ⇒ 保持后端顺序
  if (scopeConfig.order_by !== undefined && scopeConfig.order_by !== null) {
    props.orderBy = scopeConfig.order_by
  }
  if (scopeConfig.empty_text) props.emptyText = scopeConfig.empty_text
  if (scopeConfig.search_placeholder) props.searchPlaceholder = scopeConfig.search_placeholder
  if (scopeConfig.badge_field) {
    props.badgeField = scopeConfig.badge_field
    props.badgeMap = scopeConfig.badge_map || {}
  }
  if (scopeConfig.node_icon !== undefined) {
    const icon = NODE_ICONS[scopeConfig.node_icon]
    props.nodeIcon = icon === undefined ? FolderOpened : icon
  }
  if (scopeConfig.paginate_all) props.paginateAll = true
  return props
}

/**
 * @param {object} hub - ui_view_config.hub
 * @param {{ menuCode?: string, bridgeIds?: object }} ctx
 *   bridgeIds: 响应式容器（objectType → null | string[]），由调用方异步填充；
 *   含 bridge 声明的 tab 会读取它，故必须是同一引用而非拷贝。
 * @returns {{ objectTypes: string[], options: object, bridges: Array } | null}
 *   声明不合法时返回 null（调用方回退通用列表）
 */
export function resolveHubOptions(hub, { menuCode = '', bridgeIds = null } = {}) {
  const objectTypes = Array.isArray(hub?.object_types)
    ? hub.object_types.filter(Boolean)
    : []
  if (!objectTypes.length) return null

  const scopeConfig = hub.scope || {}
  if (scopeConfig.type && scopeConfig.type !== 'hierarchy') {
    console.error(`[hubOptions] 未支持的 scope.type="${scopeConfig.type}"（menu=${menuCode}）`)
    return null
  }

  const scopeObject = scopeConfig.object || objectTypes[0]
  const scopeKey = scopeConfig.scope_key || scopeObject
  if (!objectTypes.includes(scopeKey)) {
    console.error(`[hubOptions] scope_key="${scopeKey}" 不在 object_types 内（menu=${menuCode}）`)
    return null
  }

  // 动态键名与 HierarchyScopeTree 的既有约定完全一致：
  //   item_group → itemGroupIds / effectiveItemGroupIds
  const idsKey = `${camelize(scopeObject)}Ids`
  const effectiveIdsKey = `effective${pascalize(scopeObject)}Ids`

  const bridges = []
  const options = {
    defaultTab: hub.default_tab || objectTypes[0],
    tabs: buildTabs(hub.tabs, objectTypes),
    stateKey: hub.state_key,
    disableVersionContext: hub.disable_version_context !== false,
    menuCodeProvider: () => menuCode,
    filterStrategies: buildFilterStrategies(hub.filters, objectTypes, scopeKey, { bridgeIds, bridges }),
    scopeTree: {
      component: HierarchyScopeTree,
      props: buildScopeProps(scopeConfig, { scopeObject, scopeKey, idsKey, effectiveIdsKey }),
      events: {}
    },
    scopeAdapter: {
      handleScopeChange(scope, ctx) {
        const target = ctx.scopeIds?.[scopeKey]
        if (!target) return
        const selected = scope[idsKey] || []
        const effective = scope[effectiveIdsKey]?.length ? scope[effectiveIdsKey] : selected
        target.selected = selected
        target.effective = effective
      }
    }
  }

  return { objectTypes, options, bridges }
}
