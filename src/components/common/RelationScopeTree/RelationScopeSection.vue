<template>
  <div class="rss-root">
    <div class="rss-toolbar">
      <AppButton variant="text" size="sm" @click="handleExpandAll">
        <el-icon :size="14"><Expand /></el-icon>
        展开全部
      </AppButton>
      <AppButton variant="text" size="sm" @click="handleCollapseAll">
        <el-icon :size="14"><Fold /></el-icon>
        收起全部
      </AppButton>
      <AppButton variant="text" size="sm" @click="handleSelectAll">
        <el-icon :size="14"><Select /></el-icon>
        全选
      </AppButton>
      <AppButton variant="text" size="sm" @click="handleClear">
        <el-icon :size="14"><CircleClose /></el-icon>
        清空
      </AppButton>
      <AppButton variant="text" size="sm" @click="handleRefresh">
        <el-icon :size="14"><RefreshRight /></el-icon>
        刷新
      </AppButton>
    </div>

    <div v-if="stale && !hasData" class="rss-hint">
      <el-icon :size="14"><WarningFilled /></el-icon>
      <span>{{ loadError || '请先在"对象范围"中勾选域，然后展开此面板或点击"刷新"' }}</span>
    </div>

    <div class="rss-tree-container">
      <div v-show="classifierLoading" class="rss-loading">
        <el-icon class="is-loading" :size="20"><Loading /></el-icon>
        <span>分析关系中...</span>
      </div>
      <div v-if="classifierLoading" class="rss-tree-disabled-overlay"></div>
      <div v-show="!classifierLoading && !hasData" class="rss-empty">
        <el-icon :size="40"><Collection /></el-icon>
        <span>{{ loadError || (stale ? '点击"刷新"加载关系数据' : '暂无关系数据') }}</span>
      </div>
      <el-tree
        v-show="!classifierLoading && hasData"
        ref="relationTreeRef"
        :data="classifierTreeData"
        :props="{ label: 'name', children: 'children' }"
        node-key="id"
        show-checkbox
        :default-expand-all="false"
        :default-expanded-keys="classifierExpandedKeys"
        :default-checked-keys="relationCheckedNodeKeys"
        :filter-node-method="filterNodeMethod"
        :expand-on-click-node="false"
        :indent="16"
        @check="handleClassifierCheck"
        @node-expand="onNodeExpand"
        @node-collapse="onNodeCollapse"
      >
        <template #default="{ data }">
          <span class="rss-node">
            <el-icon class="rss-node-icon" :size="14">
              <component :is="getClassifierNodeIcon(data)" />
            </el-icon>
            <span class="rss-node-label" data-testid="rss-tree-label" :title="data.name">{{ data.name }}</span>
            <span v-if="data.count > 0" class="rss-node-count">({{ data.count }})</span>
          </span>
        </template>
      </el-tree>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, inject, nextTick, onMounted } from 'vue'
import {
  Loading, Expand, Fold, Select, CircleClose,
  RefreshRight, WarningFilled, Collection,
  Connection, DataAnalysis, TrendCharts, Document
} from '@element-plus/icons-vue'
import { useRelationClassifier, buildRelationScopeTree } from '@/composables/useRelationClassifier'
import { AppButton } from '@/components/common/AppButton'
import { boService } from '@/services/boService'
import { nodeKeysToRelationCodes, nodeKeysToRelationIds, relationCodesToNodeKeys, relationIdsToNodeKeys } from '@/composables/useScopeTreeState'
import { createTrace } from '@/utils/trace'
import { createScopeGuard } from '@/composables/scopeGuard'
import { apiV1, apiV2 } from '@/utils/httpClient'

const USE_FILTERSOURCE = import.meta.env.VITE_FEATURE_SCOPETREE_FILTERSOURCE !== 'false'

const props = defineProps({
  versionId: {
    type: Number,
    required: true
  },
  selectedBoIds: {
    type: Array,
    default: () => []
  },
  selectedDomainIds: {
    type: Array,
    default: () => []
  },
  selectedSubDomainIds: {
    type: Array,
    default: () => []
  },
  selectedServiceModuleIds: {
    type: Array,
    default: () => []
  },
  stale: {
    type: Boolean,
    default: false
  },
  initialRelationCodes: {
    type: Array,
    default: () => []
  },
  scopeIds: {
    type: Object,
    default: () => ({})
  },
  // OSS 变更时 RelationScopeTree 切换此 prop，触发 RelationScopeSection 清空 preservedCheckedKeys
  relationCodesClearTrigger: {
    type: Number,
    default: 0
  }
})

const emit = defineEmits(['scope-change', 'load'])

const relationTreeRef = ref(null)

const classifierLoading = ref(false)
const allRelationships = ref([])
const businessObjects = ref([])
const loadError = ref('')
const guard = createScopeGuard()

// [FIX] 标记：handleClassifierCheck 正在处理用户勾选操作
// watcher 检测到此标记时跳过 setCheckedKeys，避免 relationCodesToNodeKeys 子集匹配覆盖正确结果
const _skipWatch = ref(false)
const trace = createTrace('RelationScopeSection')

const filterCounter = ref(0)

/**
 * 用户手动展开过的节点 key 集合（跨 el-tree :data 重建持久化）。
 *
 * 背景：当 el-tree 的 :data 变化时, store.setData 会重建整个 nodesMap,
 * 所有用户的展开状态会丢失。需要一个外部 ref 跨重建持久化。
 *
 * 通过 el-tree 的 @node-expand / @node-collapse 事件持续更新此 Set,
 * installStoreSetDataHook 在 setData 内部会读取此 Set 用于恢复展开。
 */
const userExpandedKeys = ref(new Set())

function onNodeExpand(data) {
  if (data?.id != null) userExpandedKeys.value.add(String(data.id))
}
function onNodeCollapse(data) {
  if (data?.id != null) userExpandedKeys.value.delete(String(data.id))
}

/**
 * 应用 scope filter 到 el-tree。
 *
 * 不能用 el-tree 的 filter() 方法 —— 它会自动展开所有可见非叶子节点（tree-store.mjs），
 * 导致用户看到"自动全部展开"的 flash。
 *
 * 正确做法：
 * 1) 修改 store.filterText → el-tree 通过 :filter-node-method 自动重算 node.visible
 *    （这一步不触发 auto-expand）
 * 2) 用户的展开状态由 installStoreSetDataHook 跨数据重建持久化
 */
function filterAndCollapse() {
  const tree = relationTreeRef.value
  if (!tree) return
  const store = tree.store
  if (!store) return

  // 只设置 filterText，触发 :filter-node-method 重新计算 node.visible
  // 不调用 tree.filter() —— 避免 auto-expand 副作用
  store.filterText = String(filterCounter.value)

  // 恢复用户的展开状态（如果 store 因为某些原因被替换过）
  // el-tree 2.15+ 没有 setExpandedKeys / getExpandedKeys API，
  // 必须通过 store.nodesMap[key].expand() 逐个展开（与 installStoreSetDataHook 保持一致）。
  const preferred = userExpandedKeys.value
  if (preferred.size > 0) {
    nextTick(() => {
      const currentStore = relationTreeRef.value?.store
      if (!currentStore?.nodesMap) return
      for (const key of preferred) {
        const node = currentStore.nodesMap[key]
        if (node && !node.isLeaf && typeof node.expand === 'function' && !node.expanded) {
          node.expand()
        }
      }
    })
  }
}

function getScopeFilterParams() {
  return {
    domainIds: props.selectedDomainIds || [],
    subDomainIds: props.selectedSubDomainIds || [],
    serviceModuleIds: props.selectedServiceModuleIds || [],
    boIds: props.selectedBoIds || []
  }
}

function isRelationScopeMatch(rs, filterParams) {
  const { domainIds, subDomainIds, serviceModuleIds, boIds } = filterParams

  if (boIds.length > 0) {
    return boIds.includes(rs.src.boId) || boIds.includes(rs.tgt.boId)
  } else if (serviceModuleIds.length > 0) {
    return serviceModuleIds.includes(rs.src.moduleId) || serviceModuleIds.includes(rs.tgt.moduleId)
  } else if (subDomainIds.length > 0) {
    return subDomainIds.includes(rs.src.subDomainId) || subDomainIds.includes(rs.tgt.subDomainId)
  } else if (domainIds.length > 0) {
    return domainIds.includes(rs.src.domainId) || domainIds.includes(rs.tgt.domainId)
  }
  return true
}

function filterNodeMethod(value, data) {
  if (!data._relationScopes || data._relationScopes.length === 0) {
    return true
  }
  // EXTERNAL（范围外）节点按定义不在选中范围内，不应被 scope filter 过滤
  if (data.scopeType === 'external') {
    return true
  }
  const filterParams = getScopeFilterParams()
  const matched = data._relationScopes.some(rs => isRelationScopeMatch(rs, filterParams))
  // [v1.1.15 修复] 当 _relationScopes 中 boId 是 undefined (跨域 BO 不在业务对象列表中)
  //   时, isRelationScopeMatch 永远 false, 节点全部被过滤, 用户看到 "暂无关系数据"
  //   兜底: 节点有 count 时仍显示, 避免 el-tree 整树变空
  if (matched) return true
  return (data.count || 0) > 0
}

/**
 * 在树中按 id 查找节点（深度优先）
 */
function findNodeById(nodes, id) {
  if (!nodes) return null
  for (const node of nodes) {
    if (String(node.id) === id) return node
    if (node.children?.length > 0) {
      const found = findNodeById(node.children, id)
      if (found) return found
    }
  }
  return null
}

watch(
  () => [props.selectedDomainIds, props.selectedSubDomainIds, props.selectedServiceModuleIds, props.selectedBoIds],
  () => {
    if (!USE_FILTERSOURCE) return
    filterCounter.value++
    nextTick(() => {
      filterAndCollapse()
    })
  },
  { deep: true }
)

/**
 * 持续保存用户勾选的 keys, 用于在 el-tree 因数据变化触发 store.setData 时恢复
 * 根因: el-tree 的 :data 是 computed, 依赖 props.filter* (selectedDomainIds 等)
 *       用户切换对象范围时 filter 变化, computed 重算, el-tree watch 触发 store.setData
 *       setData 会清空 el-tree 的 checked 状态, 我们的 loadRelationships 来不及在 setData 前 save
 * 方案: 通过 @check 持续保存用户选择的 keys, 并 hook store.setData 在数据替换后自动恢复
 */
const preservedCheckedKeys = ref(new Set())
const preservedHalfCheckedKeys = ref(new Set())
let storeSetDataHooked = null

const classifier = useRelationClassifier(
  computed(() => props.selectedDomainIds),
  computed(() => props.selectedSubDomainIds),
  computed(() => props.selectedServiceModuleIds),
  computed(() => props.selectedBoIds),
  allRelationships,
  businessObjects
)

const classifierTreeData = USE_FILTERSOURCE
  ? ref([])
  : computed(() => {
      if (props.stale) return []
      return classifier.treeData.value
    })

watch(classifierTreeData, (newVal) => {
  if (!USE_FILTERSOURCE) return
  if (newVal && newVal.length > 0) {
    nextTick(() => {
      // 树数据重建后：
      // 1) 勾选/展开状态由 installStoreSetDataHook 在 setData 内部自动恢复
      // 2) 这里只需要重新应用 filter (设置 store.filterText) 让 :filter-node-method 重算新节点 visible
      filterAndCollapse()
    })
  }
})

const classifierExpandedKeys = computed(() => classifier.expandedNodeIds.value)

// _ossClearPending 标志已移除。
// 原因：handleObjectScopeChange 已将 emitScopeChange 提前到 relationCodesClearTrigger++ 之前，
// scopeIds.relationExtra 在 watcher 执行前已更新为空 codes，不再需要跳过逻辑。

// 监听 relationCodesClearTrigger prop 变化：OSS 变更时由 RelationScopeTree 触发
// emitScopeChange 已先同步执行（scopeIds.relationExtra 已更新为空 []），
// 此 watch 确保 preservedCheckedKeys 在 loadRelationships 异步完成前清空。
watch(
  () => props.relationCodesClearTrigger,
  (newVal, oldVal) => {
    if (!USE_FILTERSOURCE) return
    if (newVal !== oldVal) {
      preservedCheckedKeys.value = new Set()
      // [FIX] 明确清除 el-tree 的所有 checked 状态（包括被 filter 隐藏的节点）
      // 防止树数据重建后旧 checked key 残留导致联动勾选
      guard.enter()
      relationTreeRef.value?.setCheckedKeys([])
      guard.exit()
      trace.log('clearTrigger→clear', { newVal })
    }
  }
)

const relationCheckedNodeKeys = computed(() => {
  // [FIX] USE_FILTERSOURCE 模式下，直接使用 preservedCheckedKeys 作为勾选状态的真源
  // 绕过 relationCodesToNodeKeys 的子集匹配，避免跨分类（如同服务模块→同子领域跨服务模块）联动勾选
  if (USE_FILTERSOURCE) {
    return [...preservedCheckedKeys.value]
  }
  const codes = props.scopeIds?.relationExtra?.relationCodes
  // null → null（触发 watch），[] → []（不变则不触发）
  return codes == null ? null : relationCodesToNodeKeys(codes, classifierTreeData.value)
})

// [FIX] 从图表展示返回时, 父级 restore 会更新 scopeIds.relationExtra.relationCodes;
// 新挂载的 RSS 内部 preservedCheckedKeys 是空, 树不会显示勾选。
// 当 codes 非空 + 树已加载时, 从 codes 派生出 nodeKeys 填充 preservedCheckedKeys。
// 后续的 relationCheckedNodeKeys watcher → setCheckedKeys → installStoreSetDataHook 会用它恢复勾选。
// v39.4: 使用 relationIds (唯一 ID) 还原勾选状态，避免 relationCodes (类型编码) 跨 scope 误匹配
// 根因: relationCodes 是类型编码 (如 "CONTAINS")，同一 code 可出现在不同 scope 的模块节点中
//   还原时 relationCodesToNodeKeys 会匹配到"范围外"的节点，导致勾选状态"漂移"
// 修复: 优先使用 relationIds 精确匹配叶子 module 节点
watch(
  () => [props.scopeIds?.relationExtra?.relationIds, props.scopeIds?.relationExtra?.relationCodes, classifierTreeData.value],
  ([ids, codes, treeData]) => {
    if (!USE_FILTERSOURCE) return
    if (preservedCheckedKeys.value.size > 0) return  // 已有用户勾选, 不覆盖
    if (!treeData || treeData.length === 0) return  // 树未加载, 等下次

    let nodeKeys = []

    // v39.4: 优先使用 relationIds (唯一 ID) 精确匹配
    if (ids && ids.length > 0) {
      nodeKeys = relationIdsToNodeKeys(ids, treeData)
      if (nodeKeys.length > 0) {
        preservedCheckedKeys.value = new Set(nodeKeys)
        trace.log('restoreFromIds→setPreserved', { ids: ids.length, keys: nodeKeys.length })
        return
      }
    }

    // 兜底: 使用 relationCodes (类型编码) - 旧逻辑，可能跨 scope 误匹配
    if (codes && codes.length > 0) {
      nodeKeys = relationCodesToNodeKeys(codes, treeData)
      if (nodeKeys.length > 0) {
        preservedCheckedKeys.value = new Set(nodeKeys)
        trace.log('restoreFromCodes→setPreserved (fallback)', { codes: codes.length, keys: nodeKeys.length })
      }
    }
  },
  { immediate: true, deep: true }
)

watch(relationCheckedNodeKeys, (newKeys, oldKeys) => {
  if (!USE_FILTERSOURCE) return
  const treeRef = relationTreeRef.value
  if (!treeRef) return

  // [FIX] 跳过由 handleClassifierCheck 触发的回写 — handleClassifierCheck 已经
  // 直接调用了 setCheckedKeys(visibleKeys)，watcher 的 relationCodesToNodeKeys
  // 子集匹配会导致额外节点被勾选，此处跳过以避免覆盖。
  if (_skipWatch.value) {
    trace.log('watch→SKIP (handleClassifierCheck active)')
    return
  }

  // [FIX] 防止递归更新：kKeys must actually change before applying
  // USE_FILTERSOURCE 时 computed 每次返回新数组引用，即使内容未变也可能触发
  if (oldKeys && newKeys.length === oldKeys.length) {
    const s1 = new Set(newKeys.map(String))
    const s2 = new Set(oldKeys.map(String))
    if (s1.size === s2.size && [...s1].every(k => s2.has(k))) {
      trace.log('watch→SKIP (content unchanged)')
      return
    }
  }

  // 直接读取 props.scopeIds.relationCodes
  const currentCodes = props.scopeIds?.relationExtra?.relationCodes
  if (!currentCodes || currentCodes.length === 0) {
    preservedCheckedKeys.value = new Set()
    guard.enter()
    treeRef.setCheckedKeys([])
    guard.exit()
    trace.log('watch→setCheckedKeys(clear)', { currentCodesLen: currentCodes?.length ?? 'null' })
    return
  }

  // setCheckedKeys 同步触发 @check → handleClassifierCheck
  // guard.active() 阻断 handleClassifierCheck 在此 emit
  guard.enter()
  // [FIX] 过滤掉 hidden keys
  const visibleNewKeys = (newKeys || []).filter(key => {
    const node = findNodeById(classifierTreeData.value, String(key))
    return node && filterNodeMethod(null, node)
  })
  relationTreeRef.value.setCheckedKeys(visibleNewKeys)
  guard.exit()
  trace.log('watch→setCheckedKeys', { keyCount: newKeys.length, visibleCount: visibleNewKeys.length })
})

const hasData = computed(() => classifierTreeData.value.length > 0)

function getClassifierNodeIcon(data) {
  if (data.scopeType === 'internal') return Connection
  if (data.scopeType === 'external') return Connection
  if (data.categoryType) return DataAnalysis
  if (data.level === 'domain') return TrendCharts
  if (data.level === 'subDomain') return Document
  return Document
}

const metaObject = inject('metaObject', ref(null))

async function loadRelationships() {
  if (!props.versionId) return

  const isStaleRefresh = props.stale
  const isSilentRefresh = !isStaleRefresh && classifierLoading.value === false && allRelationships.value.length > 0
  console.log('[RelationScopeSection] loadRelationships START: isSilentRefresh=' + isSilentRefresh + ', isStaleRefresh=' + isStaleRefresh + ', allRelationships=' + allRelationships.value.length + ', boIds=' + props.selectedBoIds?.length)

  if (isStaleRefresh && !USE_FILTERSOURCE) {
    preservedCheckedKeys.value = new Set()
    preservedHalfCheckedKeys.value = new Set()
  }

  // 当 OSS 变更触发 silent refresh（USE_FILTERSOURCE）时，清空 preservedCheckedKeys。
  // 此时旧 RSS 选择不再适用于新的树数据（domain/boIds 已变）。
  // installStoreSetDataHook 恢复时会跳过（preservedCheckedKeys 为空）。
  if (USE_FILTERSOURCE && isSilentRefresh) {
    const codes = props.scopeIds?.relationExtra?.relationCodes
    if (!codes || codes.length === 0) {
      preservedCheckedKeys.value = new Set()
      trace.log('loadRelationships→clearPreserved', { reason: 'relationCodes empty' })
    }
  }

  if (!isSilentRefresh) {
    classifierLoading.value = true
  }
  loadError.value = ''
  try {
    console.log('[RelationScopeSection] loadRelationships: version_id=' + props.versionId)
    // [v1.1.15 修复] 用 v2 端点 /api/v2/bo/relationship 替代 v1 端点
    //   背景: TEST888 用户调 /api/v1/relationships?version_id=764 返回 0 条关系,
    //         但调 /api/v2/bo/relationship?version_id=764 返回 11 条 (跟 list 表格一致)
    //   原因: v1/v2 端点权限过滤或查询路径不同
    //   修复: el-tree 跟 list 表格一样用 v2 端点, 避免 el-tree 永远拿不到关系数据
    const result = await apiV2.get('/bo/relationship', { params: { version_id: props.versionId, page_size: 10000 } })

    if (!result.success) {
      throw new Error(result.message || `服务端错误`)
    }

    const newRelationships = result.data?.items || result.data || []

    // 准备新 businessObjects
    let newBusinessObjects
    if (metaObject.value?.business_objects?.length > 0) {
      newBusinessObjects = metaObject.value.business_objects || metaObject.value.businessObjects || []
    } else {
      newBusinessObjects = await loadBusinessObjectsWithHierarchy()
    }
    console.log('[RelationScopeSection] loadRelationships: newRelationships=' + newRelationships.length + ', newBusinessObjects=' + newBusinessObjects.length)

    // 直接赋值 (store.setData hook 会处理状态恢复)
    allRelationships.value = newRelationships
    console.log('[RelationScopeSection] ASSIGNED allRelationships: ' + newRelationships.length)
    businessObjects.value = newBusinessObjects
    console.log('[RelationScopeSection] after assign: treeData=' + (classifierTreeData.value?.length || 0))

    if (USE_FILTERSOURCE) {
      classifierTreeData.value = buildRelationScopeTree(
        {
          domainIds: props.selectedDomainIds || [],
          subDomainIds: props.selectedSubDomainIds || [],
          serviceModuleIds: props.selectedServiceModuleIds || [],
          businessObjectIds: props.selectedBoIds || []
        },
        newRelationships,
        newBusinessObjects
      )
      console.log('[RelationScopeSection] FILTERSOURCE: built tree with ' + classifierTreeData.value.length + ' root nodes')
    }

    emit('load', { relationships: allRelationships.value })

    // 注意: 不再需要在 loadRelationships 内部恢复 state
    // store.setData 已经被 hook, 会在 el-tree 重建后自动应用 preservedCheckedKeys
  } catch (error) {
    console.error('[RelationScopeSection] Failed to load relationships:', error)
    allRelationships.value = []
    loadError.value = error.message || '加载关系数据失败，请刷新重试'
  } finally {
    if (!isSilentRefresh) {
      classifierLoading.value = false
    }
  }
}

async function loadBusinessObjectsWithHierarchy() {
  try {
    const [boResult, smResult, sdResult] = await Promise.all([
      boService.query('business_object', { version_id: props.versionId, page_size: 10000 }),
      boService.query('service_module', { version_id: props.versionId, page_size: 5000 }),
      boService.query('sub_domain', { version_id: props.versionId, page_size: 1000 })
    ])

    const bos = (boResult.data?.items || boResult.data || boResult || [])
    const sms = (smResult.data?.items || smResult.data || smResult || [])
    const sds = (sdResult.data?.items || sdResult.data || sdResult || [])

    const smById = new Map()
    sms.forEach(sm => {
      const smId = sm.id ?? sm.service_module_id
      if (smId != null) smById.set(String(smId), sm)
    })

    const sdById = new Map()
    sds.forEach(sd => {
      const sdId = sd.id ?? sd.sub_domain_id
      if (sdId != null) sdById.set(String(sdId), sd)
    })

    return bos.map(bo => {
      const smId = bo.service_module_id ?? bo.serviceModuleId
      const sm = smId != null ? smById.get(String(smId)) : null
      const sdId = sm ? (sm.sub_domain_id ?? sm.subDomainId) : null
      const sd = sdId != null ? sdById.get(String(sdId)) : null

      return {
        id: bo.id,
        code: bo.code,
        name: bo.name,
        domainId: sd ? (sd.domain_id ?? sd.domainId) : bo.domain_id ?? bo.domainId,
        domain: sd ? (sd.domain_name ?? sd.domainName) : bo.domain_name ?? bo.domainName,
        subDomainId: sd ? (sd.id ?? sd.sub_domain_id) : bo.sub_domain_id ?? bo.subDomainId,
        subDomain: sd ? (sd.name ?? sd.sub_domain_name) : bo.sub_domain_name ?? bo.subDomainName,
        serviceModuleId: smId,
        serviceModule: sm ? (sm.name ?? sm.service_module_name) : bo.service_module_name ?? bo.serviceModuleName,
        serviceModuleName: sm ? (sm.name ?? sm.service_module_name) : bo.service_module_name ?? bo.serviceModuleName
      }
    })
  } catch (e) {
    console.warn('[RelationScopeSection] Failed to load business objects:', e)
    return []
  }
}

function getSelectedScopePayload() {
  // [FIX v3.18] 统一从 preservedCheckedKeys 同时提取 codes + ids，
  // 全选/清空/handleClassifierCheck 共享同一真源 (preservedCheckedKeys)，
  // 避免不同 emit 路径 relationIds 缺失导致 fallback 到 relation_code__in。
  if (USE_FILTERSOURCE) {
    const visibleKeys = [...preservedCheckedKeys.value]
    return {
      relationCodes: nodeKeysToRelationCodes(visibleKeys, classifierTreeData.value),
      relationIds: nodeKeysToRelationIds(visibleKeys, classifierTreeData.value)
    }
  }
  // 非 USE_FILTERSOURCE 模式下 relationIds 由 classifier 内部维护
  return {
    relationCodes: classifier.getSelectedRelationCodes(),
    relationIds: classifier.getSelectedRelationIds?.() || []
  }
}

function emitScopeChange() {
  const { relationCodes, relationIds } = getSelectedScopePayload()
  emit('scope-change', { relationCodes, relationIds })
}

function getSelectedRelationCodes() {
  return getSelectedScopePayload().relationCodes
}

function handleClassifierCheck(data, { checkedKeys, checkedNodes, halfCheckedNodes }) {
  trace.log('handleClassifierCheck', { keyCount: checkedKeys?.length || 0, guardActive: guard.active() })

  if (USE_FILTERSOURCE) {
    // 防止 watch → setCheckedKeys → @check → handleClassifierCheck 循环
    if (guard.active()) return

    // [FIX] 过滤掉被 filter 隐藏的节点 key
    const visibleKeys = (checkedKeys || []).filter(key => {
      const node = findNodeById(classifierTreeData.value, String(key))
      return node && filterNodeMethod(null, node)
    })

    // [FIX] 直接设置 checked keys（本地管理），绕过 relationCodesToNodeKeys 子集匹配。
    // emit 触发的 watcher 会尝试通过 relationCodesToNodeKeys 回写，但 _skipWatch
    // 标记会让 watcher 跳过，避免其他分类（如"同子领域跨服务模块"）的叶子节点被联动勾选。
    preservedCheckedKeys.value = new Set(visibleKeys)
    _skipWatch.value = true

    const codes = nodeKeysToRelationCodes(visibleKeys, classifierTreeData.value)
    // [FIX] 同时传递 relationIds（关系记录 ID），用于精确过滤关系列表。
    // relation_code 是类型编码（如 APPROVES），同一 code 对应多条关系，无法精确定位。
    const ids = nodeKeysToRelationIds(visibleKeys, classifierTreeData.value)
    emit('scope-change', { relationCodes: codes, relationIds: ids })

    guard.enter()
    relationTreeRef.value?.setCheckedKeys(visibleKeys)
    guard.exit()

    trace.log('handleClassifierCheck→done', { keyCount: visibleKeys.length, codeCount: codes.length })
    nextTick(() => { _skipWatch.value = false })
    return
  }

  if (guard.active()) {
    return
  }
  const effectiveChecked = checkedKeys || []
  preservedCheckedKeys.value = new Set(effectiveChecked)
  preservedHalfCheckedKeys.value = new Set(halfCheckedNodes?.map(n => n.id) || [])
  console.log('[RelationScopeSection] handleClassifierCheck: preserved=' + preservedCheckedKeys.value.size)
  classifier.selectedScopeIds.value = effectiveChecked
  emitScopeChange()

  if (effectiveChecked.length === 0) {
    nextTick(() => {
      const currentChecked = relationTreeRef.value?.getCheckedKeys?.() || []
      if (currentChecked.length > 0) {
        console.log('[RelationScopeSection] handleClassifierCheck: force clear lingering keys:', currentChecked.length)
        guard.enter()
        relationTreeRef.value?.setCheckedKeys([], false)
        guard.exit()
      }
    })
  }
}

function handleExpandAll() {
  classifier.expandAll()
  classifierExpandedKeys.value = [...classifier.expandedNodeIds.value]
  if (!relationTreeRef.value?.store) return
  const nodesMap = relationTreeRef.value.store.nodesMap || {}
  Object.values(nodesMap).forEach(node => {
    if (node.childNodes && node.childNodes.length > 0) {
      node.expanded = true
    }
  })
}

function handleCollapseAll() {
  classifier.collapseAll()
  classifierExpandedKeys.value = []
  if (!relationTreeRef.value?.store) return
  const nodesMap = relationTreeRef.value.store.nodesMap || {}
  Object.values(nodesMap).forEach(node => {
    if (node.expanded) {
      node.expanded = false
    }
  })
}

function handleSelectAll() {
  if (USE_FILTERSOURCE) {
    const allIds = collectAllClassifierIds(classifierTreeData.value)
    const codes = nodeKeysToRelationCodes(allIds, classifierTreeData.value)
    const ids = nodeKeysToRelationIds(allIds, classifierTreeData.value)
    emit('scope-change', { relationCodes: codes, relationIds: ids })
    return
  }

  const allIds = collectAllClassifierIds(classifierTreeData.value)
  classifier.selectedScopeIds.value = allIds
  if (relationTreeRef.value) {
    guard.enter()
    relationTreeRef.value.setCheckedKeys(allIds, false)
    guard.exit()
  }
  emitScopeChange()
}

function collectAllClassifierIds(nodes) {
  const ids = []
  nodes.forEach(node => {
    ids.push(node.id)
    if (node.children && node.children.length > 0) {
      ids.push(...collectAllClassifierIds(node.children))
    }
  })
  return ids
}

function handleClear() {
  if (USE_FILTERSOURCE) {
    emit('scope-change', { relationCodes: [], relationIds: [] })
    return
  }

  classifier.selectedScopeIds.value = []
  if (relationTreeRef.value) {
    guard.enter()
    relationTreeRef.value.setCheckedKeys([], false)
    guard.exit()
  }
  emitScopeChange()
}

async function handleRefresh() {
  await loadRelationships()
}

function clear() {
  handleClear()
}

/**
 * 安装 el-tree store.setData 的钩子，跨 :data 重建恢复用户状态。
 *
 * 解决的问题：
 * 1) 用户展开的节点 (issue 1, regression) —— store.setData 会重置 node.expanded
 * 2) 用户勾选的节点 (反勾选 bug) —— store.setData 会清空 el-tree 的 checked 状态
 *
 * 实现思路：
 * 1) 调用 origSetData 前，从旧 store 抓取所有 expanded=true 的节点 key (data.id 字符串)
 * 2) 合并 userExpandedKeys (跨重建持久化的 Set)
 * 3) 调用 origSetData 重建 store
 * 4) 在 nextTick 中用 el-tree 标准 API 恢复：
 *    - setCheckedKeys (el-tree 2.15+ 仍有此 API)
 *    - node.expand() (el-tree 2.15+ 没有 setExpandedKeys，必须逐个 node.expand())
 *    - 同步新 store.filterText 让 :filter-node-method 重算新节点 visible
 *
 * 注意：el-tree 2.15+ 没有 setExpandedKeys/getExpandedKeys API。
 */
function installStoreSetDataHook() {
  if (storeSetDataHooked) return
  if (!relationTreeRef.value?.store) return
  const store = relationTreeRef.value.store
  const origSetData = store.setData.bind(store)
  store.setData = function (newData) {
    // 1) 抓取当前 store 中所有"用户展开过的节点 key"（data.id 字符串）
    //    注意：用 nodesMap 的 key (string) 而不是 node.id (number)
    const savedExpandedKeys = []
    const oldNodesMap = relationTreeRef.value?.store?.nodesMap
    if (oldNodesMap) {
      for (const [key, node] of Object.entries(oldNodesMap)) {
        if (node.expanded) savedExpandedKeys.push(key)
      }
    }
    // 合并 userExpandedKeys（通过 @node-expand/@node-collapse 跨重建持久化）
    const allSavedExpanded = [...new Set([...savedExpandedKeys, ...userExpandedKeys.value])]

    // 2) 执行原始 setData → 重建 store.nodesMap
    const result = origSetData(newData)

    // 3) 收集新树的所有有效 data.id（字符串）
    const allDataIds = new Set()
    const collectIds = (nodes) => {
      for (const n of nodes) {
        if (n.id != null) allDataIds.add(String(n.id))
        if (n.children) collectIds(n.children)
      }
    }
    collectIds(newData || [])

    // 4) 过滤出在新树中仍然有效的 keys
    const validChecked = preservedCheckedKeys.value.size > 0
      ? Array.from(preservedCheckedKeys.value).filter(k => allDataIds.has(String(k)))
      : []
    const validExpanded = allSavedExpanded.filter(k => allDataIds.has(String(k)))

    // 5) 在 nextTick 后用 el-tree 标准 API 恢复状态
    //    - setCheckedKeys: 恢复勾选 (el-tree 2.15+ 仍有此 API)
    //    - node.expand(): 恢复展开 (el-tree 2.15+ 没有 setExpandedKeys，必须逐个 node.expand())
    //    - 同步 filterText 让 :filter-node-method 对新节点重算 visible
    if (validChecked.length > 0 || validExpanded.length > 0) {
      nextTick(() => {
        if (validChecked.length > 0) {
          guard.enter()
          relationTreeRef.value?.setCheckedKeys(validChecked, false)
          guard.exit()
        }
        if (validExpanded.length > 0) {
          const newStore = relationTreeRef.value?.store
          if (newStore?.nodesMap) {
            for (const key of validExpanded) {
              const node = newStore.nodesMap[key]
              if (node && !node.isLeaf && typeof node.expand === 'function' && !node.expanded) {
                node.expand()
              }
            }
          }
        }
        // 同步新 store 的 filterText
        const newStore = relationTreeRef.value?.store
        if (newStore && newStore.filterText !== String(filterCounter.value)) {
          newStore.filterText = String(filterCounter.value)
        }
      })
    } else if (newData?.length > 0) {
      // 新数据但没有保留的状态 → 清掉可能的残留勾选
      nextTick(() => {
        const lingering = relationTreeRef.value?.getCheckedKeys?.() || []
        if (lingering.length > 0) {
          guard.enter()
          relationTreeRef.value?.setCheckedKeys([], false)
          guard.exit()
        }
        // 同步新 store 的 filterText
        const newStore = relationTreeRef.value?.store
        if (newStore && newStore.filterText !== String(filterCounter.value)) {
          newStore.filterText = String(filterCounter.value)
        }
      })
    }
    return result
  }
  storeSetDataHooked = store.setData
}

watch(relationTreeRef, (val) => {
  if (val) {
    installStoreSetDataHook()
  }
})

onMounted(() => {
  loadRelationships()
})

defineExpose({
  loadRelationships,
  clear,
  getSelectedRelationCodes,
  forceClearChecked() {
    preservedCheckedKeys.value = new Set()
    if (relationTreeRef.value) {
      guard.enter()
      relationTreeRef.value.setCheckedKeys([], false)
      guard.exit()
    }
    trace.log('forceClearChecked', {})
  },
  // [TEST-ONLY] 暴露内部状态供 Playwright 测试诊断
  _test: {
    get treeData() { return classifierTreeData.value },
    get loading() { return classifierLoading.value },
    get hasData() { return classifierTreeData.value.length > 0 },
    get error() { return loadError.value },
    get relationCount() { return allRelationships.value?.length || 0 },
    get filterParams() { return getScopeFilterParams() },
    get selectedCodes() { return getSelectedRelationCodes() }
  }
})
</script>

<style scoped>
.rss-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-width: 0;
  overflow: hidden;
}

.rss-toolbar {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 2px var(--spacing-xs);
  border-bottom: var(--border-width-thin) solid var(--color-border);
  flex-shrink: 0;
}

.rss-toolbar :deep(.app-btn) {
  font-size: var(--font-size-xs);
  padding: 2px 4px;
}

.rss-hint {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-warning-bg, #fdf6ec);
  color: var(--color-warning-text, #e6a23c);
  font-size: var(--font-size-sm);
}

.rss-tree-container {
  flex: 1;
  min-height: 150px;
  overflow-y: auto;
  overflow-x: hidden;
  padding: var(--spacing-xs) 0;
  min-width: 0;
}

:deep(.collapsible-panel__content) {
  overflow-x: hidden;
}

.rss-node {
  display: flex;
  align-items: center;
  flex: 1;
  gap: var(--spacing-xs);
  overflow: hidden;
}

.rss-node-icon {
  flex-shrink: 0;
  color: var(--color-text-tertiary);
}

.rss-node-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--font-size-sm);
}

.rss-node-count {
  flex-shrink: 0;
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.rss-loading,
.rss-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--spacing-xl) var(--spacing-md);
  color: var(--color-text-tertiary);
  gap: var(--spacing-sm);
}

.rss-tree-disabled-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.4);
  z-index: 10;
  pointer-events: none;
}

.rss-tree-container {
  position: relative;
}

:deep(.el-tree-node__content) {
  height: 32px;
  padding-right: var(--spacing-sm);
}

:deep(.el-tree-node__label) {
  font-size: var(--font-size-sm);
}

:deep(.el-checkbox) {
  margin-right: var(--spacing-sm);
}
</style>
