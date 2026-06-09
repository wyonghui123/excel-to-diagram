<template>
  <div class="dialog-overlay" @click.self="$emit('close')">
    <div class="dialog-card">
      <div class="dialog-header">
        <h3>个人信息</h3>
        <button class="close-btn" @click="$emit('close')">&times;</button>
      </div>

      <div class="dialog-body">
        <div class="avatar-section">
          <div class="avatar">{{ avatarText }}</div>
          <span class="avatar-hint">头像</span>
        </div>

        <div class="form-group">
          <label>用户名 <span class="required">*</span></label>
          <input
            v-model="form.username"
            type="text"
            placeholder="请输入用户名"
            disabled
          />
          <span class="hint">用户名不可修改</span>
        </div>

        <div class="form-group">
          <label>显示名称</label>
          <input
            v-model="form.displayName"
            type="text"
            placeholder="请输入显示名称"
          />
        </div>

        <div class="form-group">
          <label>电子邮件</label>
          <input
            v-model="form.email"
            type="email"
            placeholder="请输入电子邮件"
          />
        </div>

        <div v-if="errorMsg" class="error-msg">{{ errorMsg }}</div>
      </div>

      <div class="dialog-footer">
        <button class="btn btn-secondary" @click="$emit('close')">取消</button>
        <button class="btn btn-primary" @click="handleSubmit" :disabled="submitting">
          {{ submitting ? '保存中...' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { useCrudMessage } from '@/composables/useCrudMessage'
import { useUserProfileSync } from '@/composables/useUserProfileSync'
import * as authService from '@/services/authService'

const authStore = useAuthStore()
const message = useCrudMessage()
const profileSync = useUserProfileSync()
const emit = defineEmits(['close'])

const submitting = ref(false)
const errorMsg = ref('')

const form = reactive({
  username: '',
  displayName: '',
  email: ''
})

const avatarText = computed(() => {
  const name = form.displayName || authStore.userDisplayName
  return name ? name.charAt(0).toUpperCase() : '?'
})

onMounted(() => {
  loadUserProfile()
})

async function loadUserProfile() {
  try {
    const result = await authService.getProfile()
    if (result.success && result.data) {
      form.username = result.data.username || authStore.user?.username || ''
      form.displayName = result.data.display_name || authStore.userDisplayName || ''
      form.email = result.data.email || ''
    }
  } catch (e) {
    console.error('Failed to load user profile:', e)
  }
}

async function handleSubmit() {
  errorMsg.value = ''

  if (!form.displayName.trim()) {
    errorMsg.value = '显示名称不能为空'
    return
  }

  if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
    errorMsg.value = '请输入有效的电子邮件地址'
    return
  }

  submitting.value = true

  try {
    const data = await authService.updateProfile({
      display_name: form.displayName,
      email: form.email
    })

    if (data.success) {
      // [FIX 2026-06-09] 立即同步到 authStore, 顶部菜单/头像首字母实时刷新
      // 解决"改完名字没反应"导致用户误以为账号被锁的问题
      profileSync.sync({ display_name: form.displayName, email: form.email })
      message.profileUpdated()
      emit('close')
    } else {
      errorMsg.value = data.message || '保存失败'
    }
  } catch (e) {
    console.error('Save profile error:', e)
    errorMsg.value = '网络错误，请稍后重试'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.dialog-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex; align-items: center; justify-content: center;
  z-index: var(--z-index-modal-backdrop);
}

.dialog-card {
  background: var(--color-bg-container); border-radius: var(--radius-xl);
  width: 460px; max-width: 90vw; max-height: 85vh; overflow-y: auto;
  box-shadow: var(--shadow-xl);
}

.dialog-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--spacing-lg) var(--spacing-lg) 0;
}

.dialog-header h3 { margin: 0; font-size: var(--font-size-lg); color: var(--color-text-primary); }

.close-btn {
  border: none; background: transparent; font-size: 24px;
  color: var(--color-text-quaternary); cursor: pointer; padding: 0; line-height: 1;
}

.close-btn:hover { color: var(--color-text-primary); }

.dialog-body {
  padding: var(--spacing-lg);
  display: flex; flex-direction: column; gap: var(--spacing-md);
}

.avatar-section {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-xs);
  margin-bottom: var(--spacing-sm);
}

.avatar {
  width: 64px;
  height: 64px;
  border-radius: var(--radius-full);
  background: var(--color-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  font-weight: var(--font-weight-semibold);
}

.avatar-hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.form-group {
  display: flex; flex-direction: column; gap: var(--spacing-xs);
}

.form-group > label {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
}

.required { color: var(--color-error); }

.form-group input {
  padding: var(--spacing-sm) var(--spacing-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-out);
}

.form-group input:focus {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-focus);
}

.form-group input:disabled {
  background: var(--color-bg-tertiary);
  color: var(--color-text-tertiary);
  cursor: not-allowed;
}

.hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.error-msg {
  background: var(--color-error-bg);
  color: var(--color-error);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
}

.dialog-footer {
  display: flex; justify-content: flex-end; gap: var(--spacing-sm);
  padding: 0 var(--spacing-lg) var(--spacing-lg);
}

.btn {
  padding: var(--spacing-sm) var(--spacing-lg);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  font-weight: var(--font-weight-medium);
  cursor: pointer;
  border: none;
  transition: all var(--duration-fast) var(--ease-out);
}

.btn-primary { background: var(--color-primary); color: #fff; }
.btn-primary:hover:not(:disabled) { background: var(--color-primary-hover); }
.btn-primary:disabled { background: var(--color-primary-disabled); cursor: not-allowed; }
.btn-secondary { background: var(--color-bg-tertiary); color: var(--color-text-primary); }
.btn-secondary:hover { background: var(--color-border-secondary); }
</style>
