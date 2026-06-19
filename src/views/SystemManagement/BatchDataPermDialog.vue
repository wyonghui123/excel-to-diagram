<template>
  <div v-if="visible" class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog-card">
      <div class="dialog-header">
        <h3>批量配置数据权限</h3>
        <button class="close-btn" @click="$emit('close')">&times;</button>
      </div>

      <div class="dialog-body">
        <div class="form-group">
          <label>选择用户（多选）</label>
          <div class="user-select-wrapper">
            <div class="selected-users" v-if="selectedUsers.length > 0">
              <span v-for="u in selectedUsers" :key="u.id" class="user-tag">
                {{ u.display_name || u.username }}
                <button @click="removeUser(u.id)">&times;</button>
              </span>
            </div>
            <input v-model="userSearch" @input="searchUsers" @focus="showDropdown = true" placeholder="搜索用户名/邮箱..." class="search-input" />
            <div v-if="showDropdown && searchResults.length > 0" class="dropdown">
              <div v-for="u in searchResults" :key="u.id" class="dropdown-item" @click="selectUser(u)">
                {{ u.display_name || u.username }} ({{ u.username }})
              </div>
            </div>
          </div>
        </div>

        <div class="form-group">
          <label>资源类型</label>
          <select v-model="form.resource_type" class="form-select">
            <option value="domain">领域</option>
            <option value="sub_domain">子领域</option>
            <option value="service_module">服务模块</option>
            <option value="business_object">业务对象</option>
          </select>
        </div>

        <div class="form-group">
          <label>资源ID</label>
          <input v-model="form.resource_id" type="number" class="form-input" placeholder="输入资源ID" />
        </div>

        <div class="form-group">
          <label>权限级别</label>
          <select v-model="form.permission_level" class="form-select">
            <option value="read">只读</option>
            <option value="write">编辑</option>
            <option value="admin">管理</option>
          </select>
        </div>
      </div>

      <div class="dialog-footer">
        <button class="btn btn-secondary" @click="$emit('close')">取消</button>
        <button class="btn btn-primary" @click="submit" :disabled="submitting || !canSubmit">
          {{ submitting ? '提交中...' : '确认' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import * as permService from '@/services/permissionService'
import { useMessage } from '@/composables/useMessage'

const props = defineProps({ visible: Boolean })
const emit = defineEmits(['close', 'success'])

const message = useMessage()

const selectedUsers = ref([])
const userSearch = ref('')
const searchResults = ref([])
const showDropdown = ref(false)
const submitting = ref(false)

const form = ref({ resource_type: 'domain', resource_id: '', permission_level: 'read' })

const canSubmit = computed(() => selectedUsers.value.length > 0 && form.value.resource_id)

async function searchUsers() {
  if (!userSearch.value.trim()) { searchResults.value = []; return }
  try {
    const data = await permService.searchUsers(userSearch.value)
    if (data.success) {
      searchResults.value = data.data.filter(u => !selectedUsers.value.find(s => s.id === u.id))
    }
  } catch (e) { console.error('Search failed:', e) }
}

function selectUser(user) {
  selectedUsers.value.push(user)
  userSearch.value = ''
  searchResults.value = []
  showDropdown.value = false
}

function removeUser(userId) {
  selectedUsers.value = selectedUsers.value.filter(u => u.id !== userId)
}

async function submit() {
  if (!canSubmit.value) return
  submitting.value = true
  try {
    const data = await permService.batchDataPermissions({
      user_ids: selectedUsers.value.map(u => u.id),
      resource_type: form.value.resource_type,
      resource_id: parseInt(form.value.resource_id),
      permission_level: form.value.permission_level,
      inherit_to_children: true
    })
    if (data.success) {
      message.success(`成功为 ${data.data.success_count} 个用户添加数据权限`)
      emit('success')
      emit('close')
    } else {
      message.error(data.message || '添加失败')
    }
  } catch (e) { message.error('批量添加权限失败，请检查网络后重试', e) }
  finally { submitting.value = false }
}
</script>

<style scoped>
.dialog-overlay { position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.dialog-card { background: var(--color-bg-container); border-radius: var(--radius-xl); width: 480px; max-width: 90vw; max-height: 85vh; overflow-y: auto; box-shadow: var(--shadow-xl); }
.dialog-header { display: flex; align-items: center; justify-content: space-between; padding: var(--spacing-lg); border-bottom: 1px solid var(--color-border); }
.dialog-header h3 { margin: 0; font-size: var(--font-size-lg); }
.close-btn { border: none; background: transparent; font-size: 24px; cursor: pointer; color: var(--color-text-quaternary); }
.dialog-body { padding: var(--spacing-lg); display: flex; flex-direction: column; gap: var(--spacing-md); }
.dialog-footer { display: flex; justify-content: flex-end; gap: var(--spacing-sm); padding: var(--spacing-lg); border-top: 1px solid var(--color-border); }
.form-group { display: flex; flex-direction: column; gap: var(--spacing-xs); }
.form-group > label { font-size: var(--font-size-sm); font-weight: var(--font-weight-medium); color: var(--color-text-primary); }
.form-input, .form-select { padding: var(--spacing-sm) var(--spacing-md); border: 1px solid var(--color-border); border-radius: var(--radius-md); font-size: var(--font-size-sm); outline: none; }
.form-input:focus, .form-select:focus { border-color: var(--color-primary); }
.user-select-wrapper { position: relative; }
.selected-users { display: flex; flex-wrap: wrap; gap: var(--spacing-xs); margin-bottom: var(--spacing-xs); }
.user-tag { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; background: var(--color-primary-bg); color: var(--color-primary); border-radius: var(--radius-sm); font-size: var(--font-size-xs); }
.user-tag button { border: none; background: transparent; cursor: pointer; padding: 0; font-size: 14px; line-height: 1; color: var(--color-primary); }
.search-input { width: 100%; padding: var(--spacing-sm) var(--spacing-md); border: 1px solid var(--color-border); border-radius: var(--radius-md); font-size: var(--font-size-sm); outline: none; }
.search-input:focus { border-color: var(--color-primary); }
.dropdown { position: absolute; top: 100%; left: 0; right: 0; background: var(--color-bg-container); border: 1px solid var(--color-border); border-radius: var(--radius-md); max-height: 200px; overflow-y: auto; z-index: 10; box-shadow: var(--shadow-lg); }
.dropdown-item { padding: var(--spacing-sm) var(--spacing-md); cursor: pointer; font-size: var(--font-size-sm); }
.dropdown-item:hover { background: var(--color-bg-spotlight); }
.btn { padding: var(--spacing-sm) var(--spacing-lg); border-radius: var(--radius-md); font-size: var(--font-size-sm); font-weight: var(--font-weight-medium); cursor: pointer; border: none; }
.btn-primary { background: var(--color-primary); color: #fff; }
.btn-primary:hover:not(:disabled) { background: var(--color-primary-hover); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-secondary { background: var(--color-bg-tertiary); color: var(--color-text-primary); }
.btn-secondary:hover { background: var(--color-border-secondary); }
</style>
