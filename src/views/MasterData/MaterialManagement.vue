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
 * MaterialManagement — 物料管理页（MOMP 配置注入）
 *
 * 左树 = 物料组（勾选过滤右表物料），右表 = 物料。配置注入模式与组织管理页一致，
 * 本页不触碰 MOMP 本体。
 *
 * - objectTypes=['item']：右表只有「物料」一个 tab。物料组不作为并列 tab，
 *   而是把「物料组」升格为左侧导航树 —— 用户查物料的自然动作是"先定位到组"。
 * - scopeTree.component=ItemGroupScopeTree：注入物料组树组件
 * - scopeAdapter：树 emit {itemGroupIds, effectiveItemGroupIds} → scopeIds['item_group']
 * - filterStrategies['item']：勾选的组 id 拼成 item_group_id__in 传给后端
 * - 未勾选 → 不传过滤条件，后端返回全量（与组织管理页一致的语义）
 */
import { ref } from 'vue'
import { MultiObjectManagementPage } from '@/components/common/MultiObjectManagementPage'
import ItemGroupScopeTree from '@/components/common/ItemGroupScopeTree/ItemGroupScopeTree.vue'

defineOptions({ name: 'MaterialManagement' })

const objectTypes = ['item']

const pageOptions = {
  defaultTab: 'item',
  tabs: {
    item: { label: '物料' }
  },
  // 左树：物料组（纯层级分类，parent_id 自引用）
  scopeTree: {
    component: ItemGroupScopeTree,
    props: {},
    events: {}
  },
  // 主数据页无版本上下文
  disableVersionContext: true,
  stateKey: 'materialManagerState',
  menuCodeProvider: () => 'material-management',
  // 物料组范围语义映射：树 emit {itemGroupIds, effectiveItemGroupIds} → scopeIds
  //   注意写入键必须与 objectTypes 对齐 (scopeIds['item']), 不能自造 scopeIds['item_group']:
  //   handleScopeChange 里 types 来自 objectTypes, 且 filterStrategies.item 读的也是
  //   scopeIds['item'].effective。组织页之所以能写 scopeIds['org'], 是因为它的
  //   objectTypes 恰好就是 ['org'], 两者同名才凑巧对上。
  scopeAdapter: {
    handleScopeChange(scope, ctx) {
      const { scopeIds, objectTypes: types } = ctx
      const effective = scope.effectiveItemGroupIds?.length
        ? scope.effectiveItemGroupIds
        : (scope.itemGroupIds || [])
      types.forEach(type => {
        if (scopeIds[type]) {
          scopeIds[type].selected = (scope.itemGroupIds || [])
          scopeIds[type].effective = effective
        }
      })
    }
  },
  // 勾选物料组 → 按组过滤物料；未勾选 → 不过滤（全量）
  //   effective 是"选中 ∪ 子孙", 故勾父组自动含子组物料 (级联)。
  filterStrategies: {
    item(filters, scopeIds) {
      const ids = scopeIds?.['item']?.effective || []
      if (ids.length) return { ...filters, item_group_id__in: ids.join(',') }
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