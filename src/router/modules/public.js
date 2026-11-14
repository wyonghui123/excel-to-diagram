/**
 * [FR-018] 公开路由 (无需鉴权)
 *  - 登录、404、500
 *  - 重定向、占位页
 */
export default [
  {
    path: '/',
    name: 'landing',
    component: () => import('@/components/ArchWorkspaceNew.vue'),
    meta: { title: '工作台' }
  },
  {
    path: '/data/:productId?/:versionId?',
    redirect: '/system/archdata'
  },
  {
    path: '/product-version',
    redirect: '/product-management'
  },
  {
    path: '/product/:id',
    redirect: to => `/detail/product/${to.params.id}`
  },
  {
    path: '/business-config/enums/:id',
    redirect: to => `/detail/enum_type/${to.params.id}`
  },
  {
    path: '/system/relationships',
    redirect: '/system/archdata'
  },
  {
    path: '/test',
    name: 'test',
    component: () => import('@/views/ComponentTest.vue'),
    meta: { title: '组件测试' }
  },
  {
    path: '/component-comparison',
    name: 'component-comparison',
    component: () => import('@/views/ComponentComparison.vue'),
    meta: { title: 'UI组件库对比' }
  },
  // [FR-008] catch-all 404：未知路径展示 404 页而非白屏。
  // Vue Router 按路由评分匹配，catch-all 评分最低，不会抢在动态路由前面。
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/components/common/NotFound.vue'),
    meta: { title: '页面不存在', public: true }
  }
]
