<template>
  <AppModal :model-value="visible" title="账户设置" width="560px" @close="$emit('close')">
    <div class="dialog-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="dialog-tab"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <div v-show="activeTab === 'profile'" class="tab-content">
      <div v-if="!isEditing" class="profile-view">
        <div class="profile-header">
          <div class="profile-avatar">{{ avatarText }}</div>
          <div>
            <div class="profile-name">{{ profileForm.username }}</div>
            <div class="profile-role">{{ userRoles }}</div>
          </div>
        </div>

        <div class="profile-fields">
          <div class="pf-row"><span class="pf-label">用户名</span><span class="pf-value">{{ profileForm.username }}</span></div>
          <div class="pf-row"><span class="pf-label">显示名称</span><span class="pf-value">{{ profileForm.displayName || '-' }}</span></div>
          <div class="pf-row"><span class="pf-label">电子邮件</span><span class="pf-value">{{ profileForm.email || '-' }}</span></div>
        </div>

        <AppButton variant="primary" size="sm" @click="isEditing = true">编辑资料</AppButton>
      </div>

      <div v-else class="profile-edit">
        <div class="form-group">
          <label>用户名</label>
          <AppInput v-model="profileForm.username" disabled />
          <span class="hint">用户名不可修改</span>
        </div>

        <div class="form-group">
          <label>显示名称</label>
          <AppInput v-model="profileForm.displayName" placeholder="请输入显示名称" :error="errors.displayName" />
        </div>

        <div class="form-group">
          <label>电子邮件</label>
          <AppInput v-model="profileForm.email" placeholder="请输入邮箱" :error="errors.email" />
        </div>

        <div v-if="submitError" class="error-msg"><AppIcon name="warning" size="14" />{{ submitError }}</div>

        <div class="dialog-actions">
          <AppButton variant="secondary" size="sm" @click="cancelEdit">取消</AppButton>
          <AppButton variant="primary" size="sm" :loading="submitting" @click="saveProfile">保存</AppButton>
        </div>
      </div>
    </div>

    <div v-show="activeTab === 'security'" class="tab-content">
      <div v-if="!authStore.mustChangePassword" class="intro-text">为保障账户安全，建议定期更换密码</div>

      <div v-if="authStore.mustChangePassword" class="force-notice">
        <AppIcon name="warning" size="14" />密码已被重置，请设置新密码
      </div>

      <div v-if="!authStore.mustChangePassword" class="form-group">
        <label>旧密码 <em>*</em></label>
        <AppInput v-model="pwdForm.oldPassword" type="password" placeholder="请输入旧密码" show-password-toggle :error="pwdErrors.oldPassword" />
      </div>

      <div class="form-group">
        <label>新密码 <em>*</em></label>
        <AppInput v-model="pwdForm.newPassword" type="password" placeholder="至少6位" show-password-toggle :error="pwdErrors.newPassword" />

        <div v-if="pwdForm.newPassword" class="strength-bar">
          <div class="strength-fill" :class="strengthClass" :style="{ width: strengthPercent + '%' }"></div>
          <span class="strength-label" :class="strengthClass">{{ strengthLabel }}</span>
        </div>
      </div>

      <div class="form-group">
        <label>确认新密码 <em>*</em></label>
        <AppInput v-model="pwdForm.confirmPassword" type="password" placeholder="再次输入新密码" show-password-toggle :error="pwdErrors.confirmPassword" />
      </div>

      <div v-if="pwdSubmitError" class="error-msg"><AppIcon name="warning" size="14" />{{ pwdSubmitError }}</div>

      <div class="dialog-actions">
        <AppButton variant="primary" size="sm" :loading="pwdSubmitting" @click="savePassword">
          {{ authStore.mustChangePassword ? '设置密码' : '修改密码' }}
        </AppButton>
      </div>
    </div>

    <div v-show="activeTab === 'preferences'" class="tab-content">
      <div class="pref-row">
        <label class="pref-label">语言</label>
        <select v-model="prefForm.locale" class="pref-select">
          <option v-for="opt in localeOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
      </div>

      <div class="pref-row">
        <label class="pref-label">时区</label>
        <select v-model="prefForm.timezone" class="pref-select">
          <option v-for="tz in commonTimezones" :key="tz" :value="tz">{{ tz }}</option>
        </select>
      </div>

      <div class="pref-row">
        <label class="pref-label">日期格式</label>
        <div class="pref-radio-group">
          <label v-for="opt in dateStyleOptions" :key="opt.value" class="pref-radio-item" :class="{ active: prefForm.dateStyle === opt.value }">
            <input type="radio" :value="opt.value" v-model="prefForm.dateStyle" />
            <span>{{ opt.label }}</span>
            <span class="pref-hint">{{ opt.hint }}</span>
          </label>
        </div>
      </div>

      <div class="pref-row">
        <label class="pref-label">时间格式</label>
        <div class="pref-radio-group">
          <label v-for="opt in timeStyleOptions" :key="opt.value" class="pref-radio-item" :class="{ active: prefForm.timeStyle === opt.value }">
            <input type="radio" :value="opt.value" v-model="prefForm.timeStyle" />
            <span>{{ opt.label }}</span>
            <span class="pref-hint">{{ opt.hint }}</span>
          </label>
        </div>
      </div>

      <div class="pref-row">
        <label class="pref-label">时间制式</label>
        <div class="pref-radio-group inline">
          <label v-for="opt in hourCycleOptions" :key="opt.value" class="pref-radio-item" :class="{ active: prefForm.hourCycle === opt.value }">
            <input type="radio" :value="opt.value" v-model.number="prefForm.hourCycle" />
            <span>{{ opt.label }}</span>
          </label>
        </div>
      </div>

      <div class="pref-preview">
        <label class="pref-label">预览</label>
        <div class="preview-box">{{ previewFormatted }}</div>
      </div>

      <div v-if="prefSubmitError" class="error-msg"><AppIcon name="warning" size="14" />{{ prefSubmitError }}</div>

      <div class="dialog-actions">
        <AppButton variant="primary" size="sm" :loading="prefSubmitting" @click="savePreferences">保存偏好设置</AppButton>
      </div>
    </div>
  </AppModal>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { useCrudMessage } from '@/composables/useCrudMessage'
import { useUserProfileSync } from '@/composables/useUserProfileSync'
import { useUserPreferencesStore } from '@/stores/userPreferences'
import { dateFormatService } from '@/services/DateFormatService'
import * as authService from '@/services/authService'
import AppModal from '@/components/common/AppModal/AppModal.vue'
import AppButton from '@/components/common/AppButton/AppButton.vue'
import AppInput from '@/components/common/AppInput/AppInput.vue'
import AppIcon from '@/components/common/AppIcon/AppIcon.vue'

const props = defineProps({ visible: Boolean })
const emit = defineEmits(['close'])

const authStore = useAuthStore()
const message = useCrudMessage()
const profileSync = useUserProfileSync()
const prefStore = useUserPreferencesStore()

const activeTab = ref('profile')
const isEditing = ref(false)
const submitting = ref(false)
const submitError = ref('')
const pwdSubmitting = ref(false)
const pwdSubmitError = ref('')
const prefSubmitting = ref(false)
const prefSubmitError = ref('')

const profileForm = reactive({ username: '', displayName: '', email: '' })
const errors = reactive({ displayName: '', email: '' })
const pwdForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })
const pwdErrors = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })
const prefForm = reactive({ locale: 'zh-CN', timezone: 'Asia/Shanghai', dateStyle: 'medium', timeStyle: 'short', hourCycle: 24 })

const tabs = [
  { key: 'profile', label: '个人信息' },
  { key: 'security', label: '安全设置' },
  { key: 'preferences', label: '偏好设置' }
]

const localeOptions = [
  { value: 'zh-CN', label: '中文（简体）' },
  { value: 'en-US', label: 'English (US)' },
  { value: 'en-GB', label: 'English (UK)' }
]

const dateStyleOptions = [
  { value: 'full', label: '完整', hint: '如: 2025年5月24日 星期六' },
  { value: 'long', label: '长', hint: '如: 2025年5月24日' },
  { value: 'medium', label: '中', hint: '如: 2025-05-24' },
  { value: 'short', label: '短', hint: '如: 25-05-24' }
]

const timeStyleOptions = [
  { value: 'full', label: '完整', hint: '如: 14:30:00 CST' },
  { value: 'long', label: '长', hint: '如: 14:30:00' },
  { value: 'medium', label: '中', hint: '如: 14:30:00' },
  { value: 'short', label: '短', hint: '如: 14:30' }
]

const hourCycleOptions = [
  { value: 24, label: '24小时制' },
  { value: 12, label: '12小时制' }
]

const commonTimezones = [
  'Asia/Shanghai', 'Asia/Tokyo', 'Asia/Seoul', 'Asia/Singapore',
  'Asia/Kolkata', 'Asia/Dubai',
  'Europe/London', 'Europe/Paris', 'Europe/Berlin', 'Europe/Moscow',
  'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
  'America/Sao_Paulo', 'America/Mexico_City',
  'Pacific/Auckland', 'Australia/Sydney',
  'UTC'
]

const previewFormatted = computed(() => {
  return dateFormatService.format(new Date(), {
    locale: prefForm.locale,
    dateStyle: prefForm.dateStyle,
    timeStyle: prefForm.timeStyle,
    timeZone: prefForm.timezone,
    hourCycle: prefForm.hourCycle
  })
})

const avatarText = computed(() => {
  const name = profileForm.displayName || authStore.userDisplayName
  return name ? name.charAt(0).toUpperCase() : '?'
})

const userRoles = computed(() => {
  const roles = authStore.user?.roles || []
  if (!roles.length) return '普通用户'
  return roles.map(r => typeof r === 'string' ? r : r.name).filter(Boolean).join(', ') || '普通用户'
})

const strengthPercent = computed(() => {
  const p = pwdForm.newPassword
  if (!p) return 0
  let s = 0
  if (p.length >= 6) s++
  if (p.length >= 8) s++
  if (/[a-z]/.test(p) && /[A-Z]/.test(p)) s++
  if (/\d/.test(p)) s++
  if (/[^a-zA-Z0-9]/.test(p)) s++
  return s <= 2 ? 33 : s <= 3 ? 66 : 100
})

const strengthLabel = computed(() => {
  if (strengthPercent.value <= 2) return '弱'
  if (strengthPercent.value <= 3) return '中'
  return '强'
})

const strengthClass = computed(() => {
  if (strengthPercent.value <= 2) return 'weak'
  if (strengthPercent.value <= 3) return 'medium'
  return 'strong'
})

onMounted(() => {
  loadProfile()
  loadPreferences()
  if (authStore.mustChangePassword) activeTab.value = 'security'
})

async function loadProfile() {
  try {
    const data = await authService.getProfile()
    if (data.success && data.data) {
      profileForm.username = data.data.username || authStore.user?.username || ''
      profileForm.displayName = data.data.display_name || authStore.user?.display_name || ''
      profileForm.email = data.data.email || ''
    }
  } catch {
    profileForm.username = authStore.user?.username || ''
    profileForm.displayName = authStore.user?.display_name || ''
    profileForm.email = authStore.user?.email || ''
  }
}

function cancelEdit() {
  isEditing.value = false
  errors.displayName = ''
  errors.email = ''
  submitError.value = ''
  loadProfile()
}

function validateProfile() {
  let ok = true
  errors.displayName = ''
  errors.email = ''
  if (!profileForm.displayName.trim()) { errors.displayName = '不能为空'; ok = false }
  if (profileForm.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(profileForm.email) && !/^[^\s@]+@[^\s@]+$/.test(profileForm.email)) { errors.email = '格式不正确'; ok = false }
  return ok
}

async function saveProfile() {
  if (!validateProfile()) return
  submitting.value = true
  submitError.value = ''
  try {
    const data = await authService.updateProfile({ display_name: profileForm.displayName, email: profileForm.email })
    if (data.success) {
      // [FIX 2026-06-09] 立即同步到 authStore, 顶部菜单/头像首字母实时刷新
      profileSync.sync({ display_name: profileForm.displayName, email: profileForm.email })
      message.profileUpdated()
      isEditing.value = false
    } else {
      submitError.value = data.message || '保存失败'
    }
  } catch { submitError.value = '网络错误' }
  finally { submitting.value = false }
}

function validatePwd() {
  let ok = true
  pwdErrors.oldPassword = ''; pwdErrors.newPassword = ''; pwdErrors.confirmPassword = ''
  if (!authStore.mustChangePassword && !pwdForm.oldPassword) { pwdErrors.oldPassword = '请输入'; ok = false }
  if (!pwdForm.newPassword) { pwdErrors.newPassword = '请输入'; ok = false }
  else if (pwdForm.newPassword.length < 6) { pwdErrors.newPassword = '至少6位'; ok = false }
  if (!pwdForm.confirmPassword) { pwdErrors.confirmPassword = '请输入'; ok = false }
  else if (pwdForm.confirmPassword !== pwdForm.newPassword) { pwdErrors.confirmPassword = '不一致'; ok = false }
  return ok
}

async function savePassword() {
  if (!validatePwd()) return
  pwdSubmitting.value = true; pwdSubmitError.value = ''
  try {
    const data = await authService.changePassword(pwdForm.oldPassword, pwdForm.newPassword)
    if (data.success) {
      message.passwordChanged()
      pwdForm.oldPassword = ''; pwdForm.newPassword = ''; pwdForm.confirmPassword = ''
      if (authStore.mustChangePassword) authStore.mustChangePassword = false
    } else { pwdSubmitError.value = data.message || '修改失败' }
  } catch { pwdSubmitError.value = '网络错误' }
  finally { pwdSubmitting.value = false }
}

async function loadPreferences() {
  try {
    const data = await authService.getProfile()
    if (data.success && data.data) {
      const d = data.data
      prefForm.locale = d.locale || 'zh-CN'
      prefForm.timezone = d.timezone || 'Asia/Shanghai'
      prefForm.dateStyle = d.date_style || 'medium'
      prefForm.timeStyle = d.time_style || 'short'
      prefForm.hourCycle = d.hour_cycle || 24
      prefStore.loadFromUser(d)
    }
  } catch (e) { console.error('Failed to load preferences:', e) }
}

async function savePreferences() {
  prefSubmitting.value = true
  prefSubmitError.value = ''
  try {
    const success = await prefStore.save({
      locale: prefForm.locale,
      timezone: prefForm.timezone,
      dateStyle: prefForm.dateStyle,
      timeStyle: prefForm.timeStyle,
      hourCycle: prefForm.hourCycle
    })
    if (success) {
      message.preferencesSaved()
      emit('close')
    } else {
      prefSubmitError.value = '保存失败，请重试'
    }
  } catch (e) { prefSubmitError.value = '网络错误' }
  finally { prefSubmitting.value = false }
}
</script>

<style scoped lang="scss">
.dialog-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--color-border);
  margin-bottom: var(--spacing-md);
  padding-bottom: -1px;
}

.dialog-tab {
  padding: 8px 16px;
  border: none;
  background: transparent;
  font-size: 13px;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;

  &:hover { color: var(--color-text-primary); }

  &.active {
    color: var(--yonyou-orange-600);
    border-bottom-color: var(--yonyou-orange-600);
    font-weight: 500;
  }
}

.tab-content {
  min-height: 200px;
}

.profile-view {
  .profile-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
  }

  .profile-avatar {
    width: 40px;
    height: 40px;
    border-radius: 50%;
    background: var(--yonyou-orange-500);
    color: #fff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 15px;
    font-weight: 600;
    flex-shrink: 0;
  }

  .profile-name { font-size: 14px; font-weight: 600; color: var(--color-text-primary); }
  .profile-role { font-size: 12px; color: var(--color-text-tertiary); margin-top: 1px; }

  .profile-fields {
    margin-bottom: 16px;
  }

  .pf-row {
    display: flex;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid var(--color-border-secondary);

    &:last-child { border-bottom: none; }
  }

  .pf-label { font-size: 13px; color: var(--color-text-tertiary); min-width: 64px; flex-shrink: 0; }
  .pf-value { font-size: 13px; color: var(--color-text-primary); }
}

.form-group {
  margin-bottom: 14px;

  label {
    display: block;
    font-size: 13px;
    font-weight: 500;
    color: var(--color-text-primary);
    margin-bottom: 4px;

    em { color: var(--color-error); font-style: normal; margin-left: 2px; }
  }

  .hint { font-size: 11px; color: var(--color-text-tertiary); margin-top: 3px; }
}

.intro-text {
  font-size: 12px;
  color: var(--color-text-secondary);
  padding: 8px 10px;
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  margin-bottom: 14px;
}

.force-notice {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: 12px;
  border-radius: var(--radius-sm);
  margin-bottom: 14px;
}

.strength-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}

.strength-fill {
  height: 3px;
  border-radius: 2px;
  flex: 1;
  transition: width 0.3s, background 0.3s;

  &.weak { background: var(--color-error); }
  &.medium { background: var(--color-warning); }
  &.strong { background: var(--color-success); }
}

.strength-label {
  font-size: 11px;
  font-weight: 500;

  &.weak { color: var(--color-error); }
  &.medium { color: var(--color-warning); }
  &.strong { color: var(--color-success); }
}

.error-msg {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 10px;
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: 12px;
  border-radius: var(--radius-sm);
  margin-bottom: 14px;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 18px;
}

.pref-row {
  margin-bottom: 14px;
}

.pref-label {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
  margin-bottom: 4px;
}

.pref-select {
  width: 100%;
  padding: 6px 10px;
  font-size: 13px;
  color: var(--color-text-primary);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  outline: none;
  cursor: pointer;

  &:focus {
    border-color: var(--color-primary);
  }
}

.pref-radio-group {
  display: flex;
  flex-direction: column;
  gap: 6px;

  &.inline {
    flex-direction: row;
    gap: 16px;
  }
}

.pref-radio-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 13px;
  transition: border-color 0.2s, background 0.2s;

  input[type="radio"] {
    width: 14px;
    height: 14px;
    accent-color: var(--color-primary);
    cursor: pointer;
    flex-shrink: 0;
  }

  span:first-of-type {
    font-weight: 500;
    color: var(--color-text-primary);
  }

  .pref-hint {
    font-size: 11px;
    color: var(--color-text-tertiary);
    margin-left: 4px;
  }

  &.active {
    border-color: var(--color-primary);
    background: var(--color-primary-bg);
  }

  &:hover {
    border-color: var(--color-primary);
  }
}

.pref-preview {
  margin-top: 14px;
}

.preview-box {
  padding: 8px 10px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}
</style>
