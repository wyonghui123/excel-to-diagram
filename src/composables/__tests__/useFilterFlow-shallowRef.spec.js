/**
 * 烟雾测试 useFilterFlow (W1 PR-1.3 shallowRef 改造后)
 */
import { describe, it, expect, vi } from 'vitest'
import { ref, nextTick } from 'vue'

describe('useFilterFlow shallowRef 改造烟雾测试 (W1 PR-1.3)', () => {
  it('模块加载 OK', async () => {
    const mod = await import('@/composables/useFilterFlow')
    expect(typeof mod.useFilterFlow).toBe('function')
  })

  it('useFilterFlow 返回 API 包含核心方法', async () => {
    const { useFilterFlow } = await import('@/composables/useFilterFlow')
    const target = ref(null)
    const flow = useFilterFlow({ target })
    expect(typeof flow.registerSource).toBe('function')
    expect(typeof flow.unregisterSource).toBe('function')
    expect(typeof flow.registerTarget).toBe('function')
    expect(typeof flow.getSource).toBe('function')
    expect(typeof flow.clearAll).toBe('function')
    expect(flow.sources).toBeDefined()  // computed
  })

  it('registerSource 后 sources computed 自动更新（shallowRef + trigger 路径）', async () => {
    const { useFilterFlow } = await import('@/composables/useFilterFlow')
    const target = ref(null)
    const flow = useFilterFlow({ target })

    const source = { id: 's1', value: ref(1) }
    flow.registerSource(source)
    await nextTick()

    expect(flow.sources.value).toHaveLength(1)
    expect(flow.sources.value[0].id).toBe('s1')
  })

  it('unregisterSource 后 sources 自动更新', async () => {
    const { useFilterFlow } = await import('@/composables/useFilterFlow')
    const target = ref(null)
    const flow = useFilterFlow({ target })

    flow.registerSource({ id: 's1', value: ref(1) })
    flow.registerSource({ id: 's2', value: ref(2) })
    await nextTick()
    expect(flow.sources.value).toHaveLength(2)

    flow.unregisterSource('s1')
    await nextTick()
    expect(flow.sources.value).toHaveLength(1)
    expect(flow.sources.value[0].id).toBe('s2')
  })

  it('getSource 返回已注册的 source', async () => {
    const { useFilterFlow } = await import('@/composables/useFilterFlow')
    const target = ref(null)
    const flow = useFilterFlow({ target })

    const s = { id: 's1', value: ref(1) }
    flow.registerSource(s)
    const retrieved = flow.getSource('s1')
    expect(retrieved).toBe(s)
  })

  it('不存在的 sourceId 返回 undefined', async () => {
    const { useFilterFlow } = await import('@/composables/useFilterFlow')
    const target = ref(null)
    const flow = useFilterFlow({ target })
    expect(flow.getSource('nonexistent')).toBeUndefined()
  })

  it('registerSource 接受 id 缺失的 source 但不崩溃（log error）', async () => {
    const { useFilterFlow } = await import('@/composables/useFilterFlow')
    const target = ref(null)
    const flow = useFilterFlow({ target })
    const consoleErr = vi.spyOn(console, 'error').mockImplementation(() => {})
    flow.registerSource({ value: ref(1) })  // 缺 id
    expect(consoleErr).toHaveBeenCalled()
    consoleErr.mockRestore()
  })
})
