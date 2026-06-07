<template>
  <div class="condition-rule-list">
    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="3" animated />
    </div>

    <div v-else-if="rules.length === 0" class="empty-state">
      <el-empty description="暂无条件型权限规则" :image-size="80" />
    </div>

    <div v-else class="perm-list">
      <div
        v-for="rule in rules"
        :key="rule.id"
        class="perm-item"
        :class="{ 'is-denied': rule.is_denied }"
      >
        <div class="perm-main">
          <span v-if="rule.is_denied" class="denied-badge">禁止</span>
          <span class="perm-name">{{ rule.resource_type }}</span>
          <code class="perm-condition">{{ rule.condition }}</code>
        </div>
        <div v-if="rule.friendly_condition" class="perm-friendly">
          {{ rule.friendly_condition }}
        </div>
        <div class="perm-meta">
          <span class="perm-level" :class="'level-' + rule.permission_level">
            {{ getPermLevelLabel(rule.permission_level) }}
          </span>
          <span v-if="rule.inherit_to_children" class="inherit-badge">继承</span>
          <button class="btn-link edit" @click="$emit('edit', rule)">编辑</button>
          <button class="btn-link danger" @click="handleDelete(rule)">删除</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'

interface ConditionRule {
  id: number | string
  resource_type: string
  condition: string
  friendly_condition?: string
  permission_level: 'none' | 'read' | 'write' | 'manage'
  inherit_to_children: boolean
  is_denied: boolean
}

const props = defineProps<{
  modelValue: ConditionRule[]
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [rules: ConditionRule[]]
  'delete': [rule: ConditionRule]
  'edit': [rule: ConditionRule]
}>()

const rules = computed(() => props.modelValue)

const permLevelLabels: Record<string, string> = {
  none: '无权限',
  read: '只读',
  write: '可编辑',
  manage: '完全管理'
}

function getPermLevelLabel(level: string): string {
  return permLevelLabels[level] || level
}

async function handleDelete(rule: ConditionRule) {
  try {
    await ElMessageBox.confirm(
      `确定删除条件规则 "${rule.condition}" 吗？`,
      '删除确认',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    emit('delete', rule)
  } catch {
    // 用户取消
  }
}
</script>

<style scoped lang="scss">
@import '../../../styles/mixins.scss';

.condition-rule-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.loading-state,
.empty-state {
  padding: var(--spacing-lg);
  text-align: center;
}

.perm-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.perm-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--spacing-sm);
  background: var(--color-bg-spotlight);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-light);
  transition: all var(--transition-fast);

  &:hover {
    border-color: var(--color-border);
  }

  &.is-denied {
    border-left: 3px solid var(--color-error);
    background: rgba(234, 88, 12, 0.02);
  }
}

.perm-main {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-xs);
}

.perm-name {
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  font-weight: var(--font-weight-medium);
}

.perm-condition {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
  font-family: monospace;
  background: var(--color-bg-layout);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  flex: 1;
}

.perm-friendly {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin-top: 4px;
  padding-left: 4px;
}

.perm-meta {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-xs);
}

.denied-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: 10px;
  font-weight: var(--font-weight-medium);
  margin-right: var(--spacing-xs);
}

.perm-level {
  font-size: var(--font-size-xs);
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  font-weight: var(--font-weight-medium);

  &.level-none { 
    background: #f5f5f5; 
    color: #999; 
  }
  
  &.level-read { 
    background: #e3f2fd; 
    color: #1976d2; 
  }
  
  &.level-write { 
    background: #fff3e0; 
    color: #f57c00; 
  }
  
  &.level-manage { 
    background: #fce4ec; 
    color: #c62828; 
  }
}

.inherit-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-success-bg);
  color: var(--color-success);
}

.btn-link {
  @include button-link;
  font-size: 11px;
  padding: 0;
  margin-left: auto;

  &.edit {
    color: var(--color-primary);
  }

  &.danger {
    color: var(--color-error);

    &:hover {
      text-decoration: underline;
    }
  }
}
</style>
