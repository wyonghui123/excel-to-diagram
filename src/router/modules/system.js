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
    // [P1 入口收敛] 本页已由 task.v1 直接接管（TaskCenter.vue：监控 tab + 详情抽屉），
    // 读路径走 /api/v1/tasks。遗留的 task-definitions / task-queues /
    // task-executions / ai-async-tasks 四条路由（scheduled_task 等旧实体泛型列表）
    // 已随菜单收敛一并下线——保留会让 URL 直访落回旧任务体系。
    path: '/system/task-management',
    name: 'task-management',
    component: () => import('@/views/TaskCenter/TaskCenter.vue'),
    meta: { title: '任务管理', requiresAuth: true, requiresAdmin: true }
  },
  {
    // 平台运维作业：进程内调度器状态 + 手动触发（只读/触发页，page_type=custom_page）
    path: '/system/platform-ops-jobs',
    name: 'platform-ops-jobs',
    component: () => import('@/views/SystemManagement/PlatformOpsJobs.vue'),
    meta: { title: '平台运维作业', requiresAuth: true, requiresAdmin: true }
  }
]
