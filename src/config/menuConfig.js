export const tabGroupConfigs = {
  'user-permission': {
    title: '用户与权限管理',
    tabs: [
      { key: 'users', label: '用户管理', objectType: 'user' },
      { key: 'user-groups', label: '用户组管理', objectType: 'user_group' },
      { key: 'roles', label: '角色管理', objectType: 'role' },
    ],
  },
  'business-config': {
    title: '业务配置',
    tabs: [
      { key: 'enum-types', label: '枚举类型', objectType: 'enum_type' },
    ],
  },
  'task-management': {
    title: '任务调度',
    tabs: [
      { key: 'task-definitions', label: '任务定义', objectType: 'scheduled_task' },
      { key: 'task-queues', label: '任务队列', objectType: 'task_queue' },
      { key: 'task-executions', label: '执行记录', objectType: 'task_execution' },
      { key: 'ai-async-tasks', label: 'AI异步任务', objectType: 'ai_async_task' },
    ],
  },
}

export function getGroupTabs(group) {
  const config = tabGroupConfigs[group]
  if (!config) return []
  return config.tabs || []
}

export function getGroupTitle(group) {
  const config = tabGroupConfigs[group]
  return config ? config.title : group
}
