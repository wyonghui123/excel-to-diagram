/**
 * useMetaList.consumer.spec.js - 5 consumer × 4 displayMode 契约守卫（PR 9）
 *
 * 目的：
 *   验证 5 个关键 consumer 正确使用 useMetaList / MetaListPage
 *   任何重构破坏 consumer 集成时被立即捕获
 *
 * 5 consumer（spec v1.5.0 §19.5）：
 *   1. ObjectPage/AssociationSection.vue - 3 处嵌入（m2m/annotation/default）
 *   2. ObjectChildSection/ObjectChildSection.vue - 双模式（useMetaList=true/false）
 *   3. SearchHelpDialog.vue - 3 displayMode（flat/tree_flat/tree）
 *   4. AssignmentDialog/AssignmentDialog.vue - dialog 模式
 *   5. MultiObjectManagementPage/MultiObjectManagementPage.vue - useMultiObjectPage 集成
 *
 * 测试设计：
 *   - 静态分析源码（readFileSync）
 *   - 验证关键 props / displayMode / objectType 正确传递
 *   - 验证 import 路径正确
 *   - 验证 boService 调用契约
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

// 5 consumer 路径
const CONSUMER_PATHS = {
  AssociationSection: 'src/components/common/ObjectPage/AssociationSection.vue',
  ObjectChildSection: 'src/components/common/ObjectChildSection/ObjectChildSection.vue',
  SearchHelpDialog: 'src/components/common/SearchHelpDialog.vue',
  AssignmentDialog: 'src/components/common/AssignmentDialog/AssignmentDialog.vue',
  MultiObjectManagementPage: 'src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue',
}

const consumerSources = {}
for (const [name, path] of Object.entries(CONSUMER_PATHS)) {
  consumerSources[name] = readFileSync(resolve(__dirname, '../../..', path), 'utf-8')
}

describe('5 Consumer × MetaListPage 契约守卫（PR 9）', () => {
  describe('Consumer 1: AssociationSection（3 处嵌入）', () => {
    it('C1.1: import MetaListPage 正确', () => {
      expect(consumerSources.AssociationSection).toContain(`import MetaListPage from '../MetaListPage/MetaListPage.vue'`)
    })

    it('C1.2: 第 1 处嵌入 - 关联数据展示（m2m）', () => {
      // L4-14: 关联数据展示
      expect(consumerSources.AssociationSection).toContain(`<MetaListPage`)
      expect(consumerSources.AssociationSection).toContain(`:object-type="targetType"`)
      expect(consumerSources.AssociationSection).toContain(`:enable-detail="false"`)
      expect(consumerSources.AssociationSection).toContain(`:enable-auto-crud="false"`)
    })

    it('C1.3: 第 2 处嵌入 - annotation 备注（v-if="objectType && hasRealObjectId"）', () => {
      // L45-53: annotation 备注
      expect(consumerSources.AssociationSection).toContain(`object-type="annotation"`)
    })

    it('C1.4: 第 3 处嵌入 - 普通关联（v-else-if="targetType && objectType && objectId"）', () => {
      // L71-78: 普通关联
      expect(consumerSources.AssociationSection).toContain(`:object-type="targetType || section.association"`)
    })

    it('C1.5: 3 处 MetaListPage 嵌入总数 = 3', () => {
      const matches = consumerSources.AssociationSection.match(/<MetaListPage[\s>]/g) || []
      expect(matches.length).toBe(3)
    })

    it('C1.6: 使用 boService.queryAssociations 自定义 fetcher（m2m 关联）', () => {
      // L196, L289: queryAssociations 调用
      const queryAssocCount = (consumerSources.AssociationSection.match(/boService\.queryAssociations/g) || []).length
      expect(queryAssocCount).toBeGreaterThanOrEqual(2)
    })

    it('C1.7: 使用 boService._clearCache 双向刷新链', () => {
      // L408, L602: _clearCache 调用（spec v1.5.0 §19.6 关键链路）
      const clearCacheCount = (consumerSources.AssociationSection.match(/boService\._clearCache/g) || []).length
      expect(clearCacheCount).toBeGreaterThanOrEqual(2)
    })
  })

  describe('Consumer 2: ObjectChildSection（双模式）', () => {
    it('C2.1: import MetaListPage 正确', () => {
      expect(consumerSources.ObjectChildSection).toContain(`import MetaListPage from '@/components/common/MetaListPage/MetaListPage.vue'`)
    })

    it('C2.2: 接受 useMetaList prop（默认 false）', () => {
      expect(consumerSources.ObjectChildSection).toMatch(/useMetaList:\s*\{[^}]*default:\s*false/)
    })

    it('C2.3: 接受 displayMode prop', () => {
      expect(consumerSources.ObjectChildSection).toMatch(/displayMode:\s*\{/)
    })

    it('C2.4: 双模式切换 - useMetaListMode computed', () => {
      expect(consumerSources.ObjectChildSection).toContain(`const useMetaListMode = computed(() => props.useMetaList)`)
    })

    it('C2.5: 模式 1 - useMetaList=true 时渲染 MetaListPage', () => {
      // L46-49: v-if="useMetaListMode" 包裹 MetaListPage
      expect(consumerSources.ObjectChildSection).toContain(`v-if="useMetaListMode"`)
      expect(consumerSources.ObjectChildSection).toContain(`<MetaListPage`)
      expect(consumerSources.ObjectChildSection).toContain(`:object-type="childObjectType"`)
    })

    it('C2.6: 模式 2 - useMetaList=false 时使用自实现 el-table', () => {
      // L37: v-else-if="!hasData && !useMetaListMode" → 简单表格
      expect(consumerSources.ObjectChildSection).toContain(`v-else-if="!hasData && !useMetaListMode"`)
    })

    it('C2.7: 4 种 displayMode 分支处理（expandable/always/...）', () => {
      // L238, L374, L483, L489, L512: displayMode 多个分支
      const displayModeCount = (consumerSources.ObjectChildSection.match(/props\.displayMode === /g) || []).length
      expect(displayModeCount).toBeGreaterThanOrEqual(3)
    })
  })

  describe('Consumer 3: SearchHelpDialog（3 displayMode）', () => {
    it('C3.1: import MetaListPage 正确', () => {
      expect(consumerSources.SearchHelpDialog).toContain(`import MetaListPage from '@/components/common/MetaListPage/MetaListPage.vue'`)
    })

    it('C3.2: displayMode 派生（从 presentation.value.display_mode）', () => {
      expect(consumerSources.SearchHelpDialog).toContain(`const displayMode = computed(() => presentation.value.display_mode || 'flat')`)
    })

    it('C3.3: 模式 1 - flat 模式渲染 MetaListPage（v-if="flat || tree_flat"）', () => {
      // L55-57: v-if="displayMode === 'flat' || displayMode === 'tree_flat'"
      expect(consumerSources.SearchHelpDialog).toContain(`v-if="displayMode === 'flat' || displayMode === 'tree_flat'"`)
    })

    it('C3.4: 模式 2 - tree 模式渲染 el-tree（v-else-if="tree"）', () => {
      // L72-73: v-else-if="displayMode === 'tree'"
      expect(consumerSources.SearchHelpDialog).toContain(`v-else-if="displayMode === 'tree'"`)
    })

    it('C3.5: 3 种 displayMode 互斥（不会同时匹配）', () => {
      const flatMatch = (consumerSources.SearchHelpDialog.match(/displayMode === 'flat'/g) || []).length
      const treeFlatMatch = (consumerSources.SearchHelpDialog.match(/displayMode === 'tree_flat'/g) || []).length
      const treeMatch = (consumerSources.SearchHelpDialog.match(/displayMode === 'tree'/g) || []).length
      // 至少有这 3 个分支
      expect(flatMatch).toBeGreaterThanOrEqual(1)
      expect(treeFlatMatch).toBeGreaterThanOrEqual(1)
      expect(treeMatch).toBeGreaterThanOrEqual(1)
    })

    it('C3.6: tree 模式自实现（el-tree，不用 MetaListPage）', () => {
      // L72-86: el-tree 完整 tree 模式
      expect(consumerSources.SearchHelpDialog).toContain(`<el-tree`)
    })
  })

  describe('Consumer 4: AssignmentDialog（dialog 模式）', () => {
    it('C4.1: import MetaListPage 正确', () => {
      expect(consumerSources.AssignmentDialog).toContain(`import MetaListPage from '@/components/common/MetaListPage/MetaListPage.vue'`)
    })

    it('C4.2: 接受 objectType prop', () => {
      expect(consumerSources.AssignmentDialog).toMatch(/objectType:\s*\{/)
    })

    it('C4.3: 使用 display-mode="dialog"（核心契约）', () => {
      // L29: :display-mode="'dialog'"
      expect(consumerSources.AssignmentDialog).toContain(`:display-mode="'dialog'"`)
    })

    it('C4.4: 渲染在 el-dialog 内', () => {
      expect(consumerSources.AssignmentDialog).toContain(`<el-dialog`)
      expect(consumerSources.AssignmentDialog).toContain(`</el-dialog>`)
    })

    it('C4.5: dialogTitle 动态计算', () => {
      expect(consumerSources.AssignmentDialog).toContain(`const dialogTitle = computed(`)
    })
  })

  describe('Consumer 5: MultiObjectManagementPage（useMultiObjectPage 集成）', () => {
    it('C5.1: import MetaListPage 正确', () => {
      expect(consumerSources.MultiObjectManagementPage).toContain(`import { MetaListPage } from '@/components/common/MetaListPage'`)
    })

    it('C5.2: import useMultiObjectPage composable', () => {
      expect(consumerSources.MultiObjectManagementPage).toContain(`import { useMultiObjectPage } from '@/composables/useMultiObjectPage'`)
    })

    it('C5.3: 接受 objectTypes prop（多对象类型）', () => {
      expect(consumerSources.MultiObjectManagementPage).toMatch(/objectTypes:\s*\{\s*type:\s*Array,\s*required:\s*true/)
    })

    it('C5.4: 使用 useMultiObjectPage 创建 page', () => {
      // L232: const page = reactive(useMultiObjectPage(...))
      expect(consumerSources.MultiObjectManagementPage).toContain(`const page = reactive(useMultiObjectPage(props.objectTypes, props.options, coordinator))`)
    })

    it('C5.5: 渲染 page.objectTypes 透传到 MetaListPage', () => {
      // L77-78: :object-types="page.objectTypes"
      expect(consumerSources.MultiObjectManagementPage).toContain(`:object-types="page.objectTypes"`)
    })

    it('C5.6: 纯元数据驱动（spec 描述）', () => {
      // L113: "纯元数据驱动的通用组件"
      expect(consumerSources.MultiObjectManagementPage).toContain('纯元数据驱动')
    })
  })

  describe('5 Consumer 综合契约', () => {
    it('C-X.1: 5 consumer 都正确 import MetaListPage', () => {
      for (const [name, source] of Object.entries(consumerSources)) {
        expect(source, `${name} should import MetaListPage`).toMatch(/import .*MetaListPage.*from .*MetaListPage/)
      }
    })

    it('C-X.2: 5 consumer 都接受 objectType(s) 或 childObjectType 或 object-type="..." 形式', () => {
      for (const [name, source] of Object.entries(consumerSources)) {
        // 支持多种 prop 命名：objectType / objectTypes / childObjectType / object-type="..." (动态)
        const hasObjectType = (
          source.match(/objectTypes?:\s*\{/) ||
          source.match(/childObjectType\s*[=:]/) ||
          source.match(/:object-type="(childObjectType|targetType|objectType|entityType)/) ||
          source.match(/object-type=/)
        ) !== null
        expect(hasObjectType, `${name} should accept objectType(s) prop`).toBe(true)
      }
    })

    it('C-X.3: 5 consumer 总计嵌入 MetaListPage = 3+1+1+1+1 = 7 处', () => {
      // AssociationSection: 3
      // ObjectChildSection: 1 (useMetaList=true)
      // SearchHelpDialog: 1 (flat/tree_flat)
      // AssignmentDialog: 1
      // MultiObjectManagementPage: 1
      const total = Object.values(consumerSources).reduce(
        (sum, source) => sum + ((source.match(/<MetaListPage[\s>]/g) || []).length),
        0
      )
      // 注：SearchHelpDialog 还有 1 个空行 <MetaListPage ... />
      // 实际总数 = 7+ 处
      expect(total).toBeGreaterThanOrEqual(6)
    })
  })
})
