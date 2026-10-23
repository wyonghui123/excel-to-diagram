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
 * RegionManagement — 行政区划管理页（MOMP 配置注入）
 *
 * 形态：左树 = 行政区划树（国家 / 省级 / 地市 / 区县），右表 = 区划列表。
 *       与位置管理、组织管理、物料管理同构，本页不触碰 MOMP 本体。
 *
 * - objectTypes=['region']：单类型页
 * - scopeTree.component=RegionScopeTree：注入区划范围树（扁平 parent_id → 客户端组树）
 * - scopeAdapter：树 emit {regionIds, effectiveRegionIds} → scopeIds['region']
 *   写入键必须与 objectTypes 对齐（handleScopeChange 只遍历 objectTypes）
 * - filterStrategies['region']：effective（勾选 ∪ 全部子孙）非空 → id__in；
 *   未勾选 → 不过滤（后端全量）。
 *   与位置页同理：区划是四级自引用树，勾中「省」应连带地市/区县一起出来，
 *   故必须用 effective（含全部子孙）而不是 selected；用 id__in 而非
 *   parent_id__in —— 后者只能命中直接子级，孙级及以下会漏。
 * - disableVersionContext=true：主数据页无产品/版本上下文
 */
import { ref } from 'vue'
import { MultiObjectManagementPage } from '@/components/common/MultiObjectManagementPage'
import RegionScopeTree from '@/components/common/RegionScopeTree/RegionScopeTree.vue'

defineOptions({ name: 'RegionManagement' })

const objectTypes = ['region']

const pageOptions = {
  defaultTab: 'region',
  tabs: {
    region: { label: '行政区划' }
  },
  scopeTree: {
    component: RegionScopeTree,
    props: {},
    events: {}
  },
  disableVersionContext: true,
  stateKey: 'regionManagerState',
  menuCodeProvider: () => 'region-list',
  scopeAdapter: {
    handleScopeChange(scope, ctx) {
      const { scopeIds } = ctx
      const effective = scope.effectiveRegionIds?.length
        ? scope.effectiveRegionIds
        : (scope.regionIds || [])
      const target = scopeIds['region']
      if (target) {
        target.selected = (scope.regionIds || [])
        target.effective = effective
      }
    }
  },
  filterStrategies: {
    region(filters, scopeIds) {
      const ids = scopeIds?.['region']?.effective || []
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
