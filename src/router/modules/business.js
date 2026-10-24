/**
 * [FR-018] 业务路由 (需要鉴权)
 *  - 列表/详情/工作台/架构图/账户
 */
export default [
  {
    path: '/archdata-chart',
    name: 'archdata-chart',
    component: () => import('@/views/AADiagramApp/index.vue'),
    meta: {
      title: '架构数据图表',
      requiresAuth: true,
      hiddenFromMenu: true
    }
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
    meta: { title: '产品版本管理', requiresAuth: true }
  },
  {
    path: '/user-permission/:tab?',
    name: 'user-permission',
    component: () => import('@/views/GenericTabContainer.vue'),
    props: { group: 'user-permission' },
    meta: {
      title: '用户与权限管理',
      requiresAuth: true,
      requiresAdmin: true,
      baseTabPath: '/user-permission'
    }
  },
  {
    path: '/business-config/:tab?',
    name: 'business-config',
    component: () => import('@/views/GenericTabContainer.vue'),
    props: { group: 'business-config' },
    meta: {
      title: '业务配置',
      requiresAuth: true,
      requiresAdmin: true,
      baseTabPath: '/business-config'
    }
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
    component: () => import('@/views/SystemManagement/ArchDataManagement.vue'),
    meta: { title: '架构数据管理', requiresAuth: true }
  },
  {
    path: '/org-management',
    // [模型驱动 2026-10-24] 组织管理页不再有独立 Vue 壳：页面形态取自 org.yaml 的
    //   ui_view_config.hub（左树 = 组织层级，右表 = 组织列表），由通用 hub 页渲染。
    //   name 与 menu_code 对齐，使 dynamicRoutes 的 hasRoute 去重生效（不再重复注册）。
    name: 'org-management',
    component: () => import('@/components/common/MultiObjectHubPage/MultiObjectHubPage.vue'),
    props: { objectType: 'org', menuCode: 'org-management' },
    meta: { title: '组织管理', requiresAuth: true }
  },
  {
    path: '/account',
    name: 'AccountSettings',
    component: () => import('@/views/AccountSettings/index.vue'),
    meta: { title: '账户设置', requiresAuth: true }
  }
]
