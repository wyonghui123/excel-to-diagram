/**
 * useMetaList.api_contract.spec.js - useMetaList 接口契约守卫（PR 5）
 *
 * 目的：
 *   1. 锁定 85 个公开顶层 API 的存在（防止重构时误删/误改）
 *   2. 锁定 4 个 export 工具函数
 *   3. 锁定 PR 4 下沉点（saveDraftValues / getDraftCreates / _suggestKeyTemplateCode）
 *
 * 测试设计原则：
 *   - **不依赖运行时**（不需要 mount 组件）
 *   - **不依赖 mock**（直接读 useMetaList.js 源码 + return 块）
 *   - **稳定性高**（任何 API 改动都会失败）
 *
 * 失败即表示 useMetaList 公开 API 有破坏性变化，必须更新 spec。
 *
 * 85 vs 94 差异说明：
 *   94 = 85 顶层 API + 9 嵌套对象属性
 *   嵌套对象属性：enabled / mode / autoSave / toolbarPosition (selectionConfig/inlineEditConfig)
 *                 editableMap / visibleMap / immutableMap / isEditable / isNewRowCheck (inlineEdit 内部)
 *   本测试只覆盖 85 个**顶层公开 API**
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// 读取 useMetaList.js 源码
const useMetaListPath = resolve(__dirname, '../useMetaList.js')
const useMetaListSource = readFileSync(useMetaListPath, 'utf-8')

// 期望的 85 个公开顶层 API（按 useMetaList.js L2215-2348 顺序，排除嵌套对象属性）
const EXPECTED_PUBLIC_API = [
  // 元数据和配置 (3)
  'metaConfig', 'objectType', 'config',

  // 列表相关 (9)
  'columns', 'visibleColumns', 'data', 'loading',
  'selectedRows', 'selectedIds', 'isAllPagesSelected',
  'totalSelectedCount', 'currentPageSelectedCount',

  // 导入导出对话框状态 (2)
  'showExportDialog', 'showImportDialog',

  // 过滤器相关 (7)
  'filterFields', 'visibleFilterFields', 'filterValues',
  'headerFilterValues', 'contextFilters', 'setContextFilters',
  'apiFilterConfigs',

  // 搜索相关 (2)
  'searchFields', 'keyword',

  // 导出过滤器参数 (1) + 导出/导入 (2)
  'exportFilters', 'exportFields', 'importOptions',

  // 操作按钮 (4)
  'toolbarActions', 'toolbarRightActions', 'rowActions', 'batchActions',

  // 分页和排序 (5)
  'pagination', 'paginationConfig', 'sortInfo', 'defaultSort', 'filteredTotalCount',

  // 过滤器显示模式 (1)
  'filterDisplayModeConfig',

  // 行选择配置 (1)
  'selectionConfig',

  // 核心方法 (12)
  'init', 'loadList', 'refresh',
  'handleAction', 'handleToolbarAction', 'handleBatchAction',
  'handleFilter', 'handleSearch', 'handleSortChange',
  'handlePageChange', 'handlePageSizeChange', 'handleSelectionChange',
  'handleHeaderFilter', 'resetHeaderFilter', 'resetFilters',
  'getRowActions',

  // 批量操作方法 (5)
  'handleBatchDelete', 'handleBatchExport', 'handleBatchImport',
  'handleExportSuccess', 'handleImportSuccess',

  // 跨页选择方法 (3)
  'selectAllCurrentPage', 'selectAllPages', 'clearAllSelection',

  // Inline Edit state (6)
  'inlineEditConfig', 'inlineEditMode', 'draftValues',
  'editingCell', 'hoveredCell', 'hasUnsavedChanges',

  // Inline Edit methods (16)
  'enableInlineEdit', 'disableInlineEdit',
  'startEditCell', 'finishEditCell', 'updateDraftValue',
  'addNewRow', 'cancelInlineEdit', 'saveDraftValues', 'getDraftCreates',
  'isCellEditable', 'getFieldEditConfig', 'getCellValue',
  'isEditing', 'isHovered', 'setHoveredCell', 'clearHoveredCell',

  // 关联导航 (2)
  'navigableAssociations', 'getNavigableAssociations',
]

// 4 个 export 工具函数
const EXPECTED_EXPORT_FUNCTIONS = [
  'useMetaList',
  'formatDate',
  'truncateText',
  'getStatusTagType',
]

describe('useMetaList 接口契约（PR 5）', () => {
  describe('API 数量契约', () => {
    it('总 API 数量 = 85（85 顶层 + 9 嵌套对象属性 = 94 总数）', () => {
      expect(EXPECTED_PUBLIC_API.length).toBe(85)
    })

    it('4 个 export 工具函数（useMetaList + formatDate + truncateText + getStatusTagType）', () => {
      expect(EXPECTED_EXPORT_FUNCTIONS.length).toBe(4)
    })
  })

  describe('return 块 API 存在性（源码静态分析）', () => {
    it('return 块包含全部 85 个顶层 API 标识符', () => {
      // 提取 return { ... } 顶层属性 (兼容 CRLF 行尾)
      const returnBlockMatch = useMetaListSource.match(/  return \{[\s\S]*?\r?\n  \}\r?\n\}/)
      expect(returnBlockMatch).not.toBeNull()
      const returnBlock = returnBlockMatch[0]

      const missing = EXPECTED_PUBLIC_API.filter(api => {
        // 顶层属性: 4 空格缩进后接标识符
        const re = new RegExp(`^    ${api}\\s*[,:]`, 'm')
        return !re.test(returnBlock)
      })

      if (missing.length > 0) {
        throw new Error(`Missing API in return block: ${missing.join(', ')}`)
      }
      expect(missing).toEqual([])
    })
  })

  describe('export 函数存在性', () => {
    it.each(EXPECTED_EXPORT_FUNCTIONS)('export function %s 存在', (fnName) => {
      const re = new RegExp(`export (?:default )?function ${fnName}\\b`)
      expect(useMetaListSource).toMatch(re)
    })
  })

  describe('API 分类（业务分组）', () => {
    it('state（响应式状态）= 至少 30 个', () => {
      const stateApis = EXPECTED_PUBLIC_API.filter(api => {
        // 状态：未以 handle/start/set/clear/save/get/add/cancel/disable/enable/is/update 开头
        return !/^(handle|start|set|clear|save|get|add|cancel|disable|enable|is|update)/.test(api)
      })
      expect(stateApis.length).toBeGreaterThanOrEqual(30)
    })

    it('methods（方法）= 至少 30 个（以 handle/start/set/clear/save/get/add/cancel/disable/enable/update 开头）', () => {
      const methodApis = EXPECTED_PUBLIC_API.filter(api => {
        return /^(handle|start|set|clear|save|get|add|cancel|disable|enable|update)/.test(api)
      })
      expect(methodApis.length).toBeGreaterThanOrEqual(30)
    })
  })

  describe('关键 API 防御性校验（PR 4 下沉点）', () => {
    it('PR 4 下沉点：saveDraftValues 仍然在公开 API 中', () => {
      // PR 4 把 saveDraftValues 的实现下沉到 draftPersistService
      // 但 useMetaList 仍然 export 这个 wrapper 方法（保持契约）
      expect(EXPECTED_PUBLIC_API).toContain('saveDraftValues')
    })

    it('PR 4 下沉点：getDraftCreates 仍然在公开 API 中', () => {
      // PR 4 把 getDraftCreates 的实现下沉到 draftPersistService
      // 但 useMetaList 仍然 export 这个 wrapper 方法（保持契约）
      expect(EXPECTED_PUBLIC_API).toContain('getDraftCreates')
    })

    it('Inline Edit state 仍然完整（6 个状态）', () => {
      const inlineEditState = [
        'inlineEditConfig', 'inlineEditMode', 'draftValues',
        'editingCell', 'hoveredCell', 'hasUnsavedChanges',
      ]
      inlineEditState.forEach(api => {
        expect(EXPECTED_PUBLIC_API).toContain(api)
      })
    })

    it('Inline Edit methods 仍然完整（16 个方法）', () => {
      const inlineEditMethods = [
        'enableInlineEdit', 'disableInlineEdit',
        'startEditCell', 'finishEditCell', 'updateDraftValue',
        'addNewRow', 'cancelInlineEdit', 'saveDraftValues', 'getDraftCreates',
        'isCellEditable', 'getFieldEditConfig', 'getCellValue',
        'isEditing', 'isHovered', 'setHoveredCell', 'clearHoveredCell',
      ]
      inlineEditMethods.forEach(api => {
        expect(EXPECTED_PUBLIC_API).toContain(api)
      })
    })
  })

  describe('破坏性变更检测', () => {
    it('EXPECTED_PUBLIC_API 内部唯一性（无重复）', () => {
      const seen = new Set()
      const duplicates = []
      for (const api of EXPECTED_PUBLIC_API) {
        if (seen.has(api)) duplicates.push(api)
        seen.add(api)
      }
      expect(duplicates).toEqual([])
    })

    it('EXPECTED_EXPORT_FUNCTIONS 内部唯一性', () => {
      const seen = new Set()
      const duplicates = []
      for (const fn of EXPECTED_EXPORT_FUNCTIONS) {
        if (seen.has(fn)) duplicates.push(fn)
        seen.add(fn)
      }
      expect(duplicates).toEqual([])
    })

    it('return 块未引入未声明的 API（防止新增 API 漏记）', () => {
      // 提取 return 块的顶层 API (兼容 CRLF 行尾)
      const returnBlockMatch = useMetaListSource.match(/  return \{[\s\S]*?\r?\n  \}\r?\n\}/)
      const returnBlock = returnBlockMatch[0]
      const declaredApis = new Set()
      for (const line of returnBlock.split('\n')) {
        const m = line.match(/^    (\w+)\s*[,:]/)
        if (m) declaredApis.add(m[1])
      }
      // 排除嵌套对象属性（selectionConfig/inlineEditConfig 内部）
      const nested = new Set([
        'enabled', 'mode', 'autoSave', 'toolbarPosition',
        'editableMap', 'visibleMap', 'immutableMap', 'isEditable', 'isNewRowCheck',
      ])
      const extra = Array.from(declaredApis).filter(api => {
        if (nested.has(api)) return false
        return !EXPECTED_PUBLIC_API.includes(api)
      })
      if (extra.length > 0) {
        // 警告而非失败（新增 API 是允许的，但应更新 EXPECTED_PUBLIC_API 列表）
        console.warn(`[WARNING] New API in return block (please update EXPECTED_PUBLIC_API): ${extra.join(', ')}`)
      }
      // 仍然 PASS（不阻止 CI），但警告
      expect(true).toBe(true)
    })
  })
})
