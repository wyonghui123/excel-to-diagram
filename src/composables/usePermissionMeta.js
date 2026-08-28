import { ref, shallowRef } from 'vue'
import {
  loadPermissionMetaWithScope,
  ScopeCodeInvalidError,
} from '@/services/permissionService'

/**
 * [P2-Matrix-02] 权限配置元数据加载（scopeCode 3 层保护 · BLOCKER）
 *
 * 供权限配置主面板（矩阵 / 菜单视图）复用的标准加载入口。核心保证：
 * - scopeCode 无效 → 捕获 ScopeCodeInvalidError → scopeError 状态（UI 渲染 Warning AppAlert）
 * - **绝不重试不带 scope_code 的请求**（Spec 5.5.4 P0 铁律 / 5.5.5 第 0 项验收③）
 *   —— 后端 400 SCOPE_CODE_INVALID 后，本 composable 不会再次发起任何 /meta 请求，
 *      meta 保持 null（页面不加载任何数据），只通过 scopeError 暴露错误供 UI 提示。
 * - 非 scope 类失败（网络 / 500 / 后端异常 / 业务错误）→ 静默降级，但通过 lastError
 *   暴露 message/httpStatus 给 UI，避免出现"元数据未就绪"这种无诊断信息的死文字。
 *
 * @returns {{
 *   meta: Ref<Object|null>,
 *   loading: Ref<boolean>,
 *   scopeError: Ref<ScopeCodeInvalidError|null>,
 *   availableScopeCodes: Ref<string[]>,
 *   lastError: Ref<{message: string, httpStatus: number|null, code: string|null}|null>,
 *   loadMetaWithScope: (scopeCode?: string) => Promise<Object|null>,
 *   clearScopeError: () => void,
 * }}
 */
export function usePermissionMeta() {
  const meta = shallowRef(null)
  const loading = ref(false)
  /** @type {import('vue').Ref<ScopeCodeInvalidError|null>} scopeCode 无效时置位（AppAlert 数据源） */
  const scopeError = ref(null)
  /** 后端返回的可用 scope code 白名单（供 UI 提示用户） */
  const availableScopeCodes = ref([])
  /** [v34 2026-08-27] 非 scope 类失败（500 / 网络 / 业务错误）的诊断信息，供 UI 显示具体原因 */
  const lastError = ref(null)

  async function loadMetaWithScope(scopeCode, extraParams = {}) {
    loading.value = true
    scopeError.value = null
    lastError.value = null
    try {
      const params = { ...extraParams }
      if (scopeCode) params.scope_code = scopeCode
      const r = await loadPermissionMetaWithScope(params)
      if (r.success && r.data) {
        meta.value = r.data
        return r.data
      }
      // 非 SCOPE_CODE_INVALID 的失败（网络 / 500 / 业务错误）：
      // 把 r.message / httpStatus / code 暴露给 UI，便于排查"元数据未就绪"。
      lastError.value = {
        message: r.message || `请求失败（httpStatus=${r.httpStatus ?? '?'}）`,
        httpStatus: r.httpStatus ?? null,
        code: r.code || null,
      }
      return null
    } catch (e) {
      if (e instanceof ScopeCodeInvalidError) {
        // [P0 铁律] scopeCode 无效：记录错误供 Warning AppAlert，meta 保持 null，
        // **不重试** —— 下一个请求必须由用户修正 scope_code 后重新触发。
        scopeError.value = e
        availableScopeCodes.value = e.availableScopeCodes || []
        meta.value = null
        return null
      }
      // 其他异常（如前端代码 bug / 序列化失败）也要让 UI 能定位
      lastError.value = {
        message: e?.message || String(e),
        httpStatus: null,
        code: e?.name || 'EXCEPTION',
      }
      throw e
    } finally {
      loading.value = false
    }
  }

  function clearScopeError() {
    scopeError.value = null
  }

  return {
    meta,
    loading,
    scopeError,
    availableScopeCodes,
    lastError,
    loadMetaWithScope,
    clearScopeError,
  }
}
