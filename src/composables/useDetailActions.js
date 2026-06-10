/**
 * useDetailActions - 详情抽屉/页面的底部操作按钮配置
 *
 * 设计目标：
 * 1. 统一返回"按 mode 切换的按钮配置数组"，避免在多个 DetailPage 组件里重复硬编码
 * 2. 关闭动作（close）不在此处暴露 —— 由 el-drawer / el-dialog 自身的 X 按钮承担，
 *    防止"顶部 X"和"底部关闭"两个按钮语义重复
 * 3. 刷新动作仅在 view 模式出现 —— 新建 / 编辑模式下没有"已存在数据"可刷新，
 *    强行渲染会让用户误以为能 undo 输入
 *
 * 返回结构：每个 action 形如
 *   {
 *     key: 'save' | 'cancel' | 'refresh',
 *     label: '保存' | '取消' | '刷新',
 *     variant: 'primary' | 'secondary' | 'danger',
 *     icon: 'save' | 'refresh' | null,
 *     visible: boolean,   // 是否显示
 *     disabled: boolean,  // 是否禁用
 *     onClick: () => void, // 点击回调（markRaw 避免响应式包装函数）
 *   }
 *
 * @example
 * const { actions } = useDetailActions({
 *   mode: effectiveMode,           // 'add' | 'edit' | 'view'
 *   saving,
 *   loading,
 *   hasData: computed(() => !!data.value),
 *   onSave: handleSave,
 *   onCancel: handleCancel,
 *   onRefresh: handleRefresh,
 * })
 */

import { computed, markRaw, unref } from 'vue'

function safeUnref(value) {
  return value !== undefined ? unref(value) : undefined
}

function buildViewActions({ isLoading, hasLoadedData, onRefresh }) {
  return [
    {
      key: 'refresh',
      label: '刷新',
      variant: 'primary',
      icon: 'refresh',
      visible: true,
      disabled: isLoading || !hasLoadedData,
      onClick: markRaw(() => {
        if (typeof onRefresh === 'function') onRefresh()
      }),
    },
  ]
}

function buildEditActions({ isSaving, isLoading, onSave, onCancel }) {
  return [
    {
      key: 'cancel',
      label: '取消',
      variant: 'secondary',
      icon: null,
      visible: false, // 默认隐藏：ObjectPageHeader 已提供
      disabled: isSaving,
      onClick: markRaw(() => {
        if (typeof onCancel === 'function') onCancel()
      }),
    },
    {
      key: 'save',
      label: '保存',
      variant: 'primary',
      icon: null,
      visible: false, // 默认隐藏：ObjectPageHeader 已提供
      disabled: isSaving || isLoading,
      onClick: markRaw(() => {
        if (typeof onSave === 'function') onSave()
      }),
    },
  ]
}

/**
 * @param {Object} opts
 * @param {import('vue').Ref<string>|string} opts.mode - 'add' | 'edit' | 'view'
 * @param {import('vue').Ref<boolean>} [opts.saving]
 * @param {import('vue').Ref<boolean>} [opts.loading]
 * @param {import('vue').Ref<boolean>|boolean} [opts.hasData] - 是否有已加载的数据
 * @param {() => void} [opts.onSave]
 * @param {() => void} [opts.onCancel]
 * @param {() => void} [opts.onRefresh]
 */
export function useDetailActions(opts = {}) {
  const { mode, saving, loading, hasData, onSave, onCancel, onRefresh } = opts

  const resolvedMode = computed(() => safeUnref(mode) || 'view')
  const isSaving = computed(() => !!(saving && unref(saving)))
  const isLoading = computed(() => !!(loading && unref(loading)))
  const hasLoadedData = computed(() => {
    if (hasData === undefined) return true
    return !!unref(hasData)
  })

  const actions = computed(() => {
    const ctx = {
      isSaving: isSaving.value,
      isLoading: isLoading.value,
      hasLoadedData: hasLoadedData.value,
      onSave,
      onCancel,
      onRefresh,
    }
    const current = resolvedMode.value
    if (current === 'view') return buildViewActions(ctx)
    if (current === 'add' || current === 'edit') return buildEditActions(ctx)
    return []
  })

  return { actions, mode: resolvedMode }
}