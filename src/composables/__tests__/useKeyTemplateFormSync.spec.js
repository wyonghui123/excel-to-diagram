/**
 * useKeyTemplateFormSync.spec.js
 *
 * 覆盖 useKeyTemplateFormSync composable 的全部公开方法。
 *
 * 覆盖矩阵（14 个用例）：
 *
 *  markFieldDirty
 *   1. 标记新字段 -> 集合添加 + 响应式触发
 *   2. 重复 mark 同一字段 -> 幂等 (Set identity 不变)
 *
 *  resetFieldDirty
 *   3. 重置已标记字段 -> 集合删除 + 响应式触发
 *   4. 重复 reset 同一字段 -> 幂等
 *   5. reset 未标记字段 -> no-op
 *
 *  isFieldDirty
 *   6. 已标记返回 true
 *   7. 未标记返回 false
 *
 *  clearAll
 *   8. 清空 -> 集合 size 归零 + 响应式触发
 *   9. 重复 clearAll -> 幂等
 *  10. 空集合 clearAll -> no-op
 *
 *  响应式行为
 *  11. 多次 mark 连续触发新 Set
 *  12. mark + reset + mark -> 集合最终包含该字段
 *
 *  多实例隔离
 *  13. 两个独立 composable 互不干扰
 *  14. clearAll 不影响其他实例
 */

import { describe, it, expect } from 'vitest'
import { nextTick } from 'vue'
import { useKeyTemplateFormSync } from '@/composables/useKeyTemplateFormSync'

describe('useKeyTemplateFormSync', () => {
  describe('markFieldDirty', () => {
    it('TC-1: 标记新字段 -> 集合添加', () => {
      const { formDirtyFields, markFieldDirty } = useKeyTemplateFormSync()
      const initial = formDirtyFields.value
      markFieldDirty('code')
      expect(formDirtyFields.value.has('code')).toBe(true)
      expect(formDirtyFields.value.size).toBe(1)
      // Set identity 应变化（响应式触发）
      expect(formDirtyFields.value).not.toBe(initial)
    })

    it('TC-2: 重复 mark 同一字段 -> 幂等 (Set identity 不变)', () => {
      const { formDirtyFields, markFieldDirty } = useKeyTemplateFormSync()
      markFieldDirty('code')
      const after1 = formDirtyFields.value
      markFieldDirty('code')
      // 幂等：第二次 mark 不应创建新 Set
      expect(formDirtyFields.value).toBe(after1)
      expect(formDirtyFields.value.size).toBe(1)
    })
  })

  describe('resetFieldDirty', () => {
    it('TC-3: 重置已标记字段 -> 集合删除', () => {
      const { formDirtyFields, markFieldDirty, resetFieldDirty } = useKeyTemplateFormSync()
      markFieldDirty('code')
      markFieldDirty('name')
      const afterMark = formDirtyFields.value
      resetFieldDirty('code')
      expect(formDirtyFields.value.has('code')).toBe(false)
      expect(formDirtyFields.value.has('name')).toBe(true)
      expect(formDirtyFields.value.size).toBe(1)
      // Set identity 应变化
      expect(formDirtyFields.value).not.toBe(afterMark)
    })

    it('TC-4: 重复 reset 同一字段 -> 幂等', () => {
      const { formDirtyFields, markFieldDirty, resetFieldDirty } = useKeyTemplateFormSync()
      markFieldDirty('code')
      resetFieldDirty('code')
      const after1 = formDirtyFields.value
      resetFieldDirty('code')
      expect(formDirtyFields.value).toBe(after1)
      expect(formDirtyFields.value.size).toBe(0)
    })

    it('TC-5: reset 未标记字段 -> no-op', () => {
      const { formDirtyFields, resetFieldDirty } = useKeyTemplateFormSync()
      const initial = formDirtyFields.value
      resetFieldDirty('code')
      // 既然字段没标记过，集合不变，identity 也不变
      expect(formDirtyFields.value).toBe(initial)
      expect(formDirtyFields.value.size).toBe(0)
    })
  })

  describe('isFieldDirty', () => {
    it('TC-6: 已标记返回 true', () => {
      const { markFieldDirty, isFieldDirty } = useKeyTemplateFormSync()
      markFieldDirty('code')
      expect(isFieldDirty('code')).toBe(true)
    })

    it('TC-7: 未标记返回 false', () => {
      const { isFieldDirty } = useKeyTemplateFormSync()
      expect(isFieldDirty('code')).toBe(false)
    })
  })

  describe('clearAll', () => {
    it('TC-8: 清空 -> 集合 size 归零 + 响应式触发', () => {
      const { formDirtyFields, markFieldDirty, clearAll } = useKeyTemplateFormSync()
      markFieldDirty('code')
      markFieldDirty('name')
      const afterMark = formDirtyFields.value
      clearAll()
      expect(formDirtyFields.value.size).toBe(0)
      // identity 应变化（即便集合内容变空也算触发）
      expect(formDirtyFields.value).not.toBe(afterMark)
    })

    it('TC-9: 重复 clearAll -> 幂等', () => {
      const { formDirtyFields, markFieldDirty, clearAll } = useKeyTemplateFormSync()
      markFieldDirty('code')
      clearAll()
      const after1 = formDirtyFields.value
      clearAll()
      expect(formDirtyFields.value).toBe(after1)
    })

    it('TC-10: 空集合 clearAll -> no-op (identity 不变)', () => {
      const { formDirtyFields, clearAll } = useKeyTemplateFormSync()
      const initial = formDirtyFields.value
      clearAll()
      // 空集合清空不触发响应式（避免无意义更新）
      expect(formDirtyFields.value).toBe(initial)
    })
  })

  describe('响应式行为 (Vue reactivity)', () => {
    it('TC-11: 多次 mark 连续触发新 Set (每次都新建 Set)', async () => {
      const { formDirtyFields, markFieldDirty } = useKeyTemplateFormSync()
      markFieldDirty('a')
      const afterA = formDirtyFields.value
      await nextTick()
      markFieldDirty('b')
      const afterB = formDirtyFields.value
      // 第二次 mark 确实创建了新 Set
      expect(afterB).not.toBe(afterA)
      expect(formDirtyFields.value.size).toBe(2)
    })

    it('TC-12: mark + reset + mark -> 集合最终包含该字段', () => {
      const { formDirtyFields, markFieldDirty, resetFieldDirty, isFieldDirty } = useKeyTemplateFormSync()
      markFieldDirty('code')
      expect(isFieldDirty('code')).toBe(true)
      resetFieldDirty('code')
      expect(isFieldDirty('code')).toBe(false)
      markFieldDirty('code')
      expect(isFieldDirty('code')).toBe(true)
      expect(formDirtyFields.value.size).toBe(1)
    })
  })

  describe('多实例隔离', () => {
    it('TC-13: 两个独立 composable 互不干扰', () => {
      const a = useKeyTemplateFormSync()
      const b = useKeyTemplateFormSync()
      a.markFieldDirty('code')
      // b 不应受影响
      expect(b.isFieldDirty('code')).toBe(false)
      expect(b.formDirtyFields.value.size).toBe(0)
      // a 的集合包含 code
      expect(a.isFieldDirty('code')).toBe(true)
    })

    it('TC-14: clearAll 不影响其他实例', () => {
      const a = useKeyTemplateFormSync()
      const b = useKeyTemplateFormSync()
      a.markFieldDirty('code')
      b.markFieldDirty('name')
      a.clearAll()
      expect(a.formDirtyFields.value.size).toBe(0)
      // b 不受影响
      expect(b.isFieldDirty('name')).toBe(true)
      expect(b.formDirtyFields.value.size).toBe(1)
    })
  })
})
