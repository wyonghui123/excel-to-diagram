<script setup lang="ts">
/**
 * 重复配置警告组件
 *
 * 显示 Section 1 (管理维度) 与 Section 3 (条件型权限) 之间的重叠加警告。
 * 遵循 YonDesign 规范，使用主色淡背景 + 错误色文字。
 */
import { computed } from 'vue'
import type { Overlap } from '@/composables/useOverlaps'

interface Props {
  /** 重叠加列表 */
  overlaps: Overlap[]
  /** 是否折叠 */
  collapsed?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  collapsed: false,
})

const emit = defineEmits<{
  (e: 'view', field: string): void
  (e: 'dismiss', field: string): void
}>()

const visibleOverlaps = computed(() => props.overlaps || [])
</script>

<template>
  <div v-if="visibleOverlaps.length > 0" class="overlap-warning">
    <div class="overlap-header">
      <span class="overlap-icon">[WARNING]</span>
      <span class="overlap-title">
        检测到 {{ visibleOverlaps.length }} 个字段的重复配置
      </span>
    </div>
    <div class="overlap-list">
      <div
        v-for="overlap in visibleOverlaps"
        :key="overlap.field"
        class="overlap-item"
      >
        <div class="overlap-field">
          <span class="field-name">{{ overlap.field }}</span>
          <span class="field-count">
            涉及 {{ overlap.rules.length }} 条 Section 3 规则
          </span>
        </div>
        <div class="overlap-hint">
          <span class="hint-source">Section 1 已配：</span>
          <code class="hint-value">
            {{ overlap.dim_scope.dimension_code }} =
            [{{ overlap.dim_scope.dimension_values.join(', ') }}]
          </code>
        </div>
        <div v-if="overlap.rules.length > 0" class="overlap-rules">
          <div
            v-for="rule in overlap.rules"
            :key="rule.rule_id"
            class="rule-row"
          >
            <span class="rule-label">Section 3:</span>
            <code class="rule-value">
              {{ rule.field }} {{ rule.operator }}
              [{{ rule.value.join(', ') }}]
            </code>
            <span v-if="rule.intersection && rule.intersection.length > 0" class="rule-intersection">
              交集: [{{ rule.intersection.join(', ') }}]
            </span>
          </div>
        </div>
        <div class="overlap-action">
          Section 3 规则将在运行时覆盖 Section 1（取更严格）
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlap-warning {
  margin: var(--spacing-sm) 0;
  padding: var(--spacing-sm) var(--spacing-md);
  background: rgba(194, 65, 12, 0.08);
  border: 1px solid rgba(194, 65, 12, 0.25);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
}

.overlap-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs);
  color: var(--color-error);
  font-weight: 500;
  margin-bottom: var(--spacing-sm);
}

.overlap-icon {
  font-size: 16px;
}

.overlap-title {
  flex: 1;
}

.overlap-list {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.overlap-item {
  background: var(--color-bg-primary);
  padding: var(--spacing-sm);
  border-radius: var(--radius-sm);
  border-left: 2px solid var(--color-error);
}

.overlap-field {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-xs);
}

.field-name {
  font-weight: 500;
  color: var(--color-text-primary);
  font-family: monospace;
}

.field-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.overlap-hint,
.overlap-rules {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  margin: 2px 0;
}

.hint-source,
.rule-label {
  color: var(--color-text-tertiary);
  margin-right: 4px;
}

.hint-value,
.rule-value {
  font-family: monospace;
  color: var(--color-text-primary);
  background: var(--color-bg-secondary);
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  font-size: 11px;
}

.rule-intersection {
  color: var(--color-error);
  margin-left: var(--spacing-sm);
  font-style: italic;
}

.overlap-action {
  margin-top: var(--spacing-xs);
  padding-top: var(--spacing-xs);
  border-top: 1px dashed var(--color-border-secondary);
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
}
</style>
