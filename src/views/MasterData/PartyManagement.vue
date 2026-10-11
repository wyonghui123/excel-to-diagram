<template>
  <MultiObjectManagementPage
    ref="pageRef"
    :object-types="objectTypes"
    :options="pageOptions"
    @toolbar-action="handleToolbarAction"
  />
</template>

<script setup>
/**
 * PartyManagement — 往来单位管理页（MOMP 配置注入）
 *
 * 形态：左树 = 往来单位组（勾选过滤往来单位），右表 = 两个 tab（往来单位 / 往来单位组）。
 * 与物料管理页（MaterialManagement.vue）同构，差异只在过滤链：
 *
 * - 物料: items.item_group_id 是直 FK，左树勾选 → item_group_id__in 一步到位。
 * - 往来单位: party 不直挂 group。分组关系在关系层 —— party_relations.group_id（N:1）
 *   指向 party_groups，伙伴侧是 party2_id（party1_id 恒为我方侧）。
 *   故左树勾选 → 先查 party_relation(group_id__in=选中组) 收集 party2_id，
 *   再用 id__in 过滤 party —— 两段桥接（见 syncBridge）。
 *
 * - 桥接不走 scopeAdapter 内联执行，而是 watch page.scopeIds['party_group'].effective：
 *   MOMP 从图表/详情切回时会 restoreStateFromDiagram 直接写 scopeIds（不触发
 *   scope-change 事件），若只在 adapter 里桥接，会出现「左树恢复了勾选、右表却是全量」。
 *   故 adapter 只做同步映射（口径同物料页），桥接统一由 watcher 响应 scopeIds 变化,
 *   用户勾选与状态恢复两条路径收敛到同一条管线。
 *
 * - 空集守卫: 后端 __in 收到空串会整体跳过条件（见 sql_adapters.py _build_conditions），
 *   回退成全量。所以「选了组但组内无伙伴」必须发 id__in='-1' 哨兵表达空结果
 *   （探针实测 0 行），不能省略条件或用空串。
 */
import { ref, watch } from 'vue'
import { MultiObjectManagementPage } from '@/components/common/MultiObjectManagementPage'
import PartyGroupScopeTree from '@/components/common/PartyGroupScopeTree/PartyGroupScopeTree.vue'
import { boService } from '@/services/boService'

defineOptions({ name: 'PartyManagement' })

const objectTypes = ['party', 'party_group']

// 桥接结果: null = 未选组（不过滤, 全量）; 数组 = 选中组下伙伴 party2_id 集合（可空 → 哨兵）
const bridgedPartyIds = ref(null)
let bridgeSeq = 0

const pageOptions = {
  defaultTab: 'party',
  tabs: {
    party: { label: '往来单位' },
    party_group: { label: '往来单位组' }
  },
  // 左树：往来单位组（纯层级分类，parent_id 自引用）
  scopeTree: {
    component: PartyGroupScopeTree,
    props: {},
    events: {}
  },
  // 主数据页无版本上下文
  disableVersionContext: true,
  stateKey: 'partyManagerState',
  menuCodeProvider: () => 'party-management',
  scopeAdapter: {
    // 只做同步映射: 树 emit {partyGroupIds, effectivePartyGroupIds} → scopeIds['party_group']
    //   - 写入 scopeIds 而非组件本地变量: 勾选态随 MOMP 快照保存/恢复
    //     (saveStateForDiagram 遍历 scopeIds, restore 时直接写回)
    //   - 桥接查询在下方 watcher 执行 (覆盖 restore 路径)
    handleScopeChange(scope, ctx) {
      const target = ctx.scopeIds?.['party_group']
      if (!target) return
      target.selected = scope.partyGroupIds || []
      target.effective = scope.effectivePartyGroupIds?.length
        ? scope.effectivePartyGroupIds
        : (scope.partyGroupIds || [])
    }
  },
  filterStrategies: {
    // 勾选往来单位组 → 按桥接的伙伴集合过滤；未选组 → 不过滤（全量）
    party(filters) {
      const ids = bridgedPartyIds.value
      if (ids === null) return filters
      if (!ids.length) return { ...filters, id__in: '-1' }  // 空集哨兵, 防后端跳条件回退全量
      return { ...filters, id__in: ids.join(',') }
    },
    // 往来单位组 tab 不受左树影响 —— 它是管理页, 用户需要看到全部组才能新建/编辑。
    // 显式声明空策略, 防落 _buildRelationshipFilters 默认分支被注入 relationExtra 噪声。
    party_group(filters) {
      return filters
    }
  }
}

const pageRef = ref(null)

// ============================================================
//  桥接: scopeIds['party_group'].effective → party2_id 集合
// ============================================================
async function syncBridge(groupIds) {
  if (!groupIds?.length) {
    bridgedPartyIds.value = null
    return
  }
  const seq = ++bridgeSeq
  try {
    // page_size 500: 单组关联数超 500 会漏伙伴（当前量级 1 条, 与物料树拉全量同口径）
    const res = await boService.query('party_relation', {
      group_id__in: groupIds.join(','),
      page_size: 500
    })
    if (seq !== bridgeSeq) return  // 快速连点: 只认最后一次的响应
    const data = res.data || res
    const items = data.items || (Array.isArray(data) ? data : [])
    const ids = [...new Set(items.map(r => r.party2_id).filter(v => v != null))]
    bridgedPartyIds.value = ids
  } catch (error) {
    if (seq !== bridgeSeq) return
    console.error('[PartyManagement] 桥接查询 party_relation 失败, 回退全量:', error)
    bridgedPartyIds.value = null  // 失败不隐藏数据（宁可全量, 不误显空集）
  }
}

// scopeIds 由 MultiObjectManagementPage 的 defineExpose({ page }) 透出;
// pageRef 就绪前 getter 返回 undefined（watch 会因 pageRef 赋值重新求值）,
// 就绪后立即触发首轮桥接 —— 含 restoreStateFromDiagram 恢复勾选的场景。
// 注意: watch 比较的是 join 字符串, adapter 反复写入相同内容不会触发重复查询。
watch(
  () => pageRef.value?.page?.scopeIds?.['party_group']?.effective?.join(','),
  (key) => {
    if (key === undefined) return
    syncBridge(pageRef.value?.page?.scopeIds?.['party_group']?.effective || [])
  },
  { immediate: true }
)

function handleToolbarAction(action) {
  const actionType = typeof action === 'string' ? action : action?.type
  if (actionType === 'refresh') {
    pageRef.value?.refresh?.()
  }
}
</script>