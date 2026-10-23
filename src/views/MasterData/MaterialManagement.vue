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
 * 形态：左树 = 物料组（勾选过滤物料），右表 = 两个 tab（物料组 / 物料）。
 * 配置注入模式与组织管理页一致，本页不触碰 MOMP 本体。
 *
 * - objectTypes=['item_group','item']：右表两个 tab，顺序与业务伙伴页一致
 *   （PartyManagement 也是分类 tab 在前：业务伙伴组 / 业务伙伴 / 业务伙伴关系）。
 *   tab 渲染顺序 = objectTypes 数组顺序（MOMP page.tabs 按此构建），
 *   2026-10-23 按用户要求把物料组提到第一位；默认激活仍是物料（defaultTab）。
 *   · 物料组 tab：全量不受左树影响（它是管理页，用户要看到全部组才能新建/编辑）
 *   · 物料 tab：受左树勾选过滤（查物料的主路径是"先定位到组"）
 *   物料组同时出现在左树与右表 tab 是有意的：左树用于过滤导航，右表 tab 用于维护。
 *   v092 下架了 item-group-list 独立菜单，若不做这个 tab 物料组将没有编辑入口。
 *
 * - scopeAdapter：树 emit {itemGroupIds, effectiveItemGroupIds} → scopeIds['item']
 *   注意写入键必须与 objectTypes 对齐, 不能自造 scopeIds['item_group']:
 *   handleScopeChange 里 types 来自 objectTypes, 且 filterStrategies.item 读的也是
 *   scopeIds['item'].effective。组织页之所以能写 scopeIds['org'], 是因为它的
 *   objectTypes 恰好就是 ['org'], 两者同名才凑巧对上。
 *
 *   故意不遍历所有 objectTypes: 一旦写入 scopeIds['item_group'], 物料组 tab 会被
 *   左树反向自过滤（勾中某个组 → 物料组列表只剩勾中的组）, 用户反而看不到全部组、
 *   无法管理未勾选的组。故此处只处理 'item'。
 *
 * - filterStrategies.item_group：显式返回空过滤。
 *   combinedFilters 是所有 tab 共享的 computed (_computeTypeFilters 按 tab 分派),
 *   未声明策略的 tab 会落到 _buildRelationshipFilters 默认分支, 被注入
 *   relationIds / relationCodes 等 relationExtra 过滤参数 —— 对物料组这种
 *   非关系对象是纯噪声, 可能让列表查不到数据。故必须显式声明空策略。
 */
import { ref } from 'vue'
import { MultiObjectManagementPage } from '@/components/common/MultiObjectManagementPage'
import ItemGroupScopeTree from '@/components/common/ItemGroupScopeTree/ItemGroupScopeTree.vue'

defineOptions({ name: 'MaterialManagement' })

const objectTypes = ['item_group', 'item']

const pageOptions = {
  defaultTab: 'item',
  tabs: {
    item: { label: '物料' },
    item_group: { label: '物料组' }
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
  scopeAdapter: {
    handleScopeChange(scope, ctx) {
      const { scopeIds } = ctx
      const effective = scope.effectiveItemGroupIds?.length
        ? scope.effectiveItemGroupIds
        : (scope.itemGroupIds || [])
      const target = scopeIds['item']
      if (target) {
        target.selected = (scope.itemGroupIds || [])
        target.effective = effective
      }
    }
  },
  filterStrategies: {
    // 勾选物料组 → 按组过滤物料；未勾选 → 不过滤（全量）
    //   effective 是"选中 ∪ 子孙", 故勾父组自动含子组物料 (级联)。
    item(filters, scopeIds) {
      const ids = scopeIds?.['item']?.effective || []
      if (ids.length) return { ...filters, item_group_id__in: ids.join(',') }
      return filters
    },
    // 物料组 tab 不受左树影响 —— 它是管理页, 用户需要看到全部组才能新建/编辑。
    item_group(filters) {
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