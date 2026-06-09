/**
 * [FR-018] 系统/管理路由 (需要管理员权限)
 *  - 系统管理、角色权限、任务调度、审计日志
 */
export default [
  {
    path: '/system-admin',
    name: 'system-admin',
    component: () => import('@/views/SystemAdmin/index.vue'),
    meta: { title: '日志管理', requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/system/role-permission/:roleId',
    name: 'RolePermissionCenter',
    component: () => import('@/views/SystemManagement/RolePermissionCenter.vue'),
    meta: { title: '角色权限配置', requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/system/role-detail/:roleId',
    name: 'RolePermissionDetail',
    component: () => import('@/views/SystemManagement/RoleDetail.vue'),
    meta: { title: '角色详情', requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/role/:id',
    name: 'RoleDetail',
    component: () => import('@/views/SystemManagement/RoleDetail.vue'),
    meta: {
      title: '角色详情',
      requiresAuth: true,
      requiresAdmin: true
    }
  },
  {
    path: '/system/task-management',
    name: 'task-management',
    component: () => import('@/views/GenericTabContainer.vue'),
    props: { group: 'task-management' },
    meta: { title: '任务调度', requiresAuth: true }
  },
  {
    path: '/system/task-definitions',
    name: 'task-definitions',
    component: () => import('@/views/GenericObjectList.vue'),
    props: { objectType: 'scheduled_task' },
    meta: { title: '任务定义', requiresAuth: true }
  },
  {
    path: '/system/task-queues',
    name: 'task-queues',
    component: () => import('@/views/GenericObjectList.vue'),
    props: { objectType: 'task_queue' },
    meta: { title: '任务队列', requiresAuth: true }
  },
  {
    path: '/system/task-executions',
    name: 'task-executions',
    component: () => import('@/views/GenericObjectList.vue'),
    props: { objectType: 'task_execution' },
    meta: { title: '执行记录', requiresAuth: true }
  },
  {
    path: '/system/ai-async-tasks',
    name: 'ai-async-tasks',
    component: () => import('@/views/GenericObjectList.vue'),
    props: { objectType: 'ai_async_task' },
    meta: { title: 'AI异步任务', requiresAuth: true }
  }
]
