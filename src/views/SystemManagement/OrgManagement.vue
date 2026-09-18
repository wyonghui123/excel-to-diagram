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
 * [Spec 16 已落地 2026-09-18] user_group → org 切换：
 *   - 后端 object type 现为 "org" (org.yaml id: org, table: orgs)
 *   - 历史 alias "user_group" 已被 v089 DROP, 后端 registry 不再识别
 *   - 本页配置对象类型/编码已切到 org, 关联数据由 orgs / org_members 提供
 *
 * [MOMP 通用化 2026-08-30] 本页只做"配置注入"，不触碰 MOMP 本体：
 *   - objectTypes=['org']：以 org.yaml 作为组织数据源
 *   - scopeTree.component=OrgScopeTree：注入自研扁平→树组织范围选择组件
 *   - scopeAdapter.handleScopeChange：把 org 范围（orgIds/effectiveOrgIds）映射到 scopeIds
 *   - filterStrategies['org']：effective 非空→id__in / 空→id__in 空集守卫（绝不回退全量）
 *   - disableVersionContext=true：隐藏产品/版本选择器，GlobalToolbar 保留刷新/导入/导出
 *   - stateKey/menuCodeProvider：独立图表状态暂存 key 与菜单权限编码
 */
import { ref } from 'vue'
import { MultiObjectManagementPage } from '@/components/common/MultiObjectManagementPage'
import OrgScopeTree from '@/components/common/OrgScopeTree/OrgScopeTree.vue'

defineOptions({ name: 'OrgManagement' })

const objectTypes = ['org']

const pageOptions = {
  defaultTab: 'org',
  tabs: {
    org: { label: '组织' }
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
  // org 范围语义映射：树 emit {orgIds, effectiveOrgIds} → scopeIds['org']
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
  // [FIX 2026-09-02] 未选组织 → 不传 id__in, 后端返回全量
  //   原设计: id__in='-1' 空集守卫 (OrgScopeTree 安全策略, 避免未授权泄露全量)
  //   用户反馈: 组织管理页应默认展示全部组织, 守卫语义不符合业务预期
  //   行为: 有勾选 → 按 scope 过滤; 未勾选 → 不过滤, 后端全量
  filterStrategies: {
    'org'(filters, scopeIds) {
      const ids = scopeIds?.['org']?.effective || []
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