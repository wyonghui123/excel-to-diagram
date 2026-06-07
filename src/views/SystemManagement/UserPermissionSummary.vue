<template>
  <div class="perm-summary">
    <!-- 角色分配 -->
    <div class="perm-section">
      <h4 class="perm-section-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
        </svg>
        角色分配
        <span class="perm-count">{{ user.roles?.length || 0 }}</span>
      </h4>
      <div v-if="user.roles?.length" class="perm-tags">
        <span v-for="role in user.roles" :key="role.id" class="sm-tag sm-tag-primary">{{ role.name }}</span>
      </div>
      <div v-else class="perm-empty">未分配角色</div>
    </div>

    <!-- 用户组归属 -->
    <div class="perm-section">
      <h4 class="perm-section-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75M9 11a4 4 0 100-8 4 4 0 000 8z"/>
        </svg>
        用户组归属
        <span class="perm-count">{{ user.groups?.length || 0 }}</span>
      </h4>
      <div v-if="user.groups?.length" class="perm-group-list">
        <div v-for="group in user.groups" :key="group.id" class="perm-group-item">
          <span class="perm-group-name">{{ group.name }}</span>
          <span v-if="group.is_manager" class="sm-tag sm-tag-warning">管理员</span>
          <span v-else class="sm-tag">成员</span>
        </div>
      </div>
      <div v-else class="perm-empty">未加入任何用户组</div>
    </div>

    <!-- 功能权限 -->
    <div class="perm-section">
      <h4 class="perm-section-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>
        功能权限
        <span class="perm-count">{{ Object.keys(groupedPermissions).length }} 类资源</span>
      </h4>
      <div v-if="Object.keys(groupedPermissions).length" class="perm-resource-list">
        <div v-for="(actions, resource) in groupedPermissions" :key="resource" class="perm-resource-item">
          <span class="perm-resource-name">{{ getResourceLabel(resource) }}</span>
          <div class="perm-resource-actions">
            <span v-for="action in actions" :key="action" class="sm-tag sm-tag-success">{{ ACTION_LABELS[action] || action }}</span>
          </div>
        </div>
      </div>
      <div v-else class="perm-empty">无功能权限</div>
    </div>

    <!-- 数据权限 -->
    <div class="perm-section">
      <h4 class="perm-section-title">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M4 7v10c0 2 1.5 3 3 3h10c1.5 0 3-1 3-3V7c0-2-1.5-3-3-3H7c-1.5 0-3 1-3 3z"/>
          <path d="M4 7h16"/>
        </svg>
        数据权限
        <span class="perm-count">{{ user.data_permissions?.length || 0 }}</span>
      </h4>
      <div v-if="user.data_permissions?.length" class="perm-data-list">
        <div v-for="perm in user.data_permissions" :key="perm.id" class="perm-data-item">
          <div class="perm-data-header">
            <span class="perm-data-resource">{{ getResourceLabel(perm.resource_type) }}</span>
            <span class="sm-tag" :class="'level-' + (perm.permission_level || 'read')">{{ LEVEL_LABELS[perm.permission_level] || perm.permission_level }}</span>
          </div>
          <div class="perm-data-detail">
            <span class="perm-data-id">ID: {{ perm.resource_id }}</span>
            <span v-if="perm.inherit_to_children" class="perm-data-inherit">含子级</span>
          </div>
        </div>
      </div>
      <div v-else class="perm-empty">无数据权限</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import * as permService from '@/services/permissionService'

const props = defineProps({
  user: { type: Object, required: true }
})

function getResourceLabel(resource) {
  return permService.getResourceLabel(resource)
}

const ACTION_LABELS = permService.ACTION_LABELS

const LEVEL_LABELS = Object.fromEntries(
  Object.entries(permService.PERMISSION_LEVELS).map(([key, val]) => [key, val.label])
)

const groupedPermissions = computed(() => {
  const groups = {}
  for (const code of props.user.permissions || []) {
    const parts = code.split(':')
    if (parts.length >= 2) {
      const resource = parts[0]
      const action = parts[1]
      if (!groups[resource]) groups[resource] = new Set()
      groups[resource].add(action)
    }
  }
  const result = {}
  for (const [resource, actions] of Object.entries(groups)) {
    result[resource] = Array.from(actions).sort()
  }
  return result
})
</script>

<style scoped>
.perm-summary {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
  padding: var(--spacing-md);
}

.perm-section {
  background: var(--color-bg-layout);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
}

.perm-section-title {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin: 0 0 var(--spacing-md);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text-primary);
}

.perm-count {
  margin-left: auto;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-normal);
  color: var(--color-text-tertiary);
  background: var(--color-bg-spotlight);
  padding: 2px var(--spacing-sm);
  border-radius: var(--radius-sm);
}

.perm-tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
}

.perm-empty {
  color: var(--color-text-quaternary);
  font-size: var(--font-size-sm);
  padding: var(--spacing-md);
  text-align: center;
}

.perm-group-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.perm-group-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-container);
  border-radius: var(--radius-md);
}

.perm-group-name {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  flex: 1;
}

.perm-resource-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.perm-resource-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-container);
  border-radius: var(--radius-md);
}

.perm-resource-name {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  min-width: 100px;
}

.perm-resource-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-xs);
}

.perm-data-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.perm-data-item {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-container);
  border-radius: var(--radius-md);
}

.perm-data-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.perm-data-resource {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.perm-data-detail {
  display: flex;
  gap: var(--spacing-md);
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.perm-data-inherit {
  color: var(--color-primary);
}

.level-read { background: #e3f2fd; color: #1976d2; }
.level-write { background: #fff3e0; color: #f57c00; }
.level-admin { background: #fce4ec; color: #c62828; }
</style>
