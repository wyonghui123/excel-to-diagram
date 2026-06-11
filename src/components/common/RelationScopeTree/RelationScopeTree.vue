<template>
  <div class="relation-scope-tree">
    <CollapsiblePanel
      title="对象范围"
      :badge="selectedBoCount"
      :default-expanded="objectExpanded"
      :height-full="false"
      class="rst-panel-object"
      @toggle="handleObjectToggle"
    >
      <ObjectScopeSection
        ref="objectScopeRef"
        :version-id="versionId"
        :show-search="showSearch"
        :initial-bo-ids="initialBoIds"
        :scope-ids="scopeIds"
        :key="1"
        @scope-change="handleObjectScopeChange"
        @load="handleTreeLoad"
      />
    </CollapsiblePanel>

    <CollapsiblePanel
      title="关系范围"
      :badge="relationCodesCount"
      :default-expanded="relationExpanded"
      :height-full="false"
      class="rst-panel-relation"
      @toggle="handleRelationToggle"
    >
      <RelationScopeSection
        ref="relationScopeRef"
        :version-id="versionId"
        :selected-bo-ids="selectedBoIds"
        :selected-domain-ids="selectedDomainIds"
        :selected-sub-domain-ids="selectedSubDomainIds"
        :selected-service-module-ids="selectedServiceModuleIds"
        :stale="relationStale"
        :scope-ids="scopeIds"
        :initial-relation-codes="initialRelationCodes"
        :relation-codes-clear-trigger="relationCodesClearTrigger"
        @scope-change="handleRelationScopeChange"
        @load="handleRelationLoad"
      />
    </CollapsiblePanel>

    <CollapsiblePanel
      title="过滤条件"
      :badge="filterCount"
      :default-expanded="filterExpanded"
      :height-full="false"
      class="rst-panel-filter"
      @toggle="handleFilterToggle"
    >
      <RelationFilterSection
        ref="filterSectionRef"
        :version-id="versionId"
        :relation-disabled="filterDisabled"
        @filter-change="handleFilterChange"
      />
    </CollapsiblePanel>
  </div>
</template>

<script setup>
import { ref, computed, watch, inject, onMounted, onUnmounted, nextTick, shallowRef } from 'vue'
import { boService } from '@/services/boService'
import EnumService from '@/services/enumService'
import { useScopeFilterSource } from '@/composables/filterSources/useScopeFilterSource'
import ObjectScopeSection from './ObjectScopeSection.vue'
import RelationScopeSection from './RelationScopeSection.vue'
import RelationFilterSection from './RelationFilterSection.vue'
import CollapsiblePanel from '@/components/common/CollapsiblePanel/CollapsiblePanel.vue'
import { createTrace } from '@/utils/trace'

const props = defineProps({
  versionId: {
    type: Number,
    required: true
  },
  showSearch: {
    type: Boolean,
    default: true
  },
  defaultExpandAll: {
    type: Boolean,
    default: false
  },
  initialBoIds: {
    type: Array,
    default: () => []
  },
  initialRelationCodes: {
    type: Array,
    default: () => []
  },
  filterDisabled: {
    type: Boolean,
    default: false
  },
  scopeIds: {
    type: Object,
    default: () => ({})
  }
})

const emit = defineEmits(['scope-change', 'load'])
const trace = createTrace('RelationScopeTree')

const objectScopeRef = ref(null)
const relationScopeRef = ref(null)
const filterSectionRef = ref(null)
const coordinator = inject('refreshCoordinator', null)
// [FIX] 从图表返回时 (initialRelationCodes 或 scopeIds.relationExtra.relationCodes 非空)
//       自动展开关系范围面板, 让用户能直观看到已恢复的勾选
const _hasInitialRelCodes = () => {
  if (Array.isArray(props.initialRelationCodes) && props.initialRelationCodes.length > 0) return true
  if (Array.isArray(props.scopeIds?.relationExtra?.relationCodes) && props.scopeIds.relationExtra.relationCodes.length > 0) return true
  return false
}
const objectExpanded = ref(true)
const relationExpanded = ref(_hasInitialRelCodes())
const filterExpanded = ref(false)

// [FIX] 监听 initialRelationCodes / scopeIds.relationExtra 变化, 动态展开关系范围面板
// 场景: chart app 返回时, 父级 restore 流程异步更新 props, 初始 _hasInitialRelCodes() 是 false
//       后续 props 同步进来时, 需要重新判断并展开
watch(
  () => [props.initialRelationCodes, props.scopeIds?.relationExtra?.relationCodes],
  ([codes1, codes2]) => {
    const has = (Array.isArray(codes1) && codes1.length > 0) ||
                (Array.isArray(codes2) && codes2.length > 0)
    if (has && !relationExpanded.value) {
      relationExpanded.value = true
      trace.log('autoExpand→relPanel', { codes1: codes1?.length, codes2: codes2?.length })
    }
  },
  { immediate: true, deep: true }
)

const selectedAnnotationCategories = ref([])
const selectedFilterRelationCodes = ref([])
const localSelectedBoCount = ref(0)

function handleObjectToggle(expanded) {
  objectExpanded.value = expanded
  if (expanded) {
    relationExpanded.value = false
    filterExpanded.value = false
  }
}

function handleRelationToggle(expanded) {
  relationExpanded.value = expanded
  if (expanded) {
    objectExpanded.value = false
    filterExpanded.value = false
    if (relationStale.value) {
      scheduleAutoLoad()
    }
  }
}

function handleFilterToggle(expanded) {
  filterExpanded.value = expanded
  if (expanded) {
    objectExpanded.value = false
    relationExpanded.value = false
  }
}

const metaObject = inject('metaObject', ref(null))

const scopeSource = useScopeFilterSource({
  id: 'relation-scope',
  label: 'RelationScope',
  metaObject
})

const selectedBoIds = scopeSource.selectedBoIds
const selectedRelationCodes = scopeSource.selectedRelationCodes
const selectedRelationIds = scopeSource.selectedRelationIds
const selectedDomainIds = shallowRef([])
const selectedSubDomainIds = shallowRef([])
const selectedServiceModuleIds = shallowRef([])
const relationStale = ref(false)
const relationCodesClearTrigger = ref(0)  // OSS 变更时切换，触发 RelationScopeSection 清空 preservedCheckedKeys
// [v32-FIX] 一次性标志：首次 OSS change 后如果 relationCodes 是从 chart 恢复的，跳过清空保护 restore；
//   之后再改 OSS 则正常清空 RSS。避免 restoredCodes 检查因 codes 从未被清空而永久跳过清空。
const _restoreProtectionConsumed = ref(false)
const treeData = shallowRef([])

const hierarchyMap = computed(() => {
  if (!treeData.value || treeData.value.length === 0) return {}

  const map = {}
  function walk(nodes, domainId, subDomainId, serviceModuleId) {
    if (!nodes) return
    for (const node of nodes) {
      if (node.type === 'domain') {
        map[node.id] = { domainId: node.id }
        walk(node.children, node.id, null)
      } else if (node.type === 'sub_domain') {
        map[node.id] = { domainId, subDomainId: node.id }
        walk(node.children, domainId, node.id)
      } else if (node.type === 'service_module') {
        map[node.id] = { domainId, subDomainId, serviceModuleId: node.id }
        walk(node.children, domainId, subDomainId, node.id)
      } else if (node.type === 'business_object') {
        map[node.id] = { domainId, subDomainId, serviceModuleId }
        walk(node.children, domainId, subDomainId, serviceModuleId)
      }
    }
  }
  walk(treeData.value)
  return map
})

const effectiveDomainIds = computed(() => {
  const ids = new Set([...selectedDomainIds.value])
  for (const id of selectedSubDomainIds.value) {
    const info = hierarchyMap.value[id]
    if (info?.domainId != null) ids.add(info.domainId)
  }
  for (const id of selectedServiceModuleIds.value) {
    const info = hierarchyMap.value[id]
    if (info?.domainId != null) ids.add(info.domainId)
  }
  return [...ids]
})

const effectiveSubDomainIds = computed(() => {
  const ids = new Set([...selectedSubDomainIds.value])
  for (const id of selectedServiceModuleIds.value) {
    const info = hierarchyMap.value[id]
    if (info?.subDomainId != null) ids.add(info.subDomainId)
  }
  return [...ids]
})

const effectiveServiceModuleIds = computed(() => {
  const ids = new Set([...selectedServiceModuleIds.value])
  for (const id of selectedBoIds.value) {
    const info = hierarchyMap.value[id]
    if (info?.serviceModuleId != null) ids.add(info.serviceModuleId)
  }
  return [...ids]
})

// 取 4 个 id 源 (boIds / domainIds / subDomainIds / serviceModuleIds) 的总长度。
// 正常路径: handleObjectScopeChange 写 localSelectedBoCount (包含 4 源之和), 直接用。
// Restore 路径: localSelectedBoCount=0 但 props 同步后 4 个 ref 已有值, 用派生值兜底。
// 这样 restore 后 chip "对象范围 1" 不会因为 localSelectedBoCount 没被触发而消失。
const selectedBoCount = computed(() => {
  const local = localSelectedBoCount.value
  if (local > 0) return local
  return (selectedBoIds.value?.length || 0) +
    (selectedDomainIds.value?.length || 0) +
    (selectedSubDomainIds.value?.length || 0) +
    (selectedServiceModuleIds.value?.length || 0)
})
const relationCodesCount = computed(() => selectedRelationCodes.value?.length || 0)

const filterCount = computed(() => {
  return filterSectionRef.value?.filterCount || 0
})

const annotationCount = computed(() => {
  return filterSectionRef.value?.annotationCount || 0
})

const relationCount = computed(() => {
  return filterSectionRef.value?.relationCount || 0
})

const scopeCategories = computed(() => {
  return metaObject.value?.hierarchy_scopes || []
})

const computedCategories = computed(() => {
  if (selectedBoIds.value.length === 0) return []

  return scopeCategories.value.map(cat => ({
    ...cat,
    count: 0
  }))
})

function handleObjectScopeChange({ boIds, domainIds, subDomainIds, serviceModuleIds }) {
  selectedBoIds.value = boIds || []
  selectedDomainIds.value = domainIds || []
  selectedSubDomainIds.value = subDomainIds || []
  selectedServiceModuleIds.value = serviceModuleIds || []
  localSelectedBoCount.value = (boIds || []).length + (domainIds || []).length + (subDomainIds || []).length + (serviceModuleIds || []).length

  // OSS 变更时清空 relationCodes。
  // 关键：先同步 emitScopeChange 让 parent 更新 scopeIds.relationExtra = []，
  // 然后同步调用 loadRelationships 用空 codes 重建 RSS 树。
  // 不依赖 scheuleAutoLoad 的 300ms 延迟，避免时序窗口。
  // [v32-FIX] 用一次性标志位替代 restoredCodes 检查：
  //   首次 OSS change 时若 relationCodes 非空（从 chart 恢复），
  //   跳过清空保护 restore；之后再改 OSS 则正常清空 RSS。
  const restoredCodes = props.scopeIds?.relationExtra?.relationCodes
  const hasRestoredCodes = restoredCodes && restoredCodes.length > 0
  if (!_restoreProtectionConsumed.value && hasRestoredCodes) {
    // 首次：跳过清空，保护 restore 状态
    _restoreProtectionConsumed.value = true
  } else {
    // 后续：正常清空 RSS
    _restoreProtectionConsumed.value = true  // 标志已消费
    selectedRelationCodes.value = []
    emitScopeChange()
  }
  // emitScopeChange 同步执行 parent 的 handleScopeChange，scopeIds.relationExtra 现在是 []

  // 切换到 RelationScopeSection 触发预设清空 + forceClear
  relationCodesClearTrigger.value++
  const exposed = relationScopeRef.value?.$
  if (exposed?.exposed?.forceClearChecked) {
    exposed.exposed.forceClearChecked()
  }
  // 同步加载 RSS 树：此时 scopeIds 已更新为空 codes，新树无选中节点
  // 传入 true 表示 silent refresh（不显示 loading）
  relationScopeRef.value?.loadRelationships?.(true)
  trace.log('handleObjectScopeChange→clearRSS', { boCount: localSelectedBoCount.value })

  if ((boIds && boIds.length > 0) || (domainIds && domainIds.length > 0) ||
      (subDomainIds && subDomainIds.length > 0) || (serviceModuleIds && serviceModuleIds.length > 0)) {
    relationStale.value = true
  }
}

function handleRelationScopeChange({ relationCodes, relationIds }) {
  selectedRelationCodes.value = relationCodes || []
  // [FIX] 传递 relationIds 用于精确过滤
  selectedRelationIds.value = relationIds || []
  emitScopeChange()
}

function handleFilterChange({ annotationCategories, relationCodes }) {
  selectedAnnotationCategories.value = annotationCategories || []
  selectedFilterRelationCodes.value = relationCodes || []
  emitScopeChange()
}

function handleTreeLoad(data) {
  treeData.value = data
  emit('load', data)
}

function handleRelationLoad() {
  relationStale.value = false
}

function emitScopeChange() {
  emit('scope-change', {
    boIds: selectedBoIds.value,
    selectedBusinessObjectIds: selectedBoIds.value,
    relationCodes: selectedRelationCodes.value,
    relationIds: selectedRelationIds.value,
    categoryTypes: computedCategories.value.map(c => c.id),
    selectedDomainIds: selectedDomainIds.value,
    selectedSubDomainIds: selectedSubDomainIds.value,
    selectedServiceModuleIds: selectedServiceModuleIds.value,
    effectiveDomainIds: effectiveDomainIds.value,
    effectiveSubDomainIds: effectiveSubDomainIds.value,
    effectiveServiceModuleIds: effectiveServiceModuleIds.value,
    annotationCategories: selectedAnnotationCategories.value,
    filterRelationCodes: selectedFilterRelationCodes.value
  })
}

function getCheckedBoIds() {
  return selectedBoIds.value
}

function getSelectedRelationCodes() {
  return selectedRelationCodes.value
}

function clearObjectScope() {
  objectScopeRef.value?.clear()
  selectedBoIds.value = []
  selectedDomainIds.value = []
  selectedSubDomainIds.value = []
  selectedServiceModuleIds.value = []
  localSelectedBoCount.value = 0
  relationStale.value = false
  emitScopeChange()
}

function clearRelationScope() {
  relationScopeRef.value?.clear()
  selectedRelationCodes.value = []
  emitScopeChange()
}

function clearFilterCondition() {
  filterSectionRef.value?.clearAll()
  selectedAnnotationCategories.value = []
  selectedFilterRelationCodes.value = []
  emitScopeChange()
}

function clearAnnotationFilter() {
  const total = filterSectionRef.value?.selectedAnnotations?.length || 0
  if (total === 0) return
  filterSectionRef.value?.setFilters({
    annotationCategories: [],
    relationCodes: filterSectionRef.value?.selectedRelations || []
  })
  selectedAnnotationCategories.value = []
  emitScopeChange()
}

function clearRelationFilter() {
  const total = filterSectionRef.value?.selectedRelations?.length || 0
  if (total === 0) return
  filterSectionRef.value?.setFilters({
    annotationCategories: filterSectionRef.value?.selectedAnnotations || [],
    relationCodes: []
  })
  selectedFilterRelationCodes.value = []
  emitScopeChange()
}

function clear() {
  objectScopeRef.value?.clear()
  relationScopeRef.value?.clear()
  selectedBoIds.value = []
  selectedDomainIds.value = []
  selectedSubDomainIds.value = []
  selectedServiceModuleIds.value = []
  selectedRelationCodes.value = []
  localSelectedBoCount.value = 0
  relationStale.value = false
  emitScopeChange()
}

function loadTreeData() {
  objectScopeRef.value?.loadTreeData()
}

async function refresh() {
  objectScopeRef.value?.loadTreeData({ silent: true })
  await relationScopeRef.value?.loadRelationships()
}

async function loadRelationTypes() {
  try {
    const result = await EnumService.loadOptions('relation_type')
    return result
  } catch (e) {
    console.error('[RelationScopeTree] Failed to load relation types:', e)
    return []
  }
}

let autoLoadTimer = null
let autoLoadInProgress = false
let pendingLoad = false
function scheduleAutoLoad() {
  clearTimeout(autoLoadTimer)
  if (autoLoadInProgress) {
    pendingLoad = true
    return
  }
  autoLoadTimer = setTimeout(async () => {
    autoLoadInProgress = true
    pendingLoad = false
    try {
      await relationScopeRef.value?.loadRelationships()
    } finally {
      autoLoadInProgress = false
      if (pendingLoad) {
        scheduleAutoLoad()
      }
    }
  }, 300)
}
watch(selectedBoIds, scheduleAutoLoad)
watch(selectedDomainIds, scheduleAutoLoad)
watch(selectedSubDomainIds, scheduleAutoLoad)
watch(selectedServiceModuleIds, scheduleAutoLoad)

// [FIX] 从图表展示返回时, 父级 restore 会更新 scopeIds; 新挂载的 tree 本地 state
// (selectedDomainIds / selectedSubDomainIds / selectedServiceModuleIds) 需要从 props 同步,
// 否则后续 filter / relation change 触发的 emitScopeChange 会用空值覆盖父级已 restore 的值
// immediate: true 是必要的: 新 child mount 时, props 已经携带了父级 restore 后的 [129],
// 但 watch 默认不立即触发,会导致 local state 一直是 [], 进而后续 emit 用空值覆盖父级
function syncFromProps(getter, target) {
  watch(getter, (newVal) => {
    if (!newVal) return
    if (JSON.stringify(newVal) === JSON.stringify(target.value)) return
    target.value = [...newVal]
  }, { deep: true, immediate: true })
}
syncFromProps(() => props.scopeIds?.domain?.selected, selectedDomainIds)
syncFromProps(() => props.scopeIds?.sub_domain?.selected, selectedSubDomainIds)
syncFromProps(() => props.scopeIds?.service_module?.selected, selectedServiceModuleIds)
// [FIX] restore 路径下也要同步 relationExtra 里的 codes/ids 到本地 scopeSource ref，
// 否则后续 RSS 的 preservedCheckedKeys → emit scope-change 链会用空值覆盖父级已 restore 的值
syncFromProps(() => props.scopeIds?.relationExtra?.relationCodes, selectedRelationCodes)
syncFromProps(() => props.scopeIds?.relationExtra?.relationIds, selectedRelationIds)

watch(() => props.versionId, () => {
  selectedBoIds.value = []
  selectedDomainIds.value = []
  selectedSubDomainIds.value = []
  selectedServiceModuleIds.value = []
  selectedRelationCodes.value = []
  localSelectedBoCount.value = 0
  relationStale.value = false
  treeData.value = []
})

onMounted(() => {
  if (coordinator) {
    coordinator.register('scopeTree', refresh)
  }
})

onUnmounted(() => {
  if (coordinator) {
    coordinator.unregister('scopeTree')
  }
})

defineExpose({
  source: scopeSource.source,
  getCheckedBoIds,
  getSelectedRelationCodes,
  clear,
  clearObjectScope,
  clearRelationScope,
  clearFilterCondition,
  clearAnnotationFilter,
  clearRelationFilter,
  loadTreeData,
  refresh,
  loadRelationTypes,
  selectedAnnotationCategories,
  selectedFilterRelationCodes,
  selectedBoCount,
  relationCodesCount,
  filterCount,
  annotationCount,
  relationCount
})
</script>

<style scoped>
.relation-scope-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-bg-container);
  overflow: hidden;
}

:deep(.collapsible-panel) {
  border-bottom: var(--border-width-thin) solid var(--color-border);
  flex-shrink: 0;
}

:deep(.collapsible-panel:last-child) {
  border-bottom: none;
}

:deep(.collapsible-panel .collapsible-panel__container) {
  border-right: none;
}

:deep(.collapsible-panel .collapsible-panel__resizer) {
  display: none;
}

:deep(.collapsible-panel.is-collapsed) {
  width: 100% !important;
  min-width: 100% !important;
  flex: 0 0 auto !important;
}

:deep(.collapsible-panel.is-collapsed .collapsible-panel__header) {
  border-bottom: none;
}

:deep(.collapsible-panel.is-collapsed ~ .collapsible-panel .collapsible-panel__header) {
  border-bottom: none;
}

.rst-panel-object {
  flex: 0 1 auto;
  min-height: 48px;
}

.rst-panel-relation {
  flex: 0 1 auto;
  min-height: 48px;
}

.rst-panel-filter {
  flex: 1;
  min-height: 48px;
}

.relation-scope-tree:has(.rst-panel-relation.is-collapsed) .rst-panel-object {
  flex: 1;
}

/* [FIX] 关系范围面板展开时, 给 .collapsible-panel 一个明确的高度
   原因: CollapsiblePanel 内部是 flex 嵌套 (panel → container → header + content),
   当外层 .rst-panel-relation 用 flex: 0 1 auto 时, 其尺寸由内容决定, 而
   .collapsible-panel__content 因循环依赖坍缩为 0, 导致 RSS 树被裁掉。
   用 :not(.is-collapsed) 在面板展开时切换为 flex: 1 1 0, 让面板占满可用空间,
   这样 content 才有高度。
*/
.rst-panel-relation:not(.is-collapsed) {
  flex: 1 1 0;
  min-height: 200px;
}

/* [FIX] CollapsiblePanel 内部 container 高度撑满, 让 content 区域有空间 */
.rst-panel-relation:not(.is-collapsed) :deep(.collapsible-panel) {
  height: 100%;
}
.rst-panel-relation:not(.is-collapsed) :deep(.collapsible-panel__container) {
  height: 100%;
}
</style>
