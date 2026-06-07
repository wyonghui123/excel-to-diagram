<template>
  <el-dialog
    :model-value="true"
    :title="`管理关联角色 - ${groupName}`"
    width="600px"
    :close-on-click-modal="false"
    @close="$emit('close')"
  >
    <el-alert type="info" :closable="false" style="margin-bottom: 16px">
      <template #title>
        用户组成员将自动继承所选角色的所有数据权限。权限的单一来源是「角色」。
      </template>
    </el-alert>

    <div v-if="loading" class="loading-state">
      <el-icon class="is-loading"><Loading /></el-icon>
      加载中...
    </div>

    <template v-else>
      <div class="section-header">
        <span>已选角色 ({{ selectedRoleIds.length }})</span>
        <el-button v-if="selectedRoleIds.length > 0" type="danger" link size="small" @click="clearAll">
          清空
        </el-button>
      </div>

      <div class="role-selector">
        <el-empty v-if="allRoles.length === 0" description="暂无可选角色，请先在「角色管理」中创建角色" />
        <el-checkbox-group v-else v-model="selectedRoleIds">
          <div
            v-for="role in allRoles"
            :key="role.id"
            class="role-item"
            :class="{ selected: selectedRoleIds.includes(role.id) }"
          >
            <el-checkbox :value="role.id">
              <div class="role-info">
                <div class="role-header">
                  <span class="role-name">{{ role.name }}</span>
                  <el-tag v-if="role.is_system" type="warning" size="small">系统</el-tag>
                </div>
                <span class="role-code">{{ role.code }}</span>
                <span v-if="role.description" class="role-desc">{{ role.description }}</span>
              </div>
            </el-checkbox>
          </div>
        </el-checkbox-group>
      </div>
    </template>

    <template #footer>
      <el-button @click="$emit('close')">取消</el-button>
      <el-button type="primary" :loading="saving" @click="handleSave">
        {{ saving ? '保存中...' : '确认保存' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import boService from '@/services/boService'

const props = defineProps({
  groupId: { type: [String, Number], required: true },
  groupName: { type: String, default: '' },
  existingRoles: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'saved'])

const allRoles = ref([])
const selectedRoleIds = ref([])
const loading = ref(false)
const saving = ref(false)

async function loadAllRoles() {
  loading.value = true
  try {
    const result = await boService.query('role', { page: 1, page_size: 100 })
    if (result.success) {
      allRoles.value = result.data?.items || []
    }
  } catch (e) {
    console.error('Failed to load roles:', e)
  } finally {
    loading.value = false
  }
}

function clearAll() {
  selectedRoleIds.value = []
}

async function handleSave() {
  saving.value = true
  try {
    const currentRoleIds = props.existingRoles.map(r => r.role_id || r.id).filter(Boolean)
    const newRoleIds = selectedRoleIds.value
    
    const toAdd = newRoleIds.filter(id => !currentRoleIds.includes(id))
    const toRemove = currentRoleIds.filter(id => !newRoleIds.includes(id))
    
    for (const roleId of toAdd) {
      await boService.associate('user_group', props.groupId, 'roles', roleId, 'role')
    }
    
    for (const roleId of toRemove) {
      await boService.dissociate('user_group', props.groupId, 'roles', roleId, 'role')
    }
    
    ElMessage.success(`成功关联 ${selectedRoleIds.value.length} 个角色`)
    emit('saved')
    emit('close')
  } catch (e) {
    ElMessage.error('网络错误')
  } finally {
    saving.value = false
  }
}

watch(() => props.existingRoles, (val) => {
  if (val && val.length > 0) {
    selectedRoleIds.value = val.map(r => r.role_id || r.id).filter(Boolean)
  }
}, { immediate: true })

onMounted(() => {
  loadAllRoles()
})
</script>

<style scoped>
.loading-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 40px;
  color: var(--el-text-color-secondary);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
}

.role-selector {
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid var(--el-border-color);
  border-radius: var(--el-border-radius-base);
}

.role-item {
  padding: 10px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  transition: background-color 0.2s;
}

.role-item:last-child {
  border-bottom: none;
}

.role-item:hover {
  background-color: var(--el-fill-color-light);
}

.role-item.selected {
  background-color: var(--el-color-primary-light-9);
}

.role-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.role-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.role-name {
  font-size: 14px;
  color: var(--el-text-color-primary);
  font-weight: 500;
}

.role-code {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: monospace;
}

.role-desc {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>
