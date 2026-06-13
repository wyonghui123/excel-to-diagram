/**
 * useMetaList.scenarios.spec.js - 8 上层使用场景组件静态分析 (FR-008 v3 验证)
 *
 * 目的：
 *   验证 v3 spec 识别的 8 个上层使用场景的 Vue 组件仍正确引用 MetaListPage/useMetaList,
 *   且传入的 props 跟 spec 期望一致。这是拆分前置的最后一道防线。
 *
 * 8 场景 + 静态验证点：
 *   1. GenericListPage (GenericObjectList.vue) - displayMode: 'page'
 *   2. AssociationSection (1对多) - displayMode: 'page', initialFilters, rowMutability
 *   3. AssociationSection (多对多) - displayMode: 'embedded', columnsOverride, fetcher
 *   4. AssociationSection (Annotation) - displayMode: 'embedded', objectType: 'annotation'
 *   5. ObjectChildSection - useMetaList: true, mode: 'element-plus'
 *   6. SearchHelpDialog - displayMode: 'dialog', hideToolbar, columnsOverride
 *   7. AssignmentDialog - displayMode: 'dialog', excludeIds
 *   8. MultiObjectPage - 多个 MetaListPage 实例
 *
 * 不依赖 dev server, 直接读 .vue 文件源码 + 字符串匹配。
 */

import { describe, it, expect } from 'vitest'
import fs from 'fs'
import path from 'path'

const SRC = path.resolve(process.cwd(), 'src')

function readFile(p) {
  return fs.readFileSync(path.join(SRC, p), 'utf8')
}

function fileExists(p) {
  return fs.existsSync(path.join(SRC, p))
}

describe('useMetaList 8 上层使用场景组件引用 (FR-008 v3)', () => {
  describe('场景 1: GenericListPage', () => {
    it('GenericObjectList.vue 存在并导入 MetaListPage', () => {
      expect(fileExists('views/GenericObjectList.vue')).toBe(true)
      const src = readFile('views/GenericObjectList.vue')
      expect(src).toMatch(/import.*MetaListPage.*from.*MetaListPage/)
    })

    it('GenericObjectList.vue 默认 displayMode 是 page (隐式)', () => {
      const src = readFile('views/GenericObjectList.vue')
      // 不传 displayMode 默认就是 'page'
      expect(src).not.toMatch(/display-mode="embedded"|display-mode="dialog"/)
    })

    it('GenericObjectList.vue 传入 enableDetail + enableAutoCrud', () => {
      const src = readFile('views/GenericObjectList.vue')
      expect(src).toMatch(/enable-detail/)
      expect(src).toMatch(/enable-auto-crud/)
    })
  })

  describe('场景 2-4: AssociationSection (1对多/多对多/Annotation)', () => {
    it('AssociationSection.vue 存在', () => {
      expect(fileExists('components/common/ObjectPage/AssociationSection.vue')).toBe(true)
    })

    it('场景 3 (多对多) 用 displayMode=embedded + 4 个 *Override', () => {
      const src = readFile('components/common/ObjectPage/AssociationSection.vue')
      expect(src).toMatch(/display-mode="'embedded'"/)
      expect(src).toMatch(/columns-override/)
      expect(src).toMatch(/row-actions-override/)
      expect(src).toMatch(/toolbar-actions-override/)
      expect(src).toMatch(/batch-actions-override/)
    })

    it('场景 4 (Annotation) objectType=annotation + annotationService fetcher', () => {
      const src = readFile('components/common/ObjectPage/AssociationSection.vue')
      expect(src).toMatch(/object-type="annotation"/)
      expect(src).toMatch(/annotationService/)
    })

    it('场景 2 (1对多) initialFilters 用 parent_id 过滤', () => {
      const src = readFile('components/common/ObjectPage/AssociationSection.vue')
      // associationFilters 用 ${objectType}_id 作为 key
      expect(src).toMatch(/\$\{props\.objectType\}_id/)
    })

    it('useBoAction 或 boService.queryAssociations 自定义 fetcher', () => {
      const src = readFile('components/common/ObjectPage/AssociationSection.vue')
      expect(src).toMatch(/queryAssociations/)
    })
  })

  describe('场景 5: ObjectChildSection', () => {
    it('ObjectChildSection.vue 存在并支持 useMetaList 开关', () => {
      expect(fileExists('components/common/ObjectChildSection/ObjectChildSection.vue')).toBe(true)
      const src = readFile('components/common/ObjectChildSection/ObjectChildSection.vue')
      expect(src).toMatch(/useMetaList/)
      expect(src).toMatch(/<MetaListPage/)
    })

    it('ObjectChildSection 传入 initialFilters + rowMutability', () => {
      const src = readFile('components/common/ObjectChildSection/ObjectChildSection.vue')
      expect(src).toMatch(/initial-filters/)
      expect(src).toMatch(/row-mutability/)
    })
  })

  describe('场景 6: SearchHelpDialog (ValueHelp)', () => {
    it('SearchHelpDialog.vue 用 displayMode=dialog', () => {
      expect(fileExists('components/common/SearchHelpDialog.vue')).toBe(true)
      const src = readFile('components/common/SearchHelpDialog.vue')
      expect(src).toMatch(/display-mode="'dialog'"/)
    })

    it('SearchHelpDialog 强制 pageSize ≤ 15', () => {
      const src = readFile('components/common/SearchHelpDialog.vue')
      expect(src).toMatch(/val\s*>\s*0\s*&&\s*val\s*<=\s*15/)
    })

    it('SearchHelpDialog 传 columnsOverride + hideToolbar + enableDetail=false', () => {
      const src = readFile('components/common/SearchHelpDialog.vue')
      expect(src).toMatch(/columns-override/)
      expect(src).toMatch(/hide-toolbar/)
      expect(src).toMatch(/enable-detail="false"/)
    })
  })

  describe('场景 7: AssignmentDialog', () => {
    it('AssignmentDialog.vue 存在并用 displayMode=dialog + excludeIds', () => {
      expect(fileExists('components/common/AssignmentDialog/AssignmentDialog.vue')).toBe(true)
      const src = readFile('components/common/AssignmentDialog/AssignmentDialog.vue')
      expect(src).toMatch(/display-mode="'dialog'"/)
      expect(src).toMatch(/exclude-ids/)
    })

    it('AssignmentDialog pageSize=15, pageSizes=[15,30,50,100]', () => {
      const src = readFile('components/common/AssignmentDialog/AssignmentDialog.vue')
      expect(src).toMatch(/pageSize:\s*15/)
      expect(src).toMatch(/pageSizes:\s*\[15,\s*30,\s*50,\s*100\]/)
    })
  })

  describe('场景 8: MultiObjectPage', () => {
    it('MultiObjectManagementPage.vue 存在', () => {
      expect(fileExists('components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue')).toBe(true)
    })

    it('useMultiObjectPage composable 存在', () => {
      expect(fileExists('composables/useMultiObjectPage.js')).toBe(true)
    })
  })

  describe('公共 API 完整性 (8 场景都用)', () => {
    it('useMetaList.js 导出 useMetaList 主入口', () => {
      const src = readFile('composables/useMetaList.js')
      expect(src).toMatch(/export function useMetaList/)
    })

    it('formatDate 工具函数导出 (供 AuditLog / SystemAdmin / InlineEditCell 使用)', () => {
      const src = readFile('composables/useMetaList.js')
      expect(src).toMatch(/export function formatDate/)
    })

    it('公共 API 包含 init/loadList/refresh/handleAction/handleBatchAction', () => {
      const src = readFile('composables/useMetaList.js')
      for (const fn of ['init', 'loadList', 'refresh', 'handleAction', 'handleBatchAction']) {
        expect(src).toMatch(new RegExp(`\\b${fn}\\b`))
      }
    })

    it('公共 API 包含 Selection API (selectAllCurrentPage/selectAllPages/clearAllSelection)', () => {
      const src = readFile('composables/useMetaList.js')
      for (const fn of ['selectAllCurrentPage', 'selectAllPages', 'clearAllSelection']) {
        expect(src).toMatch(new RegExp(`\\b${fn}\\b`))
      }
    })

    it('公共 API 包含 FR-008 selectionLimitHit + MAX_SELECTION_LIMIT (Step 0.3)', () => {
      const src = readFile('composables/useMetaList.js')
      expect(src).toMatch(/MAX_SELECTION_LIMIT/)
      expect(src).toMatch(/selectionLimitHit/)
    })
  })
})
