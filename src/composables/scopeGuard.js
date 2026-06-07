import { ref } from 'vue'

/**
 * 统一的 setCheckedKeys → @check 循环阻断守卫
 *
 * 使用计数器（而非布尔值）防御 Element Plus 内部可能的递归 @check 触发。
 * enter/exit 配对调用，depth > 0 时 active() 返回 true。
 *
 * 用法：
 *   const guard = createScopeGuard()
 *   guard.enter()
 *   treeRef.value.setCheckedKeys(keys)
 *   guard.exit()
 *
 *   // 在 @check handler 中：
 *   if (guard.active()) return
 */
export function createScopeGuard() {
  const depth = ref(0)

  return {
    /** 进入保护区，depth++ */
    enter() {
      depth.value++
    },

    /** 退出保护区，depth-- */
    exit() {
      if (depth.value > 0) {
        depth.value--
      }
    },

    /** 当前是否在保护区内（depth > 0） */
    active() {
      return depth.value > 0
    }
  }
}
