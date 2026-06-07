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
  batchAssignAssociationsV2(objectType, id, associationName, data) { return _assocService.batchAssignV2(objectType, id, associationName, data) }
  batchUnassignAssociationsV2(objectType, id, associationName, data) { return _assocService.batchUnassignV2(objectType, id, associationName, data) }
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

  // 层级操作 — 委托到 hierarchyService（FR-GAP-004）
  getHierarchyTree(rootType, params) { return _hierarchyService.getHierarchyTree(rootType, params) }
  getChildCount(objectType, id, params) { return _hierarchyService.getChildCount(objectType, id, params) }
  getObjectPath(objectType, id) { return _hierarchyService.getObjectPath(objectType, id) }

  clearAllCache() {
    this.cache.clear()
    _assocService.clearCache()
  }

  clearCache(objectType) {
    this._clearCache(objectType)
    _assocService.clearCache(objectType)
  }
}

export const boService = new BOService()

export default boService
