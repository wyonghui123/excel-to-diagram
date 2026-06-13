/**
 * useShallowArrayRef - 大数组/大对象的 shallowRef 包装
 *
 * [W1 PR-1.3] 用于替代 ref([]) 的大数组场景
 *
 * 问题：
 *   const items = ref([])   // 默认是 reactive 数组（每个元素都是 Proxy）
 *   items.value.push(x)      // 触发整条链路更新
 *   watch(items, ..., { deep: true })  // 性能灾难（10000 元素 × 嵌套对象）
 *
 * 优化：
 *   const items = useShallowArrayRef([])  // shallowRef
 *   items.set([...newItems])               // 显式整体替换触发更新
 *   items.value.push(x)                    // push 不触发响应式（需 set 替换）
 *   watch(items.ref, ...)                   // 浅 watch（默认），无需 deep:true
 *
 * 性能提升：
 *   - 10000 元素数组：reactive 创建 10000 个 Proxy → shallowRef 0 个
 *   - watch 触发次数：N×M（嵌套） → 1（整体替换）
 */
import { shallowRef, triggerRef } from 'vue'

export function useShallowArrayRef(initialValue = []) {
  const ref = shallowRef(Array.isArray(initialValue) ? initialValue : [initialValue])

  function set(newArray) {
    ref.value = Array.isArray(newArray) ? newArray : [newArray]
  }

  function trigger() {
    // 强制触发更新（用于 push 后想触发 watcher 但不想整体替换）
    triggerRef(ref)
  }

  return { ref, set, trigger }
}

export function useShallowMapRef(initialValue = new Map()) {
  const ref = shallowRef(initialValue)

  function set(newMap) {
    ref.value = newMap
  }

  function trigger() {
    triggerRef(ref)
  }

  return { ref, set, trigger }
}

export default useShallowArrayRef
