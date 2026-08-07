import { reactive } from 'vue'

/**
 * [TREE 2026-08-04] 共享的分组展开状态
 * 用于 LayoutControlPanel 的"全部展开/全部收起"与所有 LayoutGroupNode 通信。
 * 采用模块级 reactive + version 广播，避免对递归组件做 props 层层透传。
 */
export const groupExpansionState = reactive({
  version: 0,
  mode: 'none' // 'none' | 'all' | 'collapse'
})

export function expandAllGroups() {
  groupExpansionState.mode = 'all'
  groupExpansionState.version++
}

export function collapseAllGroups() {
  groupExpansionState.mode = 'collapse'
  groupExpansionState.version++
}