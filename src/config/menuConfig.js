export const tabGroupConfigs = {
  'user-permission': {
    title: '用户与权限管理',
    tabs: [
      { key: 'users', label: '用户管理', objectType: 'user' },
      { key: 'orgs', label: '组织管理', objectType: 'org' },
      { key: 'permission-sets', label: '权限集管理', objectType: 'permission_set' },
    ],
  },
  'business-config': {
    title: '业务配置',
    tabs: [
      { key: 'enum-types', label: '枚举类型', objectType: 'enum_type' },
    ],
  },
  'task-management': {
    title: '任务管理',
    // P1：仅「监控」；「定义 / 编排」归 P3。旧 4 tab（scheduled_task 等遗留实体）已切挂下线。
    tabs: [
      { key: 'monitor', label: '监控' },
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
