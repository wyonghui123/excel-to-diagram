import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface Notification {
  id: string
  title: string
  type?: 'info' | 'success' | 'warning' | 'error'
  read?: boolean
  createdAt?: string
}

export const useNotificationStore = defineStore('notification', () => {
  const notifications = ref<Notification[]>([])
  const unreadCount = computed(() => notifications.value.filter(n => !n.read).length)

  function setNotifications(items: Notification[]) {
    notifications.value = items
  }

  function markNotificationRead(id: string) {
    const notification = notifications.value.find(n => n.id === id)
    if (notification) {
      notification.read = true
    }
  }

  function markAllNotificationsRead() {
    notifications.value.forEach(n => n.read = true)
  }

  return {
    notifications,
    unreadCount,
    setNotifications,
    markNotificationRead,
    markAllNotificationsRead
  }
}, {
  persist: {
    key: 'notification-store',
    storage: sessionStorage,
    paths: ['notifications']
  }
})

export default useNotificationStore
