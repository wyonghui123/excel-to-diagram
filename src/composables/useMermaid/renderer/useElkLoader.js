import mermaid from 'mermaid'

let elkLayoutsModule = null

/**
 * 加载并注册 ELK 布局引擎
 * 强制重新注册，因为 mermaid.initialize 可能会重置布局加载器
 * @param {boolean} forceReload - 是否强制重新加载模块
 * @returns {Promise<boolean>} - 是否成功加载
 */
export async function loadElkLayouts(forceReload = false) {
  try {
    if (forceReload || !elkLayoutsModule) {
      elkLayoutsModule = null
      console.log('[loadElkLayouts] Force reloading ELK layouts module...')
      elkLayoutsModule = await import('@mermaid-js/layout-elk')
    }
    mermaid.registerLayoutLoaders([...elkLayoutsModule.default])
    console.log('[loadElkLayouts] ELK layouts registered successfully')
    return true
  } catch (e) {
    console.warn('[loadElkLayouts] ELK layout not available:', e.message)
    elkLayoutsModule = null
    return false
  }
}

/**
 * 检查 ELK 是否已加载
 * @returns {boolean}
 */
export function isElkLoaded() {
  return elkLayoutsModule !== null
}

export function useElkLoader() {
  return {
    loadElkLayouts,
    isElkLoaded
  }
}