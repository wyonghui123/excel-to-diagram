import { describe, it, expect, vi, beforeEach } from 'vitest'

// mock permissionService，隔离网络层
vi.mock('@/services/permissionService', () => ({
  loadPermissionMetaWithScope: vi.fn(),
  ScopeCodeInvalidError: class ScopeCodeInvalidError extends Error {
    constructor(message, availableScopeCodes = []) {
      super(message)
      this.name = 'ScopeCodeInvalidError'
      this.availableScopeCodes = availableScopeCodes
    }
  },
}))

import {
  loadPermissionMetaWithScope,
  ScopeCodeInvalidError,
} from '@/services/permissionService'
import { usePermissionMeta } from '../usePermissionMeta'

const MOCK_META = { dimension_priority: { product: 0 }, resource_type_labels: {} }

describe('usePermissionMeta（P2-Matrix-02 scopeCode 3 层保护）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('scopeCode 无效 → scopeError 置位、meta 保持 null、仅调用 1 次（绝不重试）', async () => {
    const err = new ScopeCodeInvalidError('范围编码无效', ['SCP', 'SCM'])
    loadPermissionMetaWithScope.mockRejectedValueOnce(err)

    const { meta, scopeError, availableScopeCodes, loadMetaWithScope } = usePermissionMeta()

    const result = await loadMetaWithScope('INVALID_VALUE')

    expect(result).toBeNull()
    expect(meta.value).toBeNull()
    expect(scopeError.value).toBeInstanceOf(ScopeCodeInvalidError)
    expect(scopeError.value.availableScopeCodes).toEqual(['SCP', 'SCM'])
    expect(availableScopeCodes.value).toEqual(['SCP', 'SCM'])
    // [P0 铁律] 失败后绝对无后续不带 scope_code 的重试请求
    expect(loadPermissionMetaWithScope).toHaveBeenCalledTimes(1)
    expect(loadPermissionMetaWithScope).toHaveBeenCalledWith({ scope_code: 'INVALID_VALUE' })
  })

  it('scopeCode 有效 → meta 正常设置、无错误、只调用 1 次', async () => {
    loadPermissionMetaWithScope.mockResolvedValueOnce({ success: true, data: MOCK_META })

    const { meta, scopeError, loadMetaWithScope } = usePermissionMeta()

    const result = await loadMetaWithScope('SCP')

    expect(result).toEqual(MOCK_META)
    expect(meta.value).toEqual(MOCK_META)
    expect(scopeError.value).toBeNull()
    expect(loadPermissionMetaWithScope).toHaveBeenCalledTimes(1)
    expect(loadPermissionMetaWithScope).toHaveBeenCalledWith({ scope_code: 'SCP' })
  })

  it('不带 scopeCode → 不携带 scope_code 参数正常加载', async () => {
    loadPermissionMetaWithScope.mockResolvedValueOnce({ success: true, data: MOCK_META })

    const { meta, loadMetaWithScope } = usePermissionMeta()

    await loadMetaWithScope()

    expect(meta.value).toEqual(MOCK_META)
    expect(loadPermissionMetaWithScope).toHaveBeenCalledWith({})
  })

  it('响应 success=false（非 scope 错误）→ 返回 null 静默降级，不抛错不白屏', async () => {
    loadPermissionMetaWithScope.mockResolvedValueOnce({ success: false, message: '500' })

    const { meta, scopeError, loadMetaWithScope } = usePermissionMeta()

    const result = await loadMetaWithScope('SCP')

    expect(result).toBeNull()
    expect(meta.value).toBeNull()
    expect(scopeError.value).toBeNull() // 非 scope 错误不置位 AppAlert
  })

  it('非 ScopeCodeInvalidError 异常 → 原样抛出（不吞掉未知错误）', async () => {
    const boom = new Error('network down')
    loadPermissionMetaWithScope.mockRejectedValueOnce(boom)

    const { loadMetaWithScope } = usePermissionMeta()

    await expect(loadMetaWithScope('SCP')).rejects.toThrow('network down')
  })

  it('clearScopeError 清空 scopeError', async () => {
    loadPermissionMetaWithScope.mockRejectedValueOnce(
      new ScopeCodeInvalidError('范围编码无效', ['SCP'])
    )

    const { loadMetaWithScope, scopeError, clearScopeError } = usePermissionMeta()

    await loadMetaWithScope('BAD')
    expect(scopeError.value).not.toBeNull()

    clearScopeError()
    expect(scopeError.value).toBeNull()
  })
})
