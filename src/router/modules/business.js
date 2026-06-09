/**
 * [FR-018] 业务路由 (需要鉴权)
 *  - 列表/详情/工作台/架构图/账户
 */
export default [
  {
    path: '/diagram',
    name: 'diagram',
    component: () => import('@/views/AADiagramApp/index.vue'),
    meta: { title: '架构图', requiresAuth: true }
  },
  {
    path: '/config',
    name: 'config',
    component: () => import('@/components/ConfigApp.vue'),
    meta: { title: '配置', requiresAuth: true }
  },
  {
    path: '/product-management',
    name: 'product-management',
    component: () => import('@/views/GenericObjectList.vue'),
    props: { objectType: 'product' },
    meta: { title: '产品管理', requiresAuth: true }
  },
  {
    path: '/user-permission/:tab?',
    name: 'user-permission',
    component: () => import('@/views/GenericTabContainer.vue'),
    props: { group: 'user-permission' },
    meta: { title: '用户与权限管理', requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/business-config/:tab?',
    name: 'business-config',
    component: () => import('@/views/GenericTabContainer.vue'),
    props: { group: 'business-config' },
    meta: { title: '业务配置', requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/detail/:objectType',
    name: 'ObjectDetailCreate',
    component: () => import('@/views/ObjectDetailPage.vue'),
    meta: {
      title: '新建对象',
      requiresAuth: true,
      objectTypeParam: 'objectType',
      isDetailRoute: true
    }
  },
  {
    path: '/detail/:objectType/:id',
    name: 'ObjectDetail',
    component: () => import('@/views/ObjectDetailPage.vue'),
    meta: {
      title: '对象详情',
      requiresAuth: true,
      objectTypeParam: 'objectType',
      isDetailRoute: true
    }
  },
  {
    path: '/system/archdata',
    name: 'ArchDataManagement',
    component: () => import('@/views/SystemManagement/RelationshipManagement.vue'),
    meta: { title: '架构数据管理', requiresAuth: true }
  },
  {
    path: '/account',
    name: 'AccountSettings',
    component: () => import('@/views/AccountSettings/index.vue'),
    meta: { title: '账户设置', requiresAuth: true }
  }
]
