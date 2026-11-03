/**
 * 主数据路由（需要鉴权）
 *  - 供应来源规则试算（规则详情 + 试算面板）
 *  - 工程变更单（列表 / 差异预览 / 详情）
 */
export default [
  {
    path: '/sourcing-rules/calc/:id?',
    name: 'SourcingRuleDetailContent',
    component: () => import('@/views/MasterData/SourcingRuleDetailContent.vue'),
    meta: { title: '供应来源规则试算', requiresAuth: true }
  },
  {
    // name 与菜单 menu_code 对齐：dynamicRoutes 通过 router.hasRoute('engineering-change')
    // 去重，避免动态路由重复注册 GenericObjectList 覆盖本页。
    path: '/master-data/engineering-change',
    name: 'engineering-change',
    component: () => import('@/views/EngineeringChangeListPage.vue'),
    meta: {
      title: '工程变更',
      requiresAuth: true,
      requiredPermissions: ['engineering_change:view']
    }
  },
  {
    path: '/master-data/engineering-change/diff',
    name: 'engineering-change-diff',
    component: () => import('@/views/EngineeringChangeDiffPage.vue'),
    meta: {
      title: '工程变更差异预览',
      requiresAuth: true,
      requiredPermissions: ['engineering_change:view']
    }
  },
  {
    path: '/master-data/engineering-change/:id',
    name: 'engineering-change-detail',
    component: () => import('@/views/EngineeringChangeDetailPage.vue'),
    meta: {
      title: '工程变更详情',
      requiresAuth: true,
      requiredPermissions: ['engineering_change:view']
    }
  }
]
