<template>
  <div class="multi-object-management">
    <GlobalToolbar
      ref="globalToolbarRef"
      :compact="true"
      :action-disabled="actionDisabledMap"
      @change="handleToolbarChange"
      @action="onGlobalAction"
    />

    <MasterDetailLayout
      sidebar-width="320px"
      :sidebar-collapsible="true"
      :sidebar-collapsed="sidebarCollapsed"
      :min-width="240"
      :max-width="800"
      @collapse-change="handleSidebarCollapse"
    >
      <template #master>
        <div v-if="page.versionContext.selectedVersionId" class="momp-sidebar">
          <RelationScopeTree
            ref="scopeTreeRef"
            :key="scopeTreeKey"
            :version-id="page.versionContext.selectedVersionId"
            :initial-bo-ids="initialBoIds"
            :initial-relation-codes="initialRelationCodes"
            :filter-disabled="page.activeTab !== 'relationship'"
            :scope-ids="page.scopeIds"
            @scope-change="page.handleScopeChange"
          />
        </div>
        <div v-else class="momp-empty-sidebar">
          <el-icon :size="32"><FolderOpened /></el-icon>
          <span>请先选择版本</span>
        </div>
      </template>

      <template #detail>
        <div class="momp-detail-content">
          <template v-if="page.versionContext.selectedVersionId">
            <div class="momp-tabs-row">
              <el-tabs v-if="page.tabs && page.tabs.length" v-model="page.activeTab" class="momp-tabs" @tab-change="$emit('tabChange', $event)">
                <el-tab-pane
                  v-for="tab in page.tabs"
                  :key="tab?.name"
                  :label="tab?.label"
                  :name="tab?.name"
                />
              </el-tabs>
              <slot name="tabsExtra" :context="tabsExtraContext" />
            </div>

            <MetaListPage
              ref="metaListPageRef"
              :key="page.activeTab"
              :object-type="page.activeTab"
              :initial-filters="page.combinedFilters"
              :options="listOptions"
              :enable-detail="true"
              :enable-auto-crud="true"
            >
              <template v-for="(_, slotName) in $slots" :key="slotName" #[slotName]="slotProps">
                <slot :name="slotName" v-bind="slotProps" />
              </template>
            </MetaListPage>
          </template>
          <div v-else class="momp-empty-detail">
            <el-icon :size="48"><Connection /></el-icon>
            <span>请选择产品和版本以查看数据</span>
          </div>
        </div>
      </template>
    </MasterDetailLayout>

    <ImportDialog
      v-model:visible="page.importDialogVisible"
      :object-type="page.activeTab"
      :object-types="page.objectTypes"
      :object-type-labels="page.objectTypeLabels"
      :multi-type-mode="true"
      :context="page.importContext"
      @success="page.handleImportSuccess"
    />

    <ExportDialog
      v-model:visible="page.exportDialogVisible"
      :object-type="page.activeTab"
      :filters="page.exportFilters"
      :object-types="page.objectTypes"
      :object-type-labels="page.objectTypeLabels"
      :sort-info="currentSortInfo"
      :default-sort="currentDefaultSort"
      :current-count="currentListCount"
      :total-count="currentTotalCount"
      :multi-type-mode="true"
      :show-export-mode="true"
      :show-export-options="true"
      @success="page.handleExportSuccess"
    />
  </div>
</template>

<script setup>
/**
 * ============================================================
 *  MultiObjectManagementPage — 元数据驱动的通用多对象管理页面
 * ============================================================
 *
 * 【设计原则】
 *   这是一个**纯元数据驱动的通用组件**，只依赖输入 `objectTypes: string[]`。
 *   所有对象树、Tab、过滤逻辑、层级关系均从元数据（hierarchies.yaml + 各对象 YAML）
 *   自动推导，**严禁在组件内硬编码任何对象类型、层级关系、FK 映射**。
 *
 * 【输入】
 *   - objectTypes: string[]  例: ['domain', 'sub_domain', 'service_module', 'business_object', 'relationship']
 *   - options:                例: { defaultTab, tabs, listOptions, ... }
 *
 * ============================================================
 *  过滤区（左侧）与 Tab 列表（右侧）的关联模型
 * ============================================================
 *
 *  【对象树结构】（RelationScopeTree → ObjectScopeSection）
 *    仅加载 3 层节点:
 *      domain → sub_domain → service_module
 *
 *    business_object **不**作为树节点加载（它是 service_module 的 composition 子对象）。
 *
 *  【Tab → 树 映射关系】（完全由元数据驱动，无硬编码）
 *
 *    对象树勾选          │  右侧 Tab 列表过滤
 *    ────────────────────┼──────────────────────────
 *    domain (勾选)       │  domain Tab:      id__in = [选中的 domain IDs]
 *                        │  sub_domain Tab:  domain_id__in = [选中的 domain IDs]
 *                        │                  ↑ FK: getParentType('sub_domain') → 'domain' → FK='domain_id'
 *                        │
 *    sub_domain (勾选)   │  sub_domain Tab:  id__in = [选中的 sub_domain IDs]
 *                        │  service_module Tab: sub_domain_id__in = [选中的 sub_domain IDs]
 *                        │                  ↑ FK: getParentType('service_module') → FK='sub_domain_id'
 *                        │
 *    service_module(勾选)│  service_module Tab: id__in = [选中的 SM IDs]
 *                        │  business_object Tab: service_module_id__in = [选中的 SM IDs]
 *                        │                  ↑ composition/getChildren: BO 是 SM 的子对象
 *                        │
 *    business_object(勾选)│ business_object Tab: id__in = [选中的 BO IDs]
 *                        │                  ↑ BO 直接精确匹配（无子对象，无 FK 传递）
 *
 *  【composition 关系深释】
 *    - business_object 是 service_module 的 composition 子对象
 *    - 在 hierarchies.yaml: level 5 (BO) 的 parent_object = level 4 (SM)
 *    - 在 business_object.yaml: parent_object: service_module, parent_field: service_module_id
 *    - 因此: 对象树勾选 SM 节点 → BO Tab 通过 `service_module_id__in` 自动获取所有子 BO
 *    - 本质: SM. getChildren() = query(BO, {service_module_id__in: [SM_IDs]})
 *    - FK 字段通过 `getFKField(type)` = `getParentType(type) + '_id'` 动态推导
 *
 *  【关联关系机制】（关系 Tab）
 *    - relationship 独立于层级树，通过 relation_code（关联类型）区分
 *    - relationship.yaml 定义: source_bo_id / target_bo_id 连接双方业务对象
 *    - 支持过滤: relation_code__in / category_types__in / filterRelationCodes 取交集
 *    - relationship Tab 不受对象树 scope 选区影响（仅受全局过滤 + 关系过滤）
 *
 * ============================================================
 *  核心约定（元数据驱动的基石—必须遵守）
 * ============================================================
 *
 *  1. FK 命名约定: {parentObjectType}_id
 *     domain_id, sub_domain_id, service_module_id
 *     → 由 `getFKField(type)` = `getParentType(type) + '_id'` 自动推导
 *
 *  2. API 过滤参数约定: {fk_field}__in
 *     domain_id__in, sub_domain_id__in, service_module_id__in
 *     → 由 `_buildHierarchyFilters()` 自动构建
 *
 *  3. 树 scope 事件约定:
 *     RelationScopeTree emit 键名格式: selected{Type}Ids / effective{Type}Ids
 *     → useMultiObjectPage.handleScopeChange 通过 `_pascalCase(type)` 自动匹配
 *     (如: selectedDomainIds, effectiveServiceModuleIds)
 *
 *  4. 业务对象兼容约定:
 *     RelationScopeTree 同时 emit `boIds` 和 `selectedBusinessObjectIds`
 *     → handleScopeChange 优先读取 `selectedBusinessObjectIds`，fallback `boIds`
 *
 *  5. 版本上下文约定:
 *     product/version 通过 GlobalToolbar → useVersionContext 管理，不在对象树中
 *     → 所有 Tab 的 API 请求自动注入 version_id 过滤
 *
 * === 反模式（严禁出现）===
 * [X] 硬编码对象类型名: if (type === 'domain') ...
 * [X] 硬编码 FK 字段名:  `service_module_id__in` 直接写死
 * [X] 硬编码 scope 键名: scope.boIds 仅当无 selectedBusinessObjectIds 时 fallback
 * [X] 假设对象树一定包含某类型: isHierarchyType() 必须从元数据推导
 *
 * === 正确模式 ===
 * [OK] 使用 hierarchyTypes.getParentType(type) 推导 FK
 * [OK] 使用 getFKField(hierarchyTypes, type) 获取 FK 字段名
 * [OK] 使用 _pascalCase(type) 动态生成 scope key
 * [OK] 使用 isHierarchyType(hierarchyTypes, type) 判断层级对象
 */

import { ref, watch, computed, reactive, onMounted, provide } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { useTabStore } from '@/stores/tabStore'
import { useChartArchDataStore } from '@/stores/chartArchDataStore'
import { FolderOpened, Connection } from '@element-plus/icons-vue'
import { MasterDetailLayout } from '@/components/common/MasterDetailLayout'
import { MetaListPage } from '@/components/common/MetaListPage'
import { RelationScopeTree } from '@/components/common/RelationScopeTree'
import GlobalToolbar from '@/components/common/GlobalToolbar/GlobalToolbar.vue'
import ImportDialog from '@/components/common/ImportDialog/ImportDialog.vue'
import ExportDialog from '@/components/common/ExportDialog/ExportDialog.vue'
import { useMultiObjectPage } from '@/composables/useMultiObjectPage'
import { useRefreshCoordinator } from '@/composables/useRefreshCoordinator'
import { setRefreshCoordinator } from '@/services/boService'

const props = defineProps({
  objectTypes: { type: Array, required: true },
  options: { type: Object, default: () => ({}) }
})

const emit = defineEmits(['toolbarAction', 'tabChange'])

const route = useRoute()
const router = useRouter()

// [v32] 引入 chart tab 的 Pinia stores (单一数据源)
const tabStore = useTabStore()
const chartStore = useChartArchDataStore()

const scopeTreeRef = ref(null)
const globalToolbarRef = ref(null)
const initialBoIds = ref([])
const initialRelationCodes = ref([])
const scopeTreeKey = ref(0)  // 用于返回图表后强制 RelationScopeTree 重新挂载, 恢复勾选
const sidebarCollapsed = ref(false)

const coordinator = useRefreshCoordinator()
provide('refreshCoordinator', coordinator)
setRefreshCoordinator(coordinator)

const page = reactive(useMultiObjectPage(props.objectTypes, props.options, coordinator))

function handleSidebarCollapse(collapsed) {
  sidebarCollapsed.value = collapsed
}

onMounted(() => {
  const queryTab = route?.query?.tab
  if (queryTab && page.tabs.find(t => t.name === queryTab)) {
    page.activeTab = queryTab
  }

  // 从图表展示返回时恢复状态
  // chart app 跳转前会写入 returningFromDiagram + archManagerStateBeforeDiagram
  const restored = page.restoreStateFromDiagram()
  if (restored) {
    initialBoIds.value = restored.initialBoIds
    initialRelationCodes.value = restored.initialRelationCodes
    // 强制 RelationScopeTree 重新挂载, 让 initialBoIds / initialRelationCodes 生效
    scopeTreeKey.value++
  }
})

if (router) {
  watch(() => page.activeTab, (newTab) => {
    if (route?.query?.tab !== newTab) {
      router.replace({ query: { ...route.query, tab: newTab } })
    }
  })
}

onBeforeRouteLeave((_to, _from) => {
  // [v39.7-FIX] 每次离开管理页都重新保存状态快照，确保第二次/多次切回时也能恢复
  // 之前: saveStateForDiagram 只在点击"展示图表"按钮时调用一次
  //   → 第一次切回管理页时 restore 消费了数据, 第二次切回时数据已丢
  // 之后: 配合 restoreStateFromDiagram 不再清掉 STATE_RESTORE_KEY
  //   → 每次离开都刷新快照, 多次 restore 都能拿到最新状态
  //   → sessionStorage 容量有限 (5-10MB), 但状态快照 < 50KB, 无压力
  try {
    page.saveStateForDiagram()
  } catch (e) {
    console.warn('[v39.7] Failed to save state on route leave:', e)
  }

  // tabStore / chartStore 已在 setup() 顶部声明, 此处直接使用闭包引用
  const tabEntry = tabStore.tabs.find(t => t.id === route?.path)
  if (tabEntry && tabEntry.path !== route.fullPath) {
    tabStore.closeTab(route.path)
    tabStore.openTab({
      id: route.path,
      label: tabEntry.label,
      path: route.fullPath,
      icon: tabEntry.icon,
      badge: tabEntry.badge,
      closable: tabEntry.closable,
      pinned: tabEntry.pinned,
      meta: tabEntry.meta
    })
    tabStore.switchTab(route.path)
  }
})

const listOptions = computed(() => ({
  autoLoad: true,
  pageSize: 20,
  ...(props.options.listOptions || {})
}))

const currentSortInfo = computed(() => metaListPageRef.value?.sortInfo || null)
const currentDefaultSort = computed(() => metaListPageRef.value?.defaultSort || null)
const currentListCount = computed(() => metaListPageRef.value?.data?.length || 0)
const currentTotalCount = computed(() => {
  const t = metaListPageRef.value?.filteredTotalCount
  return t?.value ?? t ?? 0
})

const actionDisabledMap = computed(() => ({
  import: !page.canImport,
  export: !page.canExport,
  chart: !page.canShowChart,
  refresh: !page.canRefresh
}))

function onGlobalAction(action) {
  if (action === 'chart') {
    const chartData = page.handleGlobalAction('chart')
    if (chartData) {
      // [v32] 双层数据源: chartStore (主) + sessionStorage (备份)
      //   1) chartStore (Pinia in-memory): 跨组件共享, 用于 tab re-click
      //   2) sessionStorage 备份: 用于 F5 刷新场景 (Pinia 状态丢失但 sessionStorage 持久)
      chartStore.setArchData(chartData)

      // [v32-FIX] sessionStorage 备份, 应对 F5 刷新
      //   Pinia 状态在 F5 后丢失, 但 sessionStorage 保留
      //   chart tab onMounted 会先查 Pinia, 找不到再读 sessionStorage
      try {
        sessionStorage.setItem('lastArchDataForDiagram', JSON.stringify(chartData))
        sessionStorage.setItem('archDataForDiagram', JSON.stringify(chartData))
        sessionStorage.setItem('archDataCurrentStep', '3')
      } catch (e) {
        console.warn('[v32] failed to backup archData to sessionStorage:', e)
      }

      const chartTabId = '/archdata-chart'
      const existingTab = tabStore.tabs.find(t => t.id === chartTabId)
      if (existingTab) {
        // [v32] 确保 tab 可关闭 (防止 localStorage 恢复的 stale pinned/closable)
        existingTab.closable = true
        existingTab.pinned = false
        tabStore.switchTab(chartTabId)
      } else {
        tabStore.openTab({
          id: chartTabId,
          label: '架构数据图表',
          path: chartTabId,
          pinned: false
        })
      }
      router.push(chartTabId)
    }
    return
  }
  page.handleGlobalAction(action)
}

const tabsExtraContext = computed(() => {
  const tree = scopeTreeRef.value
  const objectCount = tree?.selectedBoCount ?? 0
  const relationCount = tree?.relationCodesCount ?? 0
  const annotationCountVal = tree?.annotationCount ?? 0
  const relationFilterCountVal = tree?.relationCount ?? 0

  const filters = [
    { key: 'objectScope', label: '对象范围', count: objectCount, active: objectCount > 0 },
    { key: 'relationScope', label: '关系范围', count: relationCount, active: relationCount > 0 },
    { key: 'annotationFilter', label: '备注类型', count: annotationCountVal, active: annotationCountVal > 0 },
    { key: 'relationFilter', label: '关系类型', count: relationFilterCountVal, active: relationFilterCountVal > 0 }
  ].filter(f => f.active)

  return {
    activeTab: page.activeTab,
    hasSelection: page.hasScopeSelection,
    filters,
    clear: () => {
      page.clearScope()
      scopeTreeRef.value?.clearObjectScope()
      scopeTreeRef.value?.clearRelationScope()
      scopeTreeRef.value?.clearFilterCondition()
    },
    clearFilter: (key) => {
      if (key === 'objectScope') {
        scopeTreeRef.value?.clearObjectScope()
      } else if (key === 'relationScope') {
        scopeTreeRef.value?.clearRelationScope()
      } else if (key === 'annotationFilter') {
        scopeTreeRef.value?.clearAnnotationFilter()
      } else if (key === 'relationFilter') {
        scopeTreeRef.value?.clearRelationFilter()
      }
    }
  }
})

function handleToolbarChange(payload) {
  page.handleToolbarChange(payload)
}

defineExpose({
  refresh: () => metaListPageRef.value?.refresh(),
  clearScope: () => {
    page.clearScope()
    scopeTreeRef.value?.clear()
  },
  page
})

const metaListPageRef = ref(null)

watch(() => page.combinedFilters, (newFilters) => {
  if (metaListPageRef.value?.setContextFilters) {
    metaListPageRef.value.setContextFilters(newFilters)
  }
  if (!import.meta.env.VITE_FEATURE_SCOPETREE_FILTERSOURCE) {
    coordinator.refreshAll()
  }
})

</script>

<style lang="scss" scoped>
.multi-object-management {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--color-bg-primary);
}

.momp-detail-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.momp-tabs-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--color-bg-container);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.momp-sidebar {
  height: 100%;
}

.momp-empty-sidebar,
.momp-empty-detail {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-text-tertiary);
  gap: var(--spacing-sm);
  font-size: var(--font-size-sm);
}

.momp-tabs {
  flex: 1;
  flex-shrink: 0;
}

.momp-tabs :deep(.el-tabs__header) {
  margin-bottom: 0;
  padding: 0 var(--spacing-sm);
  background: transparent;
}

.momp-tabs :deep(.el-tabs__nav-wrap::after) {
  display: none;
}
</style>
