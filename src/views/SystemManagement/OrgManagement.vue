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
 * OrgManagement — 组织管理页（基于 MOMP 通用化注入）
 *
 * ⚠️ 依赖说明（务必阅读，防止误判已有 org 对象）：
 *   "用户组 → 组织（org）"的重命名目前仅停留在设计稿
 *   docs/spec_权限体系升级/16_role_to_permission_set_and_user_group_to_org.md（准备稿，不改代码）。
 *   元数据层尚无 org.yaml / org_functions，user_group 仍是"纯用户组"。
 *   因此本页以 user_group 作为组织的数据源：
 *     - 本页的导入导出即 user_groups 表这份主数据的导入导出（组织主数据维护）
 *     - 待 spec 16 落地（user_groups→orgs）后，本页需将对象类型/编码切到 org，
 *       并补 org_type / org_scope / org_functions 的额外管理语义。
 *
 * [MOMP 通用化 2026-08-30] 本页只做"配置注入"，不触碰 MOMP 本体：
 *   - objectTypes=['user_group']：以现有 user_group 元数据作为组织数据源
 *   - scopeTree.component=OrgScopeTree：注入自研扁平→树组织范围选择组件
 *   - scopeAdapter.handleScopeChange：把 org 范围（orgIds/effectiveOrgIds）映射到 scopeIds
 *   - filterStrategies['user_group']：effective 非空→id__in / 空→id__in 空集守卫（绝不回退全量）
 *   - disableVersionContext=true：隐藏产品/版本选择器，GlobalToolbar 保留刷新/导入/导出
 *   - stateKey/menuCodeProvider：独立图表状态暂存 key 与菜单权限编码
 */
import { ref } from 'vue'
import { MultiObjectManagementPage } from '@/components/common/MultiObjectManagementPage'
import OrgScopeTree from '@/components/common/OrgScopeTree/OrgScopeTree.vue'

defineOptions({ name: 'OrgManagement' })

const objectTypes = ['user_group']

const pageOptions = {
  defaultTab: 'user_group',
  tabs: {
    user_group: { label: '组织' }
  },
  // 注入 org 范围树（非层级单类型，扁平 → parent_id 客户端组装）
  scopeTree: {
    component: OrgScopeTree,
    props: {},
    events: {}
  },
  // org 数据页无版本上下文
  disableVersionContext: true,
  stateKey: 'orgManagerStateBeforeDiagram',
  menuCodeProvider: () => 'org-management',
  // org 范围语义映射：树 emit {orgIds, effectiveOrgIds} → scopeIds['user_group']
  scopeAdapter: {
    handleScopeChange(scope, ctx) {
      const { scopeIds, objectTypes } = ctx
      const ids = scope.effectiveOrgIds?.length ? scope.effectiveOrgIds : (scope.orgIds || [])
      objectTypes.forEach(type => {
        if (scopeIds[type]) {
          scopeIds[type].selected = (scope.orgIds || [])
          scopeIds[type].effective = ids
        }
      })
    }
  },
  // 未选组织→id__in 空集守卫，绝不回退到全量加载
  filterStrategies: {
    'user_group'(filters, scopeIds) {
      const ids = scopeIds?.['user_group']?.effective || []
      if (ids.length) return { ...filters, id__in: ids.join(',') }
      return { ...filters, id__in: '-1' }
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