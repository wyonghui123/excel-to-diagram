/**
 * 主数据路由（需要鉴权）
 *  - 供应来源规则试算（规则详情 + 试算面板）
 */
export default [
  {
    path: '/sourcing-rules/calc/:id?',
    name: 'SourcingRuleDetailContent',
    component: () => import('@/views/MasterData/SourcingRuleDetailContent.vue'),
    meta: { title: '供应来源规则试算', requiresAuth: true }
  }
]
