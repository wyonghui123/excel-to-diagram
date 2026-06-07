import { ref, readonly } from 'vue'

const messages = ref([])
let messageId = 0

function showMessage(message, type = 'success', duration = 3000) {
  const id = ++messageId
  messages.value.push({ id, message, type, duration })
  
  if (duration > 0) {
    setTimeout(() => {
      removeMessage(id)
    }, duration)
  }
  
  return id
}

function removeMessage(id) {
  const index = messages.value.findIndex(m => m.id === id)
  if (index > -1) {
    messages.value.splice(index, 1)
  }
}

function clearAll() {
  messages.value = []
}

function success(message, duration) {
  return showMessage(message, 'success', duration)
}

function error(message, duration) {
  return showMessage(message, 'error', duration)
}

function warning(message, duration) {
  return showMessage(message, 'warning', duration)
}

function info(message, duration) {
  return showMessage(message, 'info', duration)
}

async function confirm({ title = '确认', content = '', type = 'warning' } = {}) {
  return new Promise((resolve) => {
    const confirmed = window.confirm(content || title)
    resolve(confirmed)
  })
}

export function useMessage() {
  return {
    messages: readonly(messages),
    show: showMessage,
    success,
    error,
    warning,
    info,
    confirm,
    remove: removeMessage,
    clearAll,
  }
}
