import { defineStore } from 'pinia'
import { ref } from 'vue'

// [FR-006] 持久化 collapsed + width,避免每次刷新侧边栏回到默认状态
export const useSidebarStore = defineStore('sidebar', () => {
  const collapsed = ref(true)
  const width = ref(240)

  function toggle() {
    collapsed.value = !collapsed.value
  }

  function setWidth(newWidth: number) {
    width.value = Math.max(180, Math.min(400, newWidth))
  }

  return {
    collapsed,
    width,
    toggle,
    setWidth
  }
}, {
  persist: {
    pick: ['collapsed', 'width']
  }
})

export default useSidebarStore
