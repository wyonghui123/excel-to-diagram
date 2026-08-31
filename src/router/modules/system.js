/**
 * [FR-018] 系统/管理路由 (需要管理员权限)
 *  - 系统管理、权限集、任务调度、审计日志
 */
export default [
  {
    path: '/system-admin',
    name: 'system-admin',
    // [FIX 2026-06-12] 之前误指到 SystemAdmin/index.vue 简化版, 丢失了:
    //   - 行 click 打开 detail drawer
    //   - ID 列 link
    //   - getLogById 拉 extra_data_parsed
    //   - deleted-data-section (DELETE 操作完整明细 JSON 块)
    // 改指完整版 AuditLogManagement.vue, 所有功能立即恢复.
    component: () => import('@/views/SystemManagement/AuditLogManagement.vue'),
    meta: { title: '审计日志管理', requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/system/permission-set-permission/:roleId',
    name: 'PermissionSetCenter',
    component: () => import('@/views/SystemManagement/PermissionSetCenter.vue'),
    meta: { title: '权限集配置', requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/system/permission-set-detail/:roleId',
    name: 'PermissionSetDetailContent',
    // [FIX 2026-07-12] 路由原本指向 PermissionSetDetail.vue (简化版, 无联动)
    // 改为 PermissionSetDetailContent.vue, 含 PermissionConfigPanel + useMenuPermission
    // 修复: 权限集详情中勾掉 "管理/编辑" 后对应 "删除" 等操作明细不联动的问题
    component: () => import('@/views/SystemManagement/PermissionSetDetailContent.vue'),
    meta: { title: '权限集详情', requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/permission-set/:id',
    name: 'PermissionSetDetail',
    component: () => import('@/views/SystemManagement/PermissionSetDetail.vue'),
    meta: {
      title: '权限集详情',
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
