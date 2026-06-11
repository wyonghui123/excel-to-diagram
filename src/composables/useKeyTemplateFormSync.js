/**
 * useKeyTemplateFormSync.js
 *
 * [NEW 2026-06-10] 选项 A 交互 (Salesforce 派)
 *
 * 用途：跟踪详情表单场景下用户编辑过的字段，用于 key template 自动建议的
 * 保护逻辑（与 inline edit 模式的 rowDrafts.has('code') 语义对齐）。
 *
 * 适用场景：
 *   - 详情表单（ObjectPageShell）新建业务对象/关系
 *   - 父对象变化时，自动重新建议 code
 *   - 但如果用户已经手动了 code 字段，则不覆盖
 *   - 提供 "重置为自动生成" 入口
 *
 * 用法：
 *   const { formDirtyFields, markFieldDirty, resetFieldDirty, isFieldDirty, clearAll }
 *     = useKeyTemplateFormSync()
 *
 *   // ObjectPageField 输入时
 *   markFieldDirty('code')
 *
 *   // ObjectPageShell 父对象变化回调中
 *   if (!isFieldDirty('code')) {
 *     // 触发重新建议
 *   }
 *
 *   // 用户点击"重置为自动生成"
 *   resetFieldDirty('code')
 *   // 然后重新建议
 *
 *   // 关闭/取消表单时
 *   clearAll()
 *
 * 设计决策：
 *   1. **响应式 Set**：用 `ref(new Set())` 包装，对外暴露 Set API
 *   2. **Set 替换触发更新**：每次 add/delete 后创建新 Set，保证 Vue 触发响应式
 *      （直接 mutate Set 不会触发响应式，因为 Vue 不会深度追踪 Set）
 *   3. **轻量级**：无外部依赖，仅用 vue 的 ref
 *   4. **可独立单测**：纯函数 + 响应式 API
 *
 * 不适用场景：
 *   - inline edit 模式（已有 rowDrafts.has('code') 保护，无需本 composable）
 *   - 非 key_template 字段的脏跟踪（按需扩展，不预先设计）
 */

import { ref } from 'vue'

/**
 * @returns {{
 *   formDirtyFields: import('vue').Ref<Set<string>>,
 *   markFieldDirty: (fieldName: string) => void,
 *   resetFieldDirty: (fieldName: string) => void,
 *   isFieldDirty: (fieldName: string) => boolean,
 *   clearAll: () => void,
 * }}
 */
export function useKeyTemplateFormSync() {
  const formDirtyFields = ref(new Set())

  /**
   * 标记字段为"已编辑"
   * 幂等：重复 mark 同一字段不会触发额外响应式更新
   *
   * @param {string} fieldName - 字段名
   */
  function markFieldDirty(fieldName) {
    if (!formDirtyFields.value.has(fieldName)) {
      formDirtyFields.value.add(fieldName)
      // 用新 Set 替换以触发响应式（Vue 不深度追踪 Set）
      formDirtyFields.value = new Set(formDirtyFields.value)
    }
  }

  /**
   * 清除字段的"已编辑"标记
   * 幂等：重复 reset 同一字段不会触发额外响应式更新
   *
   * @param {string} fieldName - 字段名
   */
  function resetFieldDirty(fieldName) {
    if (formDirtyFields.value.has(fieldName)) {
      formDirtyFields.value.delete(fieldName)
      formDirtyFields.value = new Set(formDirtyFields.value)
    }
  }

  /**
   * 检查字段是否已被用户编辑
   *
   * @param {string} fieldName - 字段名
   * @returns {boolean}
   */
  function isFieldDirty(fieldName) {
    return formDirtyFields.value.has(fieldName)
  }

  /**
   * 清空所有脏字段标记
   * 用于表单关闭/取消时
   */
  function clearAll() {
    if (formDirtyFields.value.size > 0) {
      formDirtyFields.value = new Set()
    }
  }

  return {
    formDirtyFields,
    markFieldDirty,
    resetFieldDirty,
    isFieldDirty,
    clearAll,
  }
}
