<template>
  <div class="afs-root">
    <div v-if="title" class="afs-title">{{ title }}</div>
    <div v-if="missReason" class="afs-miss" data-test="flow-miss-reason">{{ missReason }}</div>
    <ol class="afs-list">
      <li
        v-for="(step, index) in steps"
        :key="`${step.step_no}-${index}`"
        class="afs-step"
        :class="`afs-step--${step.state}`"
        data-test="flow-step"
      >
        <span class="afs-step-no" data-test="flow-step-no">第 {{ step.step_no }} 步</span>
        <span class="afs-step-body">
          <span class="afs-step-approver">{{ step.approverLabel || '待分配' }}</span>
          <span class="afs-step-meta">{{ modeLabel(step.approveMode) }}<template v-if="hasSla(step.slaHours)"> · {{ step.slaHours }} 小时内</template></span>
        </span>
        <el-tag class="afs-step-state" :type="STATE_TAG_TYPES[step.state]" size="small">
          {{ STATE_LABELS[step.state] || step.state }}
        </el-tag>
        <span v-if="step.state === 'done' && step.actor" class="afs-actor" data-test="flow-step-actor">
          {{ step.actor }} · {{ step.occurredAt }}
        </span>
      </li>
    </ol>
  </div>
</template>

<script setup>
/**
 * 审批实例流转步骤条（三步态：已完成 / 进行中 / 待处理）。
 * 单一渲染组件两处复用：任务抽屉（TaskDetailDrawer）+ 单据侧只读投影（AssociationSection）。
 * 数据结构由 buildApprovalFlow 产出，组件本身不做状态推导。
 */
defineOptions({ name: 'ApprovalFlowSteps' })

defineProps({
  steps: { type: Array, default: () => [] },
  missReason: { type: String, default: '' },
  title: { type: String, default: '' }
})

const STATE_LABELS = { done: '已完成', active: '进行中', pending: '待处理' }
// el-tag 只认 primary/success/info/warning/danger；pending 用 info（灰）
const STATE_TAG_TYPES = { done: 'success', active: 'warning', pending: 'info' }
const MODE_LABELS = { any: '任一人通过', all: '全部通过' }

function modeLabel(mode) {
  return MODE_LABELS[mode] || mode || ''
}

function hasSla(hours) {
  return hours !== null && hours !== undefined && hours !== ''
}
</script>

<style scoped>
.afs-root {
  font-size: var(--font-size-sm);
}

.afs-title {
  font-weight: 600;
  margin-bottom: var(--spacing-xs);
}

.afs-miss {
  margin-bottom: var(--spacing-xs);
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.afs-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.afs-step {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--spacing-sm);
  padding: 6px var(--spacing-sm);
  border-left: 2px solid var(--color-border-secondary);
}

.afs-step--active {
  border-left-color: var(--color-primary);
  background: var(--color-primary-bg);
}

.afs-step--pending {
  color: var(--color-text-secondary);
}

.afs-step-no {
  flex: none;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.afs-step-body {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}

.afs-step-approver {
  color: var(--color-text-primary);
}

.afs-step-meta {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}

.afs-step--pending .afs-step-approver {
  color: var(--color-text-secondary);
}

.afs-actor {
  margin-left: auto;
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
}
</style>
