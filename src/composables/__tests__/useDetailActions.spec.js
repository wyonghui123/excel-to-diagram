/**
 * useDetailActions 单元测试
 *
 * 验证按 mode 返回的按钮配置：
 * 1. view 模式返回 [刷新] —— 不返回"关闭"（X 承担）
 * 2. add/edit 模式默认 visible=false（footer 让空，因为 header 已经有保存/取消）
 * 3. saving/loading 时按钮 disabled
 * 4. onClick 回调正确触发
 * 5. 未知 mode 返回空数组
 */

/* eslint-disable max-lines-per-function -- 测试文件 describe 块按场景分组，可读性 > 单函数行数 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useDetailActions } from '@/composables/useDetailActions'

describe('useDetailActions', () => {
  let onSave, onCancel, onRefresh

  beforeEach(() => {
    onSave = vi.fn()
    onCancel = vi.fn()
    onRefresh = vi.fn()
  })

  describe('view 模式', () => {
    it('返回 [refresh] 按钮', () => {
      const { actions } = useDetailActions({ mode: ref('view'), onRefresh })
      expect(actions.value).toHaveLength(1)
      expect(actions.value[0].key).toBe('refresh')
    })

    it('不返回 close 按钮（X 按钮承担）', () => {
      const { actions } = useDetailActions({ mode: ref('view'), onRefresh })
      const keys = actions.value.map((a) => a.key)
      expect(keys).not.toContain('close')
    })

    it('点击 refresh 触发 onRefresh', () => {
      const { actions } = useDetailActions({ mode: ref('view'), onRefresh })
      actions.value[0].onClick()
      expect(onRefresh).toHaveBeenCalledTimes(1)
    })

    it('loading 时 refresh 按钮禁用', () => {
      const { actions } = useDetailActions({
        mode: ref('view'),
        loading: ref(true),
        onRefresh,
      })
      expect(actions.value[0].disabled).toBe(true)
    })

    it('hasData=false 时 refresh 按钮禁用', () => {
      const { actions } = useDetailActions({
        mode: ref('view'),
        hasData: ref(false),
        onRefresh,
      })
      expect(actions.value[0].disabled).toBe(true)
    })
  })

  describe('add 模式', () => {
    it('返回 [cancel, save] 但 visible 默认 false', () => {
      const { actions } = useDetailActions({ mode: ref('add'), onSave, onCancel })
      expect(actions.value).toHaveLength(2)
      const map = Object.fromEntries(actions.value.map((a) => [a.key, a]))
      expect(map.cancel.visible).toBe(false)
      expect(map.save.visible).toBe(false)
    })

    it('点击 save 触发 onSave', () => {
      const { actions } = useDetailActions({ mode: ref('add'), onSave, onCancel })
      const saveAction = actions.value.find((a) => a.key === 'save')
      saveAction.onClick()
      expect(onSave).toHaveBeenCalledTimes(1)
    })

    it('点击 cancel 触发 onCancel', () => {
      const { actions } = useDetailActions({ mode: ref('add'), onSave, onCancel })
      const cancelAction = actions.value.find((a) => a.key === 'cancel')
      cancelAction.onClick()
      expect(onCancel).toHaveBeenCalledTimes(1)
    })

    it('saving 时 save 和 cancel 都禁用', () => {
      const { actions } = useDetailActions({
        mode: ref('add'),
        saving: ref(true),
        onSave,
        onCancel,
      })
      const map = Object.fromEntries(actions.value.map((a) => [a.key, a]))
      expect(map.save.disabled).toBe(true)
      expect(map.cancel.disabled).toBe(true)
    })
  })

  describe('edit 模式', () => {
    it('与 add 模式行为一致', () => {
      const { actions } = useDetailActions({ mode: ref('edit'), onSave, onCancel })
      const map = Object.fromEntries(actions.value.map((a) => [a.key, a]))
      expect(map.save.visible).toBe(false)
      expect(map.cancel.visible).toBe(false)
    })
  })

  describe('未知 mode', () => {
    it('返回空数组（保守行为）', () => {
      const { actions } = useDetailActions({ mode: ref('weird-mode') })
      expect(actions.value).toEqual([])
    })
  })

  describe('mode 响应式', () => {
    it('mode 从 view 切到 add 时 actions 同步变化', () => {
      const mode = ref('view')
      const { actions } = useDetailActions({ mode, onSave, onCancel, onRefresh })
      expect(actions.value).toHaveLength(1)

      mode.value = 'add'
      expect(actions.value).toHaveLength(2)

      mode.value = 'view'
      expect(actions.value).toHaveLength(1)
    })

    it('mode 可以是字符串（不需要 ref）', () => {
      const { actions } = useDetailActions({ mode: 'view', onRefresh })
      expect(actions.value[0].key).toBe('refresh')
    })
  })

  describe('onClick 函数稳定性', () => {
    it('onClick 是 markRaw 包装（引用稳定）', () => {
      const { actions } = useDetailActions({ mode: ref('view'), onRefresh })
      const first = actions.value[0].onClick
      const second = actions.value[0].onClick
      expect(first).toBe(second)
    })
  })
})