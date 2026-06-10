/**
 * draftPersistService.spec.js - 草稿持久化 service 单测
 *
 * 覆盖矩阵（17 个用例）：
 * 1-3. hasDraftChanges: _ 开头 / 值相同 / 值不同
 * 4-7. buildDraftPayload: 新建行+保留 _id / 更新行 / 跳过 _ / 跳过 id
 * 8-10. collectDrafts: 空 / 全部未变更(new) / 部分变更(混合)
 * 11-14. saveAllDrafts: 空 / 全部未变更 / 成功 / 失败
 * 15-17. getDraftCreates: 跳过非 new / 跳过未变更 / 包含 payload
 *
 * 重要：service 行为严格匹配 useMetaList 原代码（字节级一致）：
 * - 非 __new_ 行：initialValues = {}（不查找 _initialValues）
 * - __new_ 行：查找 _initialValues
 * - buildDraftPayload 不跳过 fields 中的 id 字段（仅跳过 row 中的 id）
 */

import { describe, it, expect, vi } from 'vitest'
import {
  hasDraftChanges,
  buildDraftPayload,
  collectDrafts,
  saveAllDrafts,
  getDraftCreates,
} from '@/services/draftPersistService'

describe('draftPersistService', () => {
  describe('hasDraftChanges', () => {
    it('TC-1: _ 开头的字段被跳过', () => {
      expect(hasDraftChanges({ _x: 1, _y: 2 }, {})).toBe(false)
    })

    it('TC-2: 值相同时无变更', () => {
      expect(hasDraftChanges({ name: 'foo' }, { name: 'foo' })).toBe(false)
    })

    it('TC-3: 值不同时有变更', () => {
      expect(hasDraftChanges({ name: 'foo' }, { name: 'bar' })).toBe(true)
    })

    // [FIX 2026-06-10] 新行：只要有任一非 context 字段有非空值即视为有变更
    // 避免"用户接受 keyTemplateService 自动建议的 code，但保存时
    //  fields.code === initialValues.code 导致 hasDraftChanges=false，
    //  新行被静默从 data 移除"的 bug
    describe('新行 (isNewRow=true)', () => {
      it('TC-N1: 新行带自动建议的 code（值与 initial 相同）应视为有变更', () => {
        // 模拟场景：用户新增行，auto-suggest 填入 code='AUTO_001'，
        // 用户没改就保存。旧逻辑会因 fields===initial 返回 false 而静默删除新行。
        expect(
          hasDraftChanges(
            { code: 'AUTO_001', enum_type_id: 'annotation_category' },
            { code: 'AUTO_001', enum_type_id: 'annotation_category' },
            true
          )
        ).toBe(true)
      })

      it('TC-N2: 新行只有 *_id context 字段时视为无变更（取消新建）', () => {
        // 用户点了"新增"但啥也没填就保存，应取消
        expect(
          hasDraftChanges(
            { enum_type_id: 'annotation_category' },
            { enum_type_id: 'annotation_category' },
            true
          )
        ).toBe(false)
      })

      it('TC-N3: 新行 _ 开头字段被跳过（即使有值）', () => {
        expect(
          hasDraftChanges(
            { _initial: 1, code: 'X' },
            {},
            true
          )
        ).toBe(true)
      })

      it('TC-N4: 新行 code 为空字符串视为无变更', () => {
        expect(
          hasDraftChanges(
            { code: '', enum_type_id: 'x' },
            { enum_type_id: 'x' },
            true
          )
        ).toBe(false)
      })

      it('TC-N5: 新行 code=null 视为无变更', () => {
        expect(
          hasDraftChanges(
            { code: null, enum_type_id: 'x' },
            { enum_type_id: 'x' },
            true
          )
        ).toBe(false)
      })

      it('TC-N6: 新行 user 显式改 code 视为有变更', () => {
        expect(
          hasDraftChanges(
            { code: 'USER_CHANGED' },
            { code: 'AUTO' },
            true
          )
        ).toBe(true)
      })
    })

    describe('现有行 (isNewRow=false，默认)', () => {
      it('TC-E1: isNewRow 默认为 false，行为与旧逻辑一致', () => {
        expect(hasDraftChanges({ name: 'foo' }, { name: 'foo' })).toBe(false)
      })

      it('TC-E2: 显式传 isNewRow=false 也走旧逻辑', () => {
        expect(
          hasDraftChanges({ name: 'foo' }, { name: 'foo' }, false)
        ).toBe(false)
      })
    })
  })

  describe('buildDraftPayload', () => {
    it('TC-4: 新建行保留 * _id 字段', () => {
      const payload = buildDraftPayload(
        { name: 'foo' },
        { id: '__new_1', parent_id: 99, name: 'old' },
        true
      )
      expect(payload).toEqual({ parent_id: 99, name: 'foo' })
    })

    it('TC-5: 更新行不保留 _id（仅 fields）', () => {
      const payload = buildDraftPayload(
        { name: 'foo' },
        { id: 1, parent_id: 99 },
        false
      )
      expect(payload).toEqual({ name: 'foo' })
    })

    it('TC-6: 跳过 _ 开头的字段', () => {
      const payload = buildDraftPayload({ _foo: 1, name: 'x' }, {}, true)
      expect(payload).toEqual({ name: 'x' })
    })

    it('TC-7: 跳过 row 中的 id 字段（fields 中的 id 保留以匹配原行为）', () => {
      // 原 useMetaList 行为：fields 中的 id 不被特殊处理
      // 实际应用场景：fields 中一般不会包含 id
      const payload = buildDraftPayload({ name: 'x' }, { id: 1, name: 'y' }, true)
      // row.id=1 被跳过（startsWith('_') || key === 'id'）
      // fields.name='x' 被 push
      expect(payload).toEqual({ name: 'x' })
    })
  })

  describe('collectDrafts', () => {
    it('TC-8: 空 drafts 返回空数组', () => {
      const result = collectDrafts(new Map(), [])
      expect(result.drafts).toEqual([])
      expect(result.toRemove).toEqual([])
    })

    it('TC-9: __new_ 行只有 *_id context 字段时进入 toRemove（用 __new_ 触发 initialValues 查找）', () => {
      // [FIX 2026-06-10] 新行：只有 *_id context 字段（来自 filterValues 的 parent context）
      // 视为无变更，触发取消新建。普通 user-editable 字段（name/code 等）即使值与
      // initial 相同也视为有变更（keyTemplateService 自动建议场景）。
      const drafts = new Map([
        ['__new_1', { enum_type_id: 'annotation_category' }],
      ])
      const data = [{ id: '__new_1', _initialValues: { enum_type_id: 'annotation_category' } }]
      const result = collectDrafts(drafts, data)
      expect(result.drafts).toEqual([])
      expect(result.toRemove.length).toBe(2)  // 1 for removeFromData + 1 for draftValues.delete
    })

    it('TC-10: 混合 new 和 非 new 行的部分变更', () => {
      // 非 new 行 (id=1)：initialValues={}，所以总是有变更（除非 fields 全是 _）
      // new 行 (__new_2)：initialValues={name:'original'}，fields.name='changed'，有变更
      const drafts = new Map([
        [1, { name: 'foo' }],                    // 非 new：总是变更
        ['__new_2', { name: 'changed' }],        // new：有变更
      ])
      const data = [
        { id: 1, _initialValues: { name: 'foo' } },
        { id: '__new_2', _initialValues: { name: 'original' } },
      ]
      const result = collectDrafts(drafts, data)
      expect(result.drafts.length).toBe(2)  // 两个都有变更
      expect(result.drafts[0].row_id).toBe(1)
      expect(result.drafts[0].is_new).toBe(false)
      expect(result.drafts[1].row_id).toBe('__new_2')
      expect(result.drafts[1].is_new).toBe(true)
      expect(result.toRemove.length).toBe(0)
    })
  })

  describe('saveAllDrafts (主入口)', () => {
    it('TC-11: 空 draftValues 提前返回', async () => {
      const result = await saveAllDrafts({
        objectType: 'order',
        draftValues: new Map(),
        data: { value: [] },
        callPost: vi.fn(),
      })
      expect(result.success).toBe(true)
      expect(result.created).toBe(0)
      expect(result.updated).toBe(0)
    })

    it('TC-12: __new_ 行只有 *_id context 字段时返回空', async () => {
      // [FIX 2026-06-10] 新行：只有 *_id context 字段视为无变更，不调后端
      const drafts = new Map([['__new_1', { enum_type_id: 'annotation_category' }]])
      const data = [{ id: '__new_1', _initialValues: { enum_type_id: 'annotation_category' } }]  // C2 修复：纯 array 而非 ref
      const callPost = vi.fn()
      const result = await saveAllDrafts({
        objectType: 'order',
        draftValues: drafts,
        data,
        callPost,
      })
      expect(result.success).toBe(true)
      expect(callPost).not.toHaveBeenCalled()
    })

    it('TC-13: 成功返回 created/updated', async () => {
      const drafts = new Map([[1, { name: 'changed' }]])
      const data = [{ id: 1, _initialValues: { name: 'original' } }]  // C2 修复：纯 array 而非 ref
      const callPost = vi.fn().mockResolvedValue({
        success: true,
        data: { created: [1, 2], updated: [3] },
      })
      const showMessage = { success: vi.fn() }
      const result = await saveAllDrafts({
        objectType: 'order',
        draftValues: drafts,
        data,
        callPost,
        showMessage,
      })
      expect(result.success).toBe(true)
      expect(result.created).toBe(2)
      expect(result.updated).toBe(1)
      expect(callPost).toHaveBeenCalledWith('batch_save', expect.objectContaining({
        object_type: 'order',
        drafts: expect.any(Array),
      }))
      expect(showMessage.success).toHaveBeenCalled()
    })

    it('TC-14: 失败返回 error', async () => {
      const drafts = new Map([[1, { name: 'changed' }]])
      const data = { value: [{ id: 1, _initialValues: { name: 'orig' } }] }
      const callPost = vi.fn().mockResolvedValue({
        success: false,
        message: 'Save failed',
        data: { failures: [{ message: 'X failed' }] },
      })
      const result = await saveAllDrafts({
        objectType: 'order',
        draftValues: drafts,
        data,
        callPost,
      })
      expect(result.success).toBe(false)
      expect(result.error).toContain('1 项失败')
    })

    // === P3-Branch: 覆盖率补强（Branch 80.76% → 90%） ===

    it('TC-15b (Branch L202-204): callPost 抛错时返回 error', async () => {
      // branch: catch (e) { return { success: false, error: e.message || String(e), toRemove } }
      const drafts = new Map([[1, { name: 'changed' }]])
      const data = [{ id: 1, _initialValues: { name: 'orig' } }]
      const callPost = vi.fn().mockRejectedValue(new Error('Network timeout'))
      const result = await saveAllDrafts({
        objectType: 'order',
        draftValues: drafts,
        data,
        callPost,
      })
      expect(result.success).toBe(false)
      expect(result.error).toBe('Network timeout')
      expect(result.toRemove).toBeDefined()
    })

    it('TC-15c (Branch L202-204): callPost 抛非 Error 对象时用 String(e) fallback', async () => {
      // branch: error: e.message || String(e) - e 不是 Error 时 String(e) 兜底
      const drafts = new Map([[1, { name: 'changed' }]])
      const data = [{ id: 1, _initialValues: { name: 'orig' } }]
      const callPost = vi.fn().mockRejectedValue('string error')  // 字符串而非 Error
      const result = await saveAllDrafts({
        objectType: 'order',
        draftValues: drafts,
        data,
        callPost,
      })
      expect(result.success).toBe(false)
      expect(result.error).toBe('string error')
    })

    it('TC-15d (Branch L197/200): 失败时 data.failures 空 + message 空 → fallback "保存失败"', async () => {
      // branch: failures = r.data?.failures || [] + r.message || '保存失败'
      const drafts = new Map([[1, { name: 'changed' }]])
      const data = [{ id: 1, _initialValues: { name: 'orig' } }]
      const callPost = vi.fn().mockResolvedValue({ success: false })  // data 和 message 都为空
      const result = await saveAllDrafts({
        objectType: 'order',
        draftValues: drafts,
        data,
        callPost,
      })
      expect(result.success).toBe(false)
      expect(result.error).toBe('保存失败')  // fallback
      expect(result.failures).toEqual([])
    })

    it('TC-15e (Branch L198-199): 失败时 failures 非空 → 详细错误消息', async () => {
      // branch: failures.length > 0 → `${failures.length} 项失败: ${failures[0].message}`
      const drafts = new Map([[1, { name: 'changed' }]])
      const data = [{ id: 1, _initialValues: { name: 'orig' } }]
      const callPost = vi.fn().mockResolvedValue({
        success: false,
        data: { failures: [{ message: 'Validation X' }, { message: 'Validation Y' }] },
      })
      const result = await saveAllDrafts({
        objectType: 'order',
        draftValues: drafts,
        data,
        callPost,
      })
      expect(result.success).toBe(false)
      expect(result.error).toBe('2 项失败: Validation X')  // failures 路径
    })
  })

  describe('getDraftCreates', () => {
    it('TC-15: 跳过非 __new_ 开头的行', () => {
      const drafts = new Map([[1, { name: 'x' }]])
      const data = []
      const result = getDraftCreates(drafts, data)
      expect(result).toEqual([])
    })

    it('TC-16: 跳过只有 *_id context 字段的未变更 __new_ 行', () => {
      // [FIX 2026-06-10] 新行：只有 *_id context 字段视为无变更，跳过
      const drafts = new Map([['__new_1', { enum_type_id: 'annotation_category' }]])
      const data = [{ id: '__new_1', _initialValues: { enum_type_id: 'annotation_category' } }]
      const result = getDraftCreates(drafts, data)
      expect(result).toEqual([])
    })

    it('TC-17: 包含已变更的新行 payload', () => {
      const drafts = new Map([['__new_1', { name: 'changed' }]])
      const data = [{ id: '__new_1', _initialValues: { name: 'original' } }]
      const result = getDraftCreates(drafts, data)
      expect(result).toEqual([{ name: 'changed' }])
    })
  })
})
