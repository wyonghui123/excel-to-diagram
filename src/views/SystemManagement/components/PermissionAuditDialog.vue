<template>
  <el-dialog
    :model-value="true"
    title="权限体检"
    width="720px"
    :close-on-click-modal="false"
    class="audit-dialog"
    @close="$emit('close')"
  >
    <div v-if="loading" class="audit-loading">
      <el-icon class="is-loading"><Loading /></el-icon>
      正在检查权限一致性...
    </div>

    <template v-else>
      <!-- 总览 -->
      <el-alert
        :type="result?.ok ? 'success' : 'warning'"
        :closable="false"
        style="margin-bottom: 12px"
      >
        <template #title>
          <template v-if="result?.ok">
            体检通过：菜单权限、功能权限、数据权限三层一致，未发现问题。
          </template>
          <template v-else>
            发现 {{ result?.summary?.total_issues }} 类潜在问题
            （{{ result?.summary?.warnings }} 项警告 / {{ result?.summary?.infos }} 项提示）
          </template>
        </template>
      </el-alert>

      <!-- 空态 -->
      <el-empty
        v-if="!result?.issues?.length"
        description="未发现一致性问题"
        :image-size="80"
      />

      <!-- 问题列表 -->
      <div v-else class="audit-issue-list">
        <div v-for="issue in result.issues" :key="issue.check" class="audit-issue-card">
          <div class="audit-issue-header">
            <el-tag :type="severityTagType(issue.severity)" size="small">
              {{ severityLabel(issue.severity) }}
            </el-tag>
            <span class="audit-issue-title">{{ issue.title }}</span>
            <span class="audit-issue-count">{{ issue.count }} 项</span>
            <el-tag v-if="issue.fixable" type="success" size="small" effect="plain">
              可清理
            </el-tag>
          </div>
          <p class="audit-issue-desc">{{ issue.description }}</p>
          <div class="audit-issue-items">
            <el-tag
              v-for="(item, idx) in issue.items.slice(0, 50)"
              :key="idx"
              size="small"
              type="info"
              effect="plain"
              class="audit-issue-item"
            >
              {{ item.label || item.code }}
            </el-tag>
            <span v-if="issue.items.length > 50" class="audit-issue-more">
              ...等共 {{ issue.items.length }} 项
            </span>
          </div>
        </div>
      </div>
    </template>

    <template #footer>
      <div class="audit-footer">
        <span v-if="lastCleanupInfo" class="audit-cleanup-info">{{ lastCleanupInfo }}</span>
        <span class="audit-footer-spacer"></span>
        <el-button :disabled="loading" @click="rerunAudit">重新体检</el-button>
        <el-button
          v-if="hasFixableIssues"
          type="warning"
          plain
          :loading="cleaning"
          @click="handleCleanup"
        >
          一键清理
        </el-button>
        <el-button type="primary" @click="$emit('close')">关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useMessage } from '@/composables/useMessage'
import {
  runPermissionAudit,
  cleanupPermissionResidue,
} from '@/services/permissionService'

// [P4-新4 2026-08-29] Spec 16: 统一使用 permissionSetId
const props = defineProps<{ permissionSetId: string }>()
defineEmits<{ (e: 'close'): void }>()

const message = useMessage()

const loading = ref(true)
const cleaning = ref(false)
const result = ref<any>(null)
const lastCleanupInfo = ref('')

const hasFixableIssues = computed(
  () => result.value?.issues?.some((i: any) => i.fixable) ?? false,
)

function severityTagType(severity: string) {
  if (severity === 'error') return 'danger'
  if (severity === 'warning') return 'warning'
  return 'info'
}

function severityLabel(severity: string) {
  if (severity === 'error') return '错误'
  if (severity === 'warning') return '警告'
  return '提示'
}

async function runAudit() {
  loading.value = true
  try {
    const res: any = await runPermissionAudit(props.permissionSetId)
    result.value = res?.data || res
  } catch (e: any) {
    message.error(`权限体检失败: ${e?.message || e}`)
    result.value = null
  } finally {
    loading.value = false
  }
}

/** 手动「重新体检」：清空上一次清理反馈 */
async function rerunAudit() {
  lastCleanupInfo.value = ''
  await runAudit()
}

async function handleCleanup() {
  // [规范] 确认弹窗统一使用 ElMessageBox 标准组件
  try {
    await ElMessageBox.confirm(
      '将删除不属于任何已分配菜单的"排除(Deny)"残留记录。已授予的功能权限不会被删除。确认清理？',
      '一键清理',
      { confirmButtonText: '清理', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return // 用户取消
  }
  cleaning.value = true
  try {
    const res: any = await cleanupPermissionResidue(props.permissionSetId)
    const data = res?.data || res
    const count = data?.deleted_count ?? 0
    lastCleanupInfo.value = count > 0 ? `已清理 ${count} 条残留记录` : '没有需要清理的残留记录'
    message.success(lastCleanupInfo.value)
    await runAudit()
  } catch (e: any) {
    message.error(`清理失败: ${e?.message || e}`)
  } finally {
    cleaning.value = false
  }
}

onMounted(runAudit)
</script>

<style scoped>
.audit-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px 0;
  color: var(--color-text-secondary);
}

.audit-issue-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 420px;
  overflow-y: auto;
}

.audit-issue-card {
  border: 1px solid var(--color-border-secondary, #e5e7eb);
  border-radius: 6px;
  padding: 12px;
}

.audit-issue-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.audit-issue-title {
  font-weight: 600;
  color: var(--color-text-primary);
}

.audit-issue-count {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs, 12px);
}

.audit-issue-desc {
  margin: 8px 0;
  font-size: var(--font-size-xs, 12px);
  line-height: 1.6;
  color: var(--color-text-secondary);
}

.audit-issue-items {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.audit-issue-more {
  font-size: var(--font-size-xs, 12px);
  color: var(--color-text-tertiary);
  align-self: center;
}

.audit-footer {
  display: flex;
  align-items: center;
  gap: 8px;
}

.audit-footer-spacer {
  flex: 1;
}

.audit-cleanup-info {
  font-size: var(--font-size-xs, 12px);
  color: var(--color-success, #67c23a);
}
</style>
