import { defineStore } from 'pinia'

export const useListActionStore = defineStore('listAction', () => {
  const actionHandlers = new Map()

  function dispatchAction(objectType, action, row) {
    const handler = actionHandlers.get(objectType)
    if (handler) {
      handler(action, row)
    }
  }

  function registerHandler(objectType, handler) {
    actionHandlers.set(objectType, handler)
    return () => {
      actionHandlers.delete(objectType)
    }
  }

  return { dispatchAction, registerHandler }
})
