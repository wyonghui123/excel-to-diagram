<template>
  <div class="multi-object-management">
    <GlobalToolbar
      ref="globalToolbarRef"
      :compact="true"
      :action-disabled="actionDisabledMap"
      :hide-chart-button="true"
      :active-view="viewMode"
      @change="handleToolbarChange"
      @action="onGlobalAction"
    >
      <!-- [A7 2026-07-30] 嵌入式图表 toggle 按钮（默认启用，无需 flag）
           替代老的"图表视图"按钮：list ↔ chart 就地切换，不跳路由 -->
      <template #actions>
        <el-tooltip :content="viewMode === 'chart' ? '切回列表视图' : '就地切换为图表视图'" placement="bottom" :teleported="false" popper-class="app-tooltip-popper">
          <el-button
            size="small"
            :icon="TrendCharts"
            :disabled="!page.canShowChart"
            class="gt-btn-chart-toggle"
            :class="{ 'is-active': viewMode === 'chart' }"
            @click="toggleEmbeddedView"
          >
            {{ viewMode === 'chart' ? '列表展示' : '图表展示' }}
          </el-button>
        </el-tooltip>
      </template>
      <!-- [FIX 2026-07-31] chart-config slot 透传: 必须用 <template #chart-config> 包裹
           才能正确传给 GlobalToolbar 的 chart-config slot（而非 default slot）
           之前 <slot name="chart-config" /> 裸写，导致内容落入 GlobalToolbar default slot，
           GlobalToolbar 的 <slot name="chart-config" /> 渲染为空 → ChartMiniToolbar 不显示 -->
      <template #chart-config><slot name="chart-config" /></template>
    </GlobalToolbar>

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
            <!-- [FIX 2026-07-30] chart 视图下隐藏 tabs/list，只显示 detailContent slot -->
            <template v-if="viewMode === 'list'">
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

              <template v-for="tab in page.tabs" :key="tab.name">
                <MetaListPage
                  v-if="visitedTabs.has(tab.name)"
                  v-show="page.activeTab === tab.name"
                  :ref="el => { if (el) metaListPageRefs[tab.name] = el }"
                  :object-type="tab.name"
                  :initial-filters="page.combinedFilters"
                  :options="listOptions"
                  :enable-detail="true"
                  :enable-auto-crud="true"
                  @row-dblclick="(payload) => handleRowDblClick(tab.name, payload)"
                >
                  <template v-for="(_, slotName) in $slots" :key="slotName" #[slotName]="slotProps">
                    <slot :name="slotName" v-bind="slotProps" />
                  </template>
                </MetaListPage>
              </template>
            </template>

            <!-- [A7 2026-07-30] 嵌入式图表视图: viewMode='chart' 时渲染业务方注入的 detailContent slot
                 context 提供 chart 需要的 scopeIds/versionId/chartData (hierarchyFilter 等)
                 [FIX 2026-07-30] chart 视图独占整个 detail 区域，不显示 list tabs -->
            <div v-if="viewMode === 'chart'" class="momp-chart-mode">
              <slot name="detailContent" :context="embeddedChartContext" />
            </div>
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
      :menu-code="menuCode"
      @success="page.handleImportSuccess"
    />

    <ExportDialog
      v-model:visible="page.exportDialogVisible"
      :object-type="page.activeTab"
      :filters="page.exportFilters"
      :object-types="page.exportObjectTypes"
      :object-type-labels="page.objectTypeLabels"
      :sort-info="currentSortInfo"
      :default-sort="currentDefaultSort"
      :current-count="currentListCount"
      :total-count="currentTotalCount"
      :multi-type-mode="true"
      :show-export-options="true"
      :default-unselected-types="['annotation', 'relationship']"
      :menu-code="menuCode"
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

import { ref, watch, computed, reactive, onMounted, onActivated, provide } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { useTabStore } from '@/stores/tabStore'
import { useChartArchDataStore } from '@/stores/chartArchDataStore'
import { FolderOpened, Connection, TrendCharts } from '@element-plus/icons-vue'
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

// [NEW v3.20 2026-06-19] 从 route name 推导 menu_code
// 路由 /system/archdata → name = "ArchDataManagement" → 映射 menu_code = "arch-data"
// 路由 /archdata-chart → name = "archdata-chart" → 也走"架构数据"前缀（图表导出）
const menuCode = computed(() => {
  const name = route?.name
  if (name === 'ArchDataManagement' || name === 'archdata-chart' || name === 'archdata') {
    return 'arch-data'
  }
  return ''
})

// [v32] 引入 chart tab 的 Pinia stores (单一数据源)
const tabStore = useTabStore()
const chartStore = useChartArchDataStore()

const scopeTreeRef = ref(null)
const globalToolbarRef = ref(null)
const initialBoIds = ref([])
const initialRelationCodes = ref([])
const scopeTreeKey = ref(0)  // 用于返回图表后强制 RelationScopeTree 重新挂载, 恢复勾选
const sidebarCollapsed = ref(false)

// [A7 2026-07-30] 嵌入式图表视图 toggle 状态
//   - viewMode: 'list' | 'chart'，切换 detail 区显示 MetaListPage 还是 detailContent slot
//   - 默认 'list'，嵌入式入口是默认行为，无 flag
const viewMode = ref('list')

// [布局设置 sidebar 整合] 提供 viewMode 给 RelationScopeTree
//   RelationScopeTree 用它判断 hasChartData (viewMode==='chart' 时布局 panel 才显示)
provide('mompViewMode', viewMode)

function toggleEmbeddedView() {
  if (!page.canShowChart) return
  if (viewMode.value === 'chart') {
    viewMode.value = 'list'
    return
  }
  // 进入 chart 模式前保存 list 状态 (复用 saveStateForDiagram 兼容老路径)
  try { page.saveStateForDiagram() } catch (e) { console.warn('[toggleEmbeddedView] saveStateForDiagram failed:', e) }
  viewMode.value = 'chart'
}

// [E2E 2026-08-08] 暴露 forceChartMode 到 window.__archPage (替代 ensureChartMode 的 12 次轮询)
//   只能在 ?mode=debug 时使用, 跳过 canShowChart 检查直接进入图表模式
if (typeof window !== 'undefined') {
  const urlParams = new URLSearchParams(window.location.search)
  if (urlParams.get('mode') === 'debug') {
    window.__archPage = window.__archPage || {}
    window.__archPage.forceChartMode = () => {
      if (viewMode.value === 'chart') return
      try { page.saveStateForDiagram() } catch (e) { console.warn('[forceChartMode] saveStateForDiagram failed:', e) }
      viewMode.value = 'chart'
    }
  }
}

// [A7 2026-07-30] 嵌入式图表 context: 传给业务方 detailContent slot
//   - versionId: 当前选中的版本
//   - scopeIds: useMultiObjectPage.scopeIds（树勾选状态）
//   - chartData: { hierarchyFilter, relationTypeFilter, relationIds, ... }
//                 (复用 handleShowChart() 返回的同结构，老路径 / 新路径都用)
//   - viewMode: 当前模式（业务方用于显示返回按钮）
const embeddedChartContext = computed(() => ({
  // [FIX 2026-07-30] useMultiObjectPage 返回的是原始对象（非 ref），
  //   reactive(page) 会自动 depth reactive 包裹；访问 selectedVersionId 时已经 unwrap，
  //   再加 .value 会变 undefined。直接读即可。
  versionId: page.versionContext?.selectedVersionId,
  productId: page.versionContext?.selectedProductId,
  scopeIds: page.scopeIds,
  chartData: page.handleShowChart ? (page.handleShowChart() || {}) : {},
  viewMode: viewMode.value
}))

const coordinator = useRefreshCoordinator()
provide('refreshCoordinator', coordinator)
setRefreshCoordinator(coordinator)

const page = reactive(useMultiObjectPage(props.objectTypes, props.options, coordinator))

function handleSidebarCollapse(collapsed) {
  sidebarCollapsed.value = collapsed
}

// [FIX 2026-07-31] dev shortcut: 支持 URL shortcut=1 参数 + scope JSON 跳过 UI 选择直接进入 EmbeddedChartView
//   设计目标: 让 AI/开发排查图表 bug 时 5 秒直达 EmbeddedChartView, 不必手动选产品/版本/勾选 scope 树/点图表按钮。
//   用法: /system/archdata?shortcut=1&productCode=TTTTT000&versionCode=V11&scope=<base64JSON>
//   scope JSON 格式 (可选): {"business_object":[boIds], "service_module":[smIds], "sub_domain":[sdIds], "domain":[dIds], "relation_codes":[...]}
//   [NEW 2026-08-07] scopeCode 参数: 更简洁的编码选择, 如 &scopeCode=SCP 选择"供应链计划"子领域
//   仅在 dev 环境启用 (import.meta.env.DEV); 生产构建短路掉, 不影响正式流程。
//   注意: productCode/versionCode 由 useVersionContext.restoreContext 处理 (在 page 创建之前);
//         这里只负责 scope 自动勾选 + toggle chart view。

// [FIX 2026-08-07] 剥离树节点 ID 前缀 (d_, s_, sm_, bo_), 返回纯数字 ID
//   树节点 ID 格式: d_2200, s_68, sm_135, bo_42
//   注意: sub_domain 节点 ID 前缀是 s_ (不是 sd_), 见 ObjectScopeSection.vue:736
//   后端 API 需要纯数字 ID
function stripPrefix(id) {
  if (typeof id === 'string') {
    const match = id.match(/^(?:d_|s_|sm_|bo_)(\d+)$/)
    if (match) return parseInt(match[1], 10)
  }
  return id
}

// [NEW 2026-08-07] 根据节点编码选择范围, 返回 scopePayload 供 page.handleScopeChange 使用
//   等待 scopeTreeRef 就绪后调用 selectByCode, 再等待 hasScopeSelection 同步
//   [FIX 2026-08-07] 改用 page.scopeIds 构建 payload, 替代 getCheckedBoIds
//   因为 selectByCode 选中的是 service_module 叶子节点, getCheckedBoIds 返回空
async function applyScopeCode(code) {
  if (!code) return null
  // [FIX 2026-08-07] 增加等待: 先等 scopeTreeRef 挂载, 再等 treeData 加载
  //   避免跨组件异步等待链过长导致 HMR 未完全生效
  //   [FIX 2026-08-07] 后端 API 响应慢 (16s+), 增加等待到 100 次 × 200ms = 20s
  for (let attempt = 0; attempt < 100; attempt++) {
    if (scopeTreeRef.value?._test?.treeData?.length) break
    await new Promise(resolve => setTimeout(resolve, 200))
  }
  if (!scopeTreeRef.value?._test?.treeData?.length) {
    console.warn('[shortcut] 20s 内 scopeTreeRef treeData 未就绪')
    return null
  }
  console.log('[shortcut] treeData 已就绪, 共', scopeTreeRef.value._test.treeData.length, '个根节点')
  const ok = await scopeTreeRef.value.selectByCode(code)
  if (!ok) return null
  // 等待 scope 同步 (handleScopeChange 通过事件链更新 page.scopeIds)
  await new Promise(resolve => setTimeout(resolve, 800))
  // 从 page.scopeIds 构建 payload, 兼容 service_module 选中的场景
  // [FIX 2026-08-07] objType 首字母大写, 生成 selectedDomainIds 而非 selecteddomainIds
  const payload = {}
  for (const objType of ['domain', 'sub_domain', 'service_module', 'business_object']) {
    const scope = page.scopeIds?.[objType]
    if (scope?.selected?.length) {
      const pascalType = objType.charAt(0).toUpperCase() + objType.slice(1).replace(/_(\w)/g, (_, c) => c.toUpperCase())
      const key = 'selected' + pascalType + 'Ids'
      // [FIX 2026-08-07] 剥离树节点 ID 前缀 (d_/sd_/sm_/bo_), 转为纯数字 ID
      payload[key] = scope.selected.map(stripPrefix)
    }
  }
  if (Object.keys(payload).length === 0) {
    console.warn('[shortcut] scopeCode 应用后 scopeIds 为空, 尝试全选兜底')
    return null
  }
  console.log('[shortcut] applyScopeCode 返回 payload:', payload)
  return payload
}

// [NEW 2026-08-07] 根据多个编码选择多个节点范围, 返回 scopePayload
//   用于 scopeCode 参数逗号分隔, 例如 scopeCode=SCP,SCM 选择多个子领域
//   合并所有编码的选中范围后统一 handleScopeChange
async function applyScopeCodes(codes) {
  if (!codes?.length) return null
  // [FIX 2026-08-07] 增加等待: 先等 scopeTreeRef 挂载, 再等 treeData 加载
  //   [FIX 2026-08-07] 后端 API 响应慢 (16s+), 增加等待到 100 次 × 200ms = 20s
  for (let attempt = 0; attempt < 100; attempt++) {
    if (scopeTreeRef.value?._test?.treeData?.length) break
    await new Promise(resolve => setTimeout(resolve, 200))
  }
  if (!scopeTreeRef.value?._test?.treeData?.length) {
    console.warn('[shortcut] 20s 内 scopeTreeRef treeData 未就绪')
    return null
  }
  console.log('[shortcut] treeData 已就绪, 共', scopeTreeRef.value._test.treeData.length, '个根节点')
  const ok = await scopeTreeRef.value.selectByCodes(codes)
  if (!ok) return null
  // 等待 scope 同步
  await new Promise(resolve => setTimeout(resolve, 800))
  // 从 page.scopeIds 构建 payload
  // [FIX 2026-08-07] objType 首字母大写, 生成 selectedDomainIds 而非 selecteddomainIds
  const payload = {}
  for (const objType of ['domain', 'sub_domain', 'service_module', 'business_object']) {
    const scope = page.scopeIds?.[objType]
    if (scope?.selected?.length) {
      const pascalType = objType.charAt(0).toUpperCase() + objType.slice(1).replace(/_(\w)/g, (_, c) => c.toUpperCase())
      const key = 'selected' + pascalType + 'Ids'
      // [FIX 2026-08-07] 剥离树节点 ID 前缀 (d_/sd_/sm_/bo_), 转为纯数字 ID
      payload[key] = scope.selected.map(stripPrefix)
    }
  }
  if (Object.keys(payload).length === 0) {
    console.warn('[shortcut] applyScopeCodes 后 scopeIds 为空')
    return null
  }
  console.log('[shortcut] applyScopeCodes 返回 payload:', payload)
  return payload
}

// [NEW 2026-08-07] debug 模式: 在控制台打印可用编码列表
//   用法: &debug=scopeCodes 在页面加载后打印所有树节点的编码
//   与 shortcut 参数独立, 可在任意视图下使用
async function debugScopeCodes() {
  // 等待 treeData 加载
  for (let attempt = 0; attempt < 30; attempt++) {
    if (scopeTreeRef.value?._test?.treeData?.length) break
    await new Promise(resolve => setTimeout(resolve, 200))
  }
  const treeData = scopeTreeRef.value?._test?.treeData || []
  if (!treeData.length) {
    console.warn('[debug] 树数据未加载')
    return
  }
  // 递归遍历树, 收集所有节点的 code/name/type
  const codes = []
  function walk(nodes, depth) {
    for (const n of nodes) {
      if (!n) continue
      codes.push({
        code: n.code || '-',
        name: n.name || '-',
        type: n.type || '-',
        depth,
        childCount: n.children?.length || 0
      })
      if (n.children?.length) walk(n.children, depth + 1)
    }
  }
  walk(treeData, 0)
  console.log('===== 可用 scopeCode 列表 =====')
  console.table(codes.map(c => ({
    code: c.code,
    name: c.name,
    type: c.type,
    depth: c.depth,
    '子节点数': c.childCount
  })))
  console.log('===============================')
  console.log('使用示例:')
  const subDomainCodes = codes.filter(c => c.type === 'sub_domain' || c.depth === 1)
  subDomainCodes.forEach(c => {
    if (c.code !== '-') {
      console.log(`  &scopeCode=${c.code}  →  ${c.name} (${c.type})`)
    }
  })
  console.log('多编码示例:')
  const multiExample = subDomainCodes.slice(0, 2).map(c => c.code).filter(Boolean).join(',')
  if (multiExample) {
    console.log(`  &scopeCode=${multiExample}  →  同时选择多个子领域`)
  }
}

async function tryApplyShortcut() {
  const params = new URLSearchParams(window.location.search)
  // [NEW 2026-08-08] preset 参数: 一键启动预设, 扩展为完整 URL 参数
  //   用法: &preset=scp 等价于 &productCode=TTTTT000&versionCode=V11&view=chart&scopeCode=SCP
  //   目标: 只需记住一个参数, 无需拼凑 4 个参数
  const preset = params.get('preset')
  if (preset === 'scp') {
    const url = new URL(window.location.href)
    url.searchParams.set('productCode', 'TTTTT000')
    url.searchParams.set('versionCode', 'V11')
    url.searchParams.set('view', 'chart')
    url.searchParams.set('scopeCode', 'SCP')
    url.searchParams.delete('preset')
    console.log('[shortcut] preset=scp 一键启动, 重定向到完整 URL:', url.toString())
    window.location.replace(url.toString())
    return
  }
  const isShortcut = params.get('shortcut') === '1'
  const isViewChart = params.get('view') === 'chart'
  if (!isShortcut && !isViewChart) return
  if (isShortcut && !import.meta.env.DEV) return
  // [FIX 2026-08-07] 防止 HMR 热更新导致组件重挂载后重复执行 shortcut
  //   使用全局变量而非组件级 ref, 因为 HMR 会重置组件内 ref 为初始值
  if (window.__SHORTCUT_APPLIED__) {
    console.log('[shortcut] 已执行过, 跳过 (全局标记)')
    return
  }
  window.__SHORTCUT_APPLIED__ = true
  // [FIX 2026-08-01] 鸡生蛋修复: 之前只在 onMounted+600ms 后调一次, 若那时
  //   versionContext 还未加载完 (canShowChart=false), tryApplyShortcut 直接 return
  //   → scope 永不应用 → 永久停留在 list 视图.
  //   现在分两步:
  //     1) 等 versionContext 加载完 (最多 6s, retry 200ms)
  //     2) 应用 scope (不管 canShowChart - scope 应用后 canShowChart 才变 true)
  //     3) 再 toggle view
  //   [FIX 2026-08-01] 加 productCode/versionCode 支持在 useVersionContext.restoreContext 中处理
  //     (见 useVersionContext.js [FIX 2026-08-01]), 这里只负责 scope + toggle.
  //   [FIX 2026-08-01] page.versionContext 通过 reactive() 包装, 内部 refs 已 auto-unwrap,
  //     所以 selectedVersionId 直接是 number 不是 Ref (无需 .value).
  //   [FIX 2026-08-07] 后端 API 响应慢 (16s+), 增加等待时间到 75 次 × 200ms = 15s
  for (let attempt = 0; attempt < 75; attempt++) {
    const vid = page.versionContext?.selectedVersionId
    if (vid) break
    await new Promise(resolve => setTimeout(resolve, 200))
  }
  const vid = page.versionContext?.selectedVersionId
  console.log('[shortcut] tryApplyShortcut entered, versionContext.selectedVersionId=', vid)
  if (!vid) {
    console.warn('[shortcut] versionContext 未加载 (15s 内无 selectedVersionId), productCode/versionCode 可能错误或后端响应慢')
    return
  }

  // scope 参数: base64(JSON), 兼容 ?scope=eyJidXNpbmVzc19...
  // [NEW 2026-08-07] scopeCode 参数: 按编码选择节点及其所有子孙, 如 ?scopeCode=SCP 选择"供应链计划"
  //   优先级: scope > scopeCode > 无参数(全选)
  // [FIX 2026-08-01] 不再以 canShowChart 为前置: scope 应用后才会有 hasScopeSelection=true
  const scopeRaw = params.get('scope')
  const scopeCode = params.get('scopeCode')
  if (scopeRaw) {
    try {
      const scopeJson = JSON.parse(atob(scopeRaw))
      // scopeJson: { business_object:[ids], service_module:[ids], sub_domain:[ids], domain:[ids], relation_codes:[...] }
      const scopePayload = {}
      if (Array.isArray(scopeJson.domain)) scopePayload.selectedDomainIds = scopeJson.domain
      if (Array.isArray(scopeJson.sub_domain)) scopePayload.selectedSubDomainIds = scopeJson.sub_domain
      if (Array.isArray(scopeJson.service_module)) scopePayload.selectedServiceModuleIds = scopeJson.service_module
      if (Array.isArray(scopeJson.business_object)) scopePayload.selectedBusinessObjectIds = scopeJson.business_object
      if (Array.isArray(scopeJson.relation_codes)) scopePayload.selectedRelationCodes = scopeJson.relation_codes
      if (Array.isArray(scopeJson.relation_ids)) scopePayload.selectedRelationIds = scopeJson.relation_ids
      if (Array.isArray(scopeJson.relation_categories)) scopePayload.selectedCategoryTypes = scopeJson.relation_categories
      page.handleScopeChange(scopePayload)
    } catch (e) {
      console.warn('[shortcut] scope JSON 解析失败, 忽略 scope 参数:', e)
    }
  } else if (scopeCode) {
    // [NEW 2026-08-07] scopeCode 参数: 按编码选择特定节点范围
    //   用法: &scopeCode=SCP 选择"供应链计划"子领域的所有业务对象
    //   多编码: &scopeCode=SCP,SCM 选择多个子领域 (逗号分隔)
    //   无需手动构造 base64 JSON, 适合快速排查验证
    const codes = scopeCode.split(',').map(c => c.trim()).filter(Boolean)
    console.log('[shortcut] 使用 scopeCode 参数:', scopeCode, '解析为', codes.length, '个编码')
    let scopePayload = null
    if (codes.length === 1) {
      scopePayload = await applyScopeCode(codes[0])
    } else {
      scopePayload = await applyScopeCodes(codes)
    }
    if (scopePayload) {
      page.handleScopeChange(scopePayload)
    } else {
      // [FIX 2026-08-08 v2] 绝不全选兜底: scopeCode 是用户明确指定的范围,
      //   如果编码匹配失败就回退到全量加载(3230个对象), 完全违背用户意图,
      //   会导致页面卡死 30s+ 且用户无法感知根因。
      //   改为: 打印错误 → 停止执行 → 用户通过 &debug=scopeCodes 查看可用编码
      console.error('【效率杀手】scopeCode 编码未匹配到任何节点, 快捷启动中止')
      console.error('  使用 &debug=scopeCodes 查看可用编码列表, 或检查编码是否正确')
      console.error('  例如: &scopeCode=SCP 选择"供应链计划", &scopeCode=SCM 选择"采购管理"')
      return  // [!!!] 关键: 停止执行, 绝不进入全选兜底
    }
  } else {
    // [NEW 2026-08-07] 无 scope 参数时自动全选所有业务对象
    //   等待 scopeTreeRef 就绪 + tree 数据加载完成
    console.log('[shortcut] 无 scope 参数, 尝试自动全选')
    for (let attempt = 0; attempt < 30; attempt++) {
      if (scopeTreeRef.value?.selectAll) break
      await new Promise(resolve => setTimeout(resolve, 200))
    }
    if (scopeTreeRef.value?.selectAll) {
      console.log('[shortcut] 调用 selectAll 全选所有业务对象')
      scopeTreeRef.value.selectAll()
    } else {
      console.warn('[shortcut] 6s 内 scopeTreeRef 未就绪, 跳过全选')
    }
  }

  // 等 scope 应用完成 + canShowChart 变 true
  // [FIX 2026-08-05] 改固定 500ms 为轮询: 冷加载时 scope 数据耗时 >500ms,
  //   canShowChart 仍为 false → 放弃切换 → 永久停留 list 视图 (渲染不稳定)。
  //   现轮询等待 canShowChart 变 true (最多 15s), 超时再放弃并告警。
  let canShow = false
  for (let attempt = 0; attempt < 75; attempt++) {  // 75 × 200ms = 15s
    if (page.canShowChart) { canShow = true; break }
    await new Promise(resolve => setTimeout(resolve, 200))
  }
  console.log('[shortcut] after scope, canShowChart=', page.canShowChart)
  if (viewMode.value !== 'chart' && canShow) {
    toggleEmbeddedView()
    console.log('[shortcut] 已进入 EmbeddedChartView')
  } else if (!canShow) {
    console.warn('[shortcut] 15s 内 canShowChart 未变 true, 未进入图表视图 (scope 数据加载慢或未选到有效范围)')
  }
}

onMounted(() => {
  const queryTab = route?.query?.tab
  if (queryTab && page.tabs.find(t => t.name === queryTab)) {
    page.activeTab = queryTab
  }

  // 从其他页面（图表 / 详情 / 工作台等）切回管理页时：
  //   1. 恢复选择/过滤/activeTab (onBeforeRouteLeave 已保存到 sessionStorage)
  //   2. 触发一次数据刷新 (相当于点击 toolbar refresh 按钮)
  //   不再走 "fresh 路径"（清空所有状态）
  // [FIX 2026-06-25] 根因修复：URL 显式携带 productId/versionId 时（如从 landing "常用产品版本" 跳转），
  //   必须让 URL 参数优先于 sessionStorage 快照，否则会被陈旧快照覆盖导致版本丢失。
  //   此时跳过 restoreStateFromDiagram() 中的 versionId/productId 恢复分支，
  //   仅保留 activeTab / scopeIds / filters 等"展示状态"恢复。
  const urlHasProductContext = !!(route?.query?.productId || route?.query?.versionId || route?.query?.productCode || route?.query?.versionCode)
  const restored = urlHasProductContext
    ? page.restoreStateFromDiagram({ skipVersionRestore: true })
    : page.restoreStateFromDiagram()
  if (restored) {
    initialBoIds.value = restored.initialBoIds
    initialRelationCodes.value = restored.initialRelationCodes
    // 强制 RelationScopeTree 重新挂载, 让 initialBoIds / initialRelationCodes 生效
    scopeTreeKey.value++
  }

  // [FIX v3.19] 切回管理页时同步数据 — 状态已恢复, 但列表可能因详情页的编辑而过时
  // 通过 refreshCoordinator 触发 (类似点 toolbar refresh 按钮), 不会清空用户的选择
  if (coordinator && coordinator.refreshAll) {
    // 异步触发, 不阻塞 onMounted
    setTimeout(() => {
      try {
        coordinator.refreshAll()
      } catch (e) {
        console.warn('[v3.19] Failed to refresh on return to arch data page:', e)
      }
    }, 0)
  }

  // [FIX 2026-07-31] shortcut: 等 versionContext 异步初始化完成后再 tryApplyShortcut
  setTimeout(() => {
    tryApplyShortcut().catch(e => console.warn('[shortcut] 应用失败:', e))
  }, 600)

  // [NEW 2026-08-07] debug 模式: 独立于 shortcut, 在控制台打印可用编码列表
  //   用法: /system/archdata?debug=scopeCodes&productCode=TTTTT000&versionCode=V11
  //   无需 shortcut=1, 适合在手动选择产品版本后查看可用编码
  const debugParam = route?.query?.debug || new URLSearchParams(window.location.search).get('debug')
  if (debugParam === 'scopeCodes') {
    setTimeout(() => {
      debugScopeCodes().catch(e => console.warn('[debug] 失败:', e))
    }, 1500)
  }
})

// [FR-005] SAP Fiori iAppState 模式：路由切回时保留状态，不自动刷新
// onActivated 在 keep-alive 缓存组件被激活时调用（非首次 onMounted）
onActivated(() => {
  console.log('[MultiObjectManagementPage] onActivated: state preserved (no auto-refresh)')
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

const currentSortInfo = computed(() => activeMetaListPage.value?.sortInfo || null)
const currentDefaultSort = computed(() => activeMetaListPage.value?.defaultSort || null)
const currentListCount = computed(() => activeMetaListPage.value?.data?.length || 0)
const currentTotalCount = computed(() => {
  const t = activeMetaListPage.value?.filteredTotalCount
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
  // [FIX 2026-08-03] 非 chart action 透传给父组件 (如 refresh → RelationshipManagement.handleToolbarAction)
  //   原: 只调 page.handleGlobalAction, 父组件 (RelationshipManagement) 的 @toolbar-action 永远不触发.
  //   现: emit('toolbarAction', action) 让父组件能响应 refresh/import/export 等 action.
  //   refresh 特殊处理: 只 emit, 不调 page.handleGlobalAction (避免异步 generateDiagram 覆盖 reload nonce).
  emit('toolbarAction', action)
  if (action !== 'refresh') {
    page.handleGlobalAction(action)
  }
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

// [FIX 2026-06-29] 行双击 → 触发该 tab 对应 MetaListPage 的 detail action
//   - 复用现有 rowActions 中的 detail 按钮逻辑
function handleRowDblClick(tabName, { row }) {
  if (!row) return
  const ref = metaListPageRefs[tabName]
  ref?.onRowAction?.({ action: { key: 'detail' }, row })
}

defineExpose({
  refresh: () => activeMetaListPage.value?.refresh(),
  clearScope: () => {
    page.clearScope()
    scopeTreeRef.value?.clear()
  },
  page,
  // [FIX 2026-07-30 v2] 暴露 viewMode 让业务方（如 RelationshipManagement）能根据当前模式
  // 条件渲染 GlobalToolbar 的 chart-config slot（避免 list 视图显示图表按钮）
  viewMode
})

// [FR-001] Per-tab MetaListPage: 每个 tab 独立实例，v-show 保留状态
const metaListPageRefs = reactive({})
const visitedTabs = reactive(new Set([page.activeTab || page.tabs[0]?.name].filter(Boolean)))

// 懒加载：首次访问 tab 时才渲染 MetaListPage
watch(() => page.activeTab, (newTab) => {
  if (newTab) visitedTabs.add(newTab)
})

// 当前激活 tab 的 MetaListPage 引用
const activeMetaListPage = computed(() => metaListPageRefs[page.activeTab])

watch(() => page.combinedFilters, (newFilters) => {
  if (activeMetaListPage.value?.setContextFilters) {
    activeMetaListPage.value.setContextFilters(newFilters)
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

/* [A7 2026-07-30] 嵌入式图表视图占满 detail 区 */
.momp-chart-mode {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

/* [A7 2026-07-30] 嵌入式图表 toggle 按钮激活态高亮（与 chart mode 一致样式） */
.gt-btn-chart-toggle {
  width: auto !important;
  min-width: 90px;
  padding: 4px 12px !important;
  background: rgba(234, 88, 12, 0.08) !important;
  border: 1px solid var(--color-primary, #ea580c) !important;
  color: var(--color-primary, #ea580c) !important;
  font-weight: 500;
  gap: 4px;

  .el-icon {
    font-size: 14px;
  }

  &:hover:not(:disabled) {
    background: var(--color-primary, #ea580c) !important;
    color: #fff !important;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  &.is-active {
    background: var(--color-primary, #ea580c) !important;
    color: #fff !important;
  }
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
