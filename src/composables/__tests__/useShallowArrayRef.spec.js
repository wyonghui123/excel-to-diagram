/**
 * 测试 useShallowArrayRef (W1 PR-1.3)
 */
import { describe, it, expect, vi } from 'vitest'
import { nextTick, watch } from 'vue'

describe('useShallowArrayRef (W1 PR-1.3)', () => {
  describe('基础行为', () => {
    it('初始化空数组', async () => {
      const { useShallowArrayRef } = await import('@/composables/useShallowArrayRef')
      const { ref } = useShallowArrayRef([])
      expect(ref.value).toEqual([])
    })

    it('初始化带值', async () => {
      const { useShallowArrayRef } = await import('@/composables/useShallowArrayRef')
      const { ref } = useShallowArrayRef([1, 2, 3])
      expect(ref.value).toEqual([1, 2, 3])
    })

    it('非数组初始值包装为单元素数组', async () => {
      const { useShallowArrayRef } = await import('@/composables/useShallowArrayRef')
      const { ref } = useShallowArrayRef('x')
      expect(ref.value).toEqual(['x'])
    })
  })

  describe('set() 整体替换触发响应式', () => {
    it('set 替换数组触发 watch', async () => {
      const { useShallowArrayRef } = await import('@/composables/useShallowArrayRef')
      const { ref, set } = useShallowArrayRef([])
      const cb = vi.fn()
      watch(ref, cb)
      set([1, 2, 3])
      await nextTick()
      expect(cb).toHaveBeenCalled()
      expect(ref.value).toEqual([1, 2, 3])
    })

    it('set 多次替换只触发 watch 一次（默认 shallow watch）', async () => {
      const { useShallowArrayRef } = await import('@/composables/useShallowArrayRef')
      const { ref, set } = useShallowArrayRef([])
      const cb = vi.fn()
      watch(ref, cb)
      set([1])
      set([2])
      set([3])
      await nextTick()
      expect(cb).toHaveBeenCalledTimes(1)
    })
  })

  describe('性能优势', () => {
    it('10000 元素数组 push 不创建 Proxy（shallow）', async () => {
      const { useShallowArrayRef } = await import('@/composables/useShallowArrayRef')
      const { ref, set } = useShallowArrayRef([])
      const big = Array.from({ length: 10000 }, (_, i) => ({ id: i, data: { x: i } }))
      set(big)
      expect(ref.value).toHaveLength(10000)
      // shallowRef.value 是数组本身（不是 Proxy 包装）
      // 验证：数组的 push 不触发响应式
      const cb = vi.fn()
      watch(ref, cb)
      ref.value.push({ id: 9999, data: { x: 9999 } })
      await nextTick()
      // 浅 watch：push 不替换引用，watcher 不触发
      expect(cb).not.toHaveBeenCalled()
    })
  })

  describe('trigger() 强制触发', () => {
    it('push 后调用 trigger 强制更新', async () => {
      const { useShallowArrayRef } = await import('@/composables/useShallowArrayRef')
      const { ref, trigger } = useShallowArrayRef([])
      const cb = vi.fn()
      watch(ref, cb)
      ref.value.push(1)
      await nextTick()
      expect(cb).not.toHaveBeenCalled()
      trigger()
      await nextTick()
      expect(cb).toHaveBeenCalled()
    })
  })

  describe('useShallowMapRef', () => {
    it('基础 set 触发 watch', async () => {
      const { useShallowMapRef } = await import('@/composables/useShallowArrayRef')
      const { ref, set } = useShallowMapRef(new Map())
      const cb = vi.fn()
      watch(ref, cb)
      const m = new Map([['k', 'v']])
      set(m)
      await nextTick()
      expect(cb).toHaveBeenCalled()
      expect(ref.value.get('k')).toBe('v')
    })

    it('default 是 empty Map', async () => {
      const { useShallowMapRef } = await import('@/composables/useShallowArrayRef')
      const { ref } = useShallowMapRef()
      expect(ref.value).toBeInstanceOf(Map)
      expect(ref.value.size).toBe(0)
    })
  })
})
