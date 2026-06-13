/**
 * useMetaList/metaConfig.js - 元数据 + 列定义 + 操作按钮子模块（Phase 3.1 拆分预研）
 *
 * v3.6 Phase 3.1 状态: 预研 (未实施迁移)
 *   - metaConfig 子模块包含 11 ref + 1 computed + 11 _transform 方法 + 380 行
 *   - 跨子模块依赖度: 🔴 极高 (11 ref 全部被其他子模块用)
 *   - 独立可行性: ❌ 不推荐 (风险/收益比过低)
 *
 * 本文件 (metaConfig.js) 是**预研文档 + API 草案**, 暂不导出 useMetaList 主入口。
 * 任何后续 agent 拆分 metaConfig 时应:
 *   1. 先解决跨子模块依赖 (selection/inlineEdit/filterSort/batchActions 都用 columns/metaConfig/filterFields)
 *   2. 用 readonly wrapper 或 Pinia store 解耦
 *   3. 然后才能真正提取
 *
 * 风险评估:
 *   1. columns 必须是 ref (FieldPolicy watch) → shallowRef 化失败
 *   2. metaConfig 是 ref 深度引用 → shallowRef 化失败
 *   3. 11 ref 跨子模块交叉依赖 → ctx 单向数据流难实现
 *   4. 4 个 *Override 覆盖逻辑 (displayMode/columnsOverride/rowActionsOverride/etc) 在 init() 内强耦合
 *   5. _loadMetaConfig 调用链依赖 _transformColumns + _enrichColumnsWithFieldMeta 等 6+ helper
 *
 * 结论: utils.js 抽取是 MVU (最小可行单元), metaConfig 抽取是"高风险低收益",
 *       推荐**保留 useMetaList.js 主入口**, 仅用 utils.js 独立化作为拆分成果。
 */

import { ref, computed } from 'vue'

/**
 * createMetaConfig - 元数据 + 列定义 + 操作按钮子模块（草案）
 *
 * @param {Object} ctx - 共享上下文 { objectType, config, t }
 * @returns {Object} { state, computed, methods, transforms }
 */
export function createMetaConfig(ctx) {
  // ======== 响应式状态 (11 ref + 1 computed) ========

  /** 元数据原始配置 */
  const metaConfig = ref(null)

  /** 列定义 (Element Plus el-table-column 格式) */
  // [CRITICAL] columns 必须是 ref (不是 shallowRef), useFieldPolicy 内部 watch 依赖
  const columns = ref([])

  /** 过滤器定义 (el-form-item 格式) */
  const filterFields = ref([])

  /** API 返回的 filters 数组 (包含 filter_type 等信息) */
  const apiFilterConfigs = ref([])

  /** 可见的过滤器字段 (过滤掉 defaultVisible=false 的字段) */
  const visibleFilterFields = computed(() =>
    filterFields.value.filter(field => field.defaultVisible !== false)
  )

  // [FIX 2026-06-08] 权限不足标记: 用于页面显示"无权限"提示而非空数据
  const permissionDenied = ref(false)

  /** 工具栏操作按钮 */
  const toolbarActions = ref([])

  /** 工具栏右侧操作按钮 */
  const toolbarRightActions = ref([])

  /** 行级操作按钮 */
  const rowActions = ref([])

  /** 批量操作配置 */
  const batchActions = ref([])

  /** 导出字段配置 */
  const exportFields = ref([])

  /** 导入选项配置 */
  const importOptions = ref({})

  return {
    // state
    metaConfig,
    columns,
    filterFields,
    apiFilterConfigs,
    visibleFilterFields,
    permissionDenied,
    toolbarActions,
    toolbarRightActions,
    rowActions,
    batchActions,
    exportFields,
    importOptions,
  }
}

/**
 * 拆分 metaConfig 的 11 个 _transform 方法 (草案)
 * 注意: 这些方法依赖 filterService + metaTransformService 9 个 helper
 *       跨子模块共享时, 需通过 ctx 注入
 */
export const _metaConfigTransforms = {
  // _loadMetaConfig, _transformMetaToComponentFormat, _transformColumns,
  // _transformActions, _enrichColumnsWithFieldMeta, _fixDatetimeColumns,
  // _backfillColumnFilterType, _inferColumnPriority, _filterRowActionsSvc,
  // _getDefaultOrdering, _inferFieldEditConfig
  // 全部依赖 filterService + metaTransformService 9 个 helper
  // 跨子模块共享时, 需通过 ctx 注入
}

/**
 * 拆分 metaConfig 的覆盖逻辑 (草案)
 * 注意: 4 个 *Override 在 init() 内强耦合
 */
export const _metaConfigOverrides = {
  // columnsOverride: 'embedded' + 'dialog' 生效
  // rowActionsOverride: 同上
  // toolbarActionsOverride: 同上
  // batchActionsOverride: 同上
  // 提取到独立函数后, 需在 init() 显式调用
}

/**
 * Phase 3.1 metaConfig 拆分决策: ⏸️ 暂不实施
 *
 * 原因:
 *   1. utils.js 抽取已经达成 Phase 3.1 MVU
 *   2. metaConfig 拆分需要先解决 11 ref 跨子模块依赖 (selection/inlineEdit/filterSort/batchActions 全用)
 *   3. ctx 单向数据流 + readonly wrapper 实施成本高 (~2-3h 重构)
 *   4. _loadMetaConfig + _transformMetaToComponentFormat 跨多个 _transform helper, 难单测
 *   5. 拆分后回归风险高 (4 场景用 *Override, 1 场景用 initialFilters)
 *
 * 推荐: 保留 useMetaList.js 整体, 仅 utils.js 独立化作为 Phase 3.1 成果
 */
export const __PHASE_3_1_META_CONFIG_STATUS__ = 'not-recommended-for-split'
