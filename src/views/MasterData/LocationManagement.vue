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
 * LocationManagement — 位置管理页（MOMP 配置注入）
 *
 * 形态：左树 = 位置树（site 场地 / warehouse 仓库 / zone 区域 / bin 库位），
 *       右表 = 位置列表。与组织管理页 / 物料管理页同构，本页不触碰 MOMP 本体。
 *
 * - objectTypes=['location']：单类型页，与 OrgManagement 同构
 * - scopeTree.component=LocationScopeTree：注入位置范围树（扁平 parent_id → 客户端组树）
 * - scopeAdapter：树 emit {locationIds, effectiveLocationIds} → scopeIds['location']
 *   写入键必须与 objectTypes 对齐（handleScopeChange 只遍历 objectTypes）
 * - filterStrategies['location']：effective（勾选 ∪ 全部子孙）非空 → id__in；
 *   未勾选 → 不过滤（后端全量），与组织管理页口径一致
 *   注意：位置是自引用树，勾中「场地」应连仓库/区域/库位一起出来，故必须用
 *   effective（含多级子孙）而不是 selected；用 id__in 而非 parent_id__in ——
 *   后者只能命中直接子级，孙级会漏。
 * - disableVersionContext=true：主数据页无产品/版本上下文，否则侧栏与详情空白
 */
import { ref } from 'vue'
import { MultiObjectManagementPage } from '@/components/common/MultiObjectManagementPage'
import LocationScopeTree from '@/components/common/LocationScopeTree/LocationScopeTree.vue'

defineOptions({ name: 'LocationManagement' })

const objectTypes = ['location']

const pageOptions = {
  defaultTab: 'location',
  tabs: {
    location: { label: '位置' }
  },
  scopeTree: {
    component: LocationScopeTree,
    props: {},
    events: {}
  },
  disableVersionContext: true,
  stateKey: 'locationManagerState',
  menuCodeProvider: () => 'location-list',
  scopeAdapter: {
    handleScopeChange(scope, ctx) {
      const { scopeIds } = ctx
      const effective = scope.effectiveLocationIds?.length
        ? scope.effectiveLocationIds
        : (scope.locationIds || [])
      const target = scopeIds['location']
      if (target) {
        target.selected = (scope.locationIds || [])
        target.effective = effective
      }
    }
  },
  filterStrategies: {
    location(filters, scopeIds) {
      const ids = scopeIds?.['location']?.effective || []
      if (ids.length) return { ...filters, id__in: ids.join(',') }
      return filters
    }
  }
}

const pageRef = ref(null)

function handleToolbarAction(action) {
  const actionType = typeof action === 'string' ? action : action?.type
  if (actionType === 'refresh') {
    pageRef.value?.refresh?.()
  }
}
</script>
