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
 * ⚠️ 数据源说明（Spec 16 迁移后）：
 *   本分支为 Spec 16 权限集重构分支，提交 5b2b0ed 已将 user_group.yaml
 *   迁移为 org.yaml（表 user_groups → orgs，含 org_type/org_scope/functions 语义）。
 *   org.yaml 的 semantics.aliases 声明了 user_group 别名，因此本页下方
 *   objectTypes=['user_group'] 运行时会被 registry 解析到 org（orgs 表），
 *   即当前"组织"数据源实际为主数据 org。
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
  // 未选组织→不设 id__in，默认展示全部 org（不施加范围过滤）
  filterStrategies: {
    'user_group'(filters, scopeIds) {
      const ids = scopeIds?.['user_group']?.effective || []
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