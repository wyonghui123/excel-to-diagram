/**
 * BO Service - v2 API 业务对象服务 (Facade)
 *
 * 统一入口，委托到子服务：
 *   boCrudService      — CRUD、批量操作
 *   associationService  — 关联操作（FR-GAP-018: 替代 boAssociationService）
 *   boExportImportService — 导入导出
 *   boSearchHelpService — 搜索帮助
 *   hierarchyService   — 层级操作（FR-GAP-004: 替代 boHierarchyService）
 */

import { BaseService } from '@/services/baseService'
import { BOExportImportService } from '@/services/bo/boExportImportService'
import { BOCrudService, setRefreshCoordinator as _setCrudCoordinator } from '@/services/bo/boCrudService'
import { BOSearchHelpService } from '@/services/bo/boSearchHelpService'
import * as _assocService from '@/services/associationService'
import * as _hierarchyService from '@/services/hierarchyService'

export function setRefreshCoordinator(coordinator) {
  _setCrudCoordinator(coordinator)
}

class BOService extends BaseService {
  constructor() {
    super(100, 5 * 60 * 1000)
    this._crud = new BOCrudService()
    this._exportImport = new BOExportImportService()
    this._searchHelp = new BOSearchHelpService()
  }

  create(objectType, data) { return this._crud.create(objectType, data) }
  read(objectType, id, options) { return this._crud.read(objectType, id, options) }
  query(objectType, params) { return this._crud.query(objectType, params) }
  update(objectType, id, data) { return this._crud.update(objectType, id, data) }
  delete(objectType, id) { return this._crud.delete(objectType, id) }
  batchCreate(objectType, items) { return this._crud.batchCreate(objectType, items) }
  batchDelete(objectType, ids) { return this._crud.batchDelete(objectType, ids) }
  executeAction(objectType, id, actionName, params) { return this._crud.executeAction(objectType, id, actionName, params) }
  deepInsert(objectType, parent, children, options) { return this._crud.deepInsert(objectType, parent, children, options) }
  suggestKeyTemplateCode(objectType, fieldValues, parentParams) { return this._crud.suggestKeyTemplateCode(objectType, fieldValues, parentParams) }

  // 关联操作 — 委托到 associationService（FR-GAP-018）
  associate(objectType, id, associationName, targetId, targetType) { return _assocService.associate(objectType, id, associationName, targetId, targetType) }
  dissociate(objectType, id, associationName, targetId, targetType) { return _assocService.dissociate(objectType, id, associationName, targetId, targetType) }
  queryAssociations(objectType, id, associationName, params) { return _assocService.queryAssociations(objectType, id, associationName, params) }
  queryAssociationsV2(objectType, id, associationName, params) { return _assocService.queryV2(objectType, id, associationName, params) }
  countAssociationsV2(objectType, id, associationName) { return _assocService.countV2(objectType, id, associationName) }
  assignAssociationV2(objectType, id, associationName, data) { return _assocService.assignV2(objectType, id, associationName, data) }
  unassignAssociationV2(objectType, id, associationName, data) { return _assocService.unassignV2(objectType, id, associationName, data) }
  // [FIX 2026-06-08] associationService.batchAssignV2 / batchUnassignV2 签名是
  // (objectType, id, associationName, targetIds, options = {}) — 第 4 参是 **数组** 不是对象。
  // 之前 boService 直接把 data 透传,导致 { target_ids: [...], target_type: '...' } 被当成
  // targetIds,内部 `targetIds?.length` 是 undefined → body 为空 → 后端 400。
  // 这里在 boService 层解包,保持对外的 (..., data) 干净 API,call site 不需要改。
  batchAssignAssociationsV2(objectType, id, associationName, data = {}) {
    return _assocService.batchAssignV2(
      objectType, id, associationName,
      data.target_ids || [],
      { targetType: data.target_type, metadata: data.metadata }
    )
  }
  batchUnassignAssociationsV2(objectType, id, associationName, data = {}) {
    return _assocService.batchUnassignV2(
      objectType, id, associationName,
      data.target_ids || [],
      { targetType: data.target_type, associationRecordIds: data.association_record_ids }
    )
  }
  batchQueryAssociations(objectType, associationName, data) { return _assocService.batchQuery(objectType, associationName, data) }
  retrieveWithAssociations(objectType, id, options) { return _assocService.retrieveWithAssociations(objectType, id, options) }

  downloadTemplate(objectType, params) { return this._exportImport.downloadTemplate(objectType, params) }
  previewImport(objectType, file, options) { return this._exportImport.previewImport(objectType, file, options) }
  exportData(objectType, params) { return this._exportImport.exportData(objectType, params) }
  exportDataAsync(objectType, params) { return this._exportImport.exportDataAsync(objectType, params) }
  getExportStatus(taskId) { return this._exportImport.getExportStatus(taskId) }
  downloadExportFile(downloadUrl, filename) { return this._exportImport.downloadExportFile(downloadUrl, filename) }
  async importData(objectType, file, options) {
    const result = await this._exportImport.importData(objectType, file, options)
    if (result.success) {
      this._crud._clearListCache(objectType)
    }
    return result
  }
  importDataAsync(file, conflictStrategy, context) { return this._exportImport.importDataAsync(file, conflictStrategy, context) }
  getImportStatus(taskId) { return this._exportImport.getImportStatus(taskId) }

  searchValueHelp(sourceType, sourceId, params) { return this._searchHelp.searchValueHelp(sourceType, sourceId, params) }
  resolveValueHelp(sourceType, sourceId, value, params) { return this._searchHelp.resolveValueHelp(sourceType, sourceId, value, params) }

  // [V1.2.0 2026-06-15] 跨域关系 Pick by Code 模式 (Phase 3)
  // 用于双模式 ValueHelp (List mode 不套 read scope → 看不到 D2; Pick by Code 逃生口)
  // 注: 这是 BO 元数据查询, 不受 read scope 限制 (只校验存在性 + product_id)
  async pickBoByCode(code, productId, options = {}) {
    if (!code || typeof code !== 'string') {
      return { success: false, message: 'MISSING_CODE', data: null }
    }
    if (!productId || (typeof productId !== 'number' && typeof productId !== 'string')) {
      return { success: false, message: 'MISSING_PRODUCT_ID', data: null }
    }
    const queryParams = new URLSearchParams()
    queryParams.set('code', code)
    queryParams.set('product_id', String(productId))
    if (options.reason) queryParams.set('reason', options.reason)
    if (options.includeOutOfScope) queryParams.set('include_out_of_scope', 'true')
    const path = `/bo/business_object/pick_by_code?${queryParams.toString()}`
    return this._request('GET', path)
  }

  // [V1.2.0 2026-06-15] 按 ID 精确查询 BO (供 ValueHelp 场景使用)
  // [V1.2.1 2026-06-16] 默认应用 dim scope 校验; 传 reason=value_help 跳过 (跨域关系创建逃生口)
  //   - 详情页请用 boService.read() (走 read_bo 路由, 有 dim scope 校验)
  //   - ValueHelp 场景: pickBoById(boId, { reason: 'value_help' })
  async pickBoById(boId, options = {}) {
    if (!boId) {
      return { success: false, message: 'MISSING_BO_ID', data: null }
    }
    const queryParams = new URLSearchParams()
    if (options.reason) queryParams.set('reason', options.reason)
    const qs = queryParams.toString()
    const path = `/bo/business_object/${boId}${qs ? '?' + qs : ''}`
    return this._request('GET', path)
  }

  // 层级操作 — 委托到 hierarchyService（FR-GAP-004）
  getHierarchyTree(rootType, params) { return _hierarchyService.getHierarchyTree(rootType, params) }
  getChildCount(objectType, id, params) { return _hierarchyService.getChildCount(objectType, id, params) }
  getObjectPath(objectType, id) { return _hierarchyService.getObjectPath(objectType, id) }

  clearAllCache() {
    this.cache.clear()
    // [FIX] boService 的 CRUD 实际由 _crud (BOCrudService) 执行，
    //   _crud 有自己独立的 cache (LRUCache 实例)。
    //   若只清 boService.cache 不清 _crud.cache，
    //   boService.query() 会从 _crud 的 cache 命中旧数据，
    //   导致 refresh() 后 UI 不更新。
    this._crud?.cache?.clear?.()
    _assocService.clearCache()
  }

  clearCache(objectType) {
    this._clearCache(objectType)
    // [FIX] 同步清理 _crud (BOCrudService) 的 cache，
    //   否则 _crud.query() 命中旧 cache，refresh() 不发请求 → UI 不刷新
    this._crud?._clearListCache?.(objectType)
    _assocService.clearCache(objectType)
  }
}

export const boService = new BOService()

export default boService
